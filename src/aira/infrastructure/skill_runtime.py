"""Enterprise Skill Runtime & Orchestration Engine for AIRA.

Coordinates sequential execution workflows of multiple Skill Packs, manages execution
contexts, propagates variables, and aggregates results.
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.permission_manager import PermissionManager
from aira.infrastructure.service_registry import ServiceRegistry
from aira.infrastructure.skill_engine import SkillEngineManager

logger = structlog.get_logger("aira.skill_runtime")


class ExecutionState(Enum):
    """Supported states within the skill execution workflow lifecycle."""

    CREATED = "CREATED"
    VALIDATING = "VALIDATING"
    WAITING_PERMISSION = "WAITING_PERMISSION"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING_NEXT_STEP = "WAITING_NEXT_STEP"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RECOVERING = "RECOVERING"
    CANCELLED = "CANCELLED"


@dataclass
class ExecutionContext:
    """Stores variables, goals, plan identifiers, and current state metrics."""

    execution_id: str
    session_id: str
    goal_id: str
    plan_id: str
    state: ExecutionState = ExecutionState.CREATED
    variables: dict[str, Any] = field(default_factory=dict)
    retry_count: int = 0
    priority: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionResult:
    """Unified aggregated results from every executed workflow step."""

    execution_id: str
    status: str
    completed_steps: list[str] = field(default_factory=list)
    failed_steps: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    execution_time: float = 0.0
    results: dict[str, Any] = field(default_factory=dict)
    logs: list[str] = field(default_factory=list)


@dataclass
class WorkflowStep:
    """Describes a single action inside a multi-skill orchestration workflow."""

    step_id: str
    skill_id: str
    # Maps context keys to skill parameters
    input_mappings: dict[str, str] = field(default_factory=dict)
    # Maps skill return keys to context variables
    output_mappings: dict[str, str] = field(default_factory=dict)


class SkillRuntimeError(Exception):
    """Raised when runtime orchestration or context propagation fails."""

    pass


class SkillOrchestrator:
    """Orchestrates validation, coordination, context propagation, and error retries."""

    def __init__(
        self,
        event_bus: EventBus,
        skill_engine: SkillEngineManager,
        permission_manager: PermissionManager,
    ) -> None:
        self.event_bus = event_bus
        self.skill_engine = skill_engine
        self.permission_manager = permission_manager

    def execute_workflow(
        self, context: ExecutionContext, steps: list[WorkflowStep]
    ) -> ExecutionResult:
        """Sequential run of workflow steps propagating values dynamically."""
        start_time = time.time()
        completed_steps = []
        failed_steps = []
        warnings = []
        results = {}
        logs = []

        context.state = ExecutionState.VALIDATING
        self.event_bus.publish_sync(
            Event(
                name="runtime.context_created",
                category="Orchestration",
                source="SkillOrchestrator",
                payload={"execution_id": context.execution_id},
            )
        )

        self.event_bus.publish_sync(
            Event(
                name="runtime.execution_started",
                category="Orchestration",
                source="SkillOrchestrator",
                payload={"execution_id": context.execution_id},
            )
        )

        context.state = ExecutionState.READY

        for step in steps:
            context.state = ExecutionState.RUNNING
            self.event_bus.publish_sync(
                Event(
                    name="runtime.skill_selected",
                    category="Orchestration",
                    source="SkillOrchestrator",
                    payload={"execution_id": context.execution_id, "skill_id": step.skill_id},
                )
            )

            # 1. Resolve skill
            skill = self.skill_engine.skill_registry.get(step.skill_id)
            if not skill:
                context.state = ExecutionState.FAILED
                err_msg = f"Step {step.step_id} failed: Skill {step.skill_id} not found."
                logs.append(err_msg)
                failed_steps.append(step.step_id)
                self.event_bus.publish_sync(
                    Event(
                        name="runtime.skill_failed",
                        category="Orchestration",
                        source="SkillOrchestrator",
                        payload={"execution_id": context.execution_id, "error": err_msg},
                    )
                )
                break

            # 2. Build inputs from context mappings
            inputs = {}
            for target_key, src_key in step.input_mappings.items():
                if src_key in context.variables:
                    inputs[target_key] = context.variables[src_key]
                else:
                    warnings.append(
                        f"Input mapping source '{src_key}' missing from context variables."
                    )

            self.event_bus.publish_sync(
                Event(
                    name="runtime.skill_started",
                    category="Orchestration",
                    source="SkillOrchestrator",
                    payload={"execution_id": context.execution_id, "skill_id": step.skill_id},
                )
            )

            # 3. Execution attempts inside retry bounds
            step_success = False
            step_result = {}
            retry_limit = 2

            for attempt in range(retry_limit):
                try:
                    step_result = skill.execute(inputs)
                    step_success = True
                    break
                except Exception as ex:
                    logs.append(f"Attempt {attempt + 1} on step {step.step_id} failed: {ex!s}")
                    context.retry_count += 1
                    context.state = ExecutionState.RECOVERING

            if not step_success:
                context.state = ExecutionState.FAILED
                failed_steps.append(step.step_id)
                self.event_bus.publish_sync(
                    Event(
                        name="runtime.skill_failed",
                        category="Orchestration",
                        source="SkillOrchestrator",
                        payload={
                            "execution_id": context.execution_id,
                            "error": f"Failed step: {step.step_id}",
                        },
                    )
                )
                break

            # 4. Map outputs to context variables
            for src_key, target_key in step.output_mappings.items():
                if src_key in step_result:
                    context.variables[target_key] = step_result[src_key]

            completed_steps.append(step.step_id)
            results[step.step_id] = step_result
            logs.append(f"Completed step {step.step_id} using {step.skill_id}.")

            self.event_bus.publish_sync(
                Event(
                    name="runtime.skill_completed",
                    category="Orchestration",
                    source="SkillOrchestrator",
                    payload={"execution_id": context.execution_id, "skill_id": step.skill_id},
                )
            )

            context.state = ExecutionState.WAITING_NEXT_STEP

        context.state = (
            ExecutionState.COMPLETED if len(failed_steps) == 0 else ExecutionState.FAILED
        )

        self.event_bus.publish_sync(
            Event(
                name="runtime.execution_finished",
                category="Orchestration",
                source="SkillOrchestrator",
                payload={"execution_id": context.execution_id, "status": context.state.value},
            )
        )

        return ExecutionResult(
            execution_id=context.execution_id,
            status=context.state.value,
            completed_steps=completed_steps,
            failed_steps=failed_steps,
            warnings=warnings,
            execution_time=time.time() - start_time,
            results=results,
            logs=logs,
        )


class SkillRuntimeManager:
    """Entry point managing orchestration workflows execution and demo scenarios."""

    def __init__(
        self,
        config: AppConfig,
        registry: ServiceRegistry,
        event_bus: EventBus,
        permission_manager: PermissionManager,
        skill_engine: SkillEngineManager,
    ) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus
        self.permission_manager = permission_manager
        self.skill_engine = skill_engine

        self.orchestrator = SkillOrchestrator(event_bus, skill_engine, permission_manager)

    def run_scenario_1(self) -> ExecutionResult:
        """Scenario 1: Open VS Code, verify application is running."""
        context = ExecutionContext(
            execution_id="scenario_1",
            session_id="session_1",
            goal_id="goal_1",
            plan_id="plan_1",
            variables={"app_name": "vscode"},
        )

        steps = [
            WorkflowStep(
                step_id="step_open_vscode",
                skill_id="app_open",
                input_mappings={"app_name": "app_name"},
                output_mappings={"status": "open_status"},
            )
        ]
        return self.orchestrator.execute_workflow(context, steps)

    def run_scenario_2(self) -> ExecutionResult:
        """Scenario 2: Resolve workspace, list project files."""
        context = ExecutionContext(
            execution_id="scenario_2",
            session_id="session_2",
            goal_id="goal_2",
            plan_id="plan_2",
            variables={"folder_path": "WORKSPACE"},
        )

        steps = [
            WorkflowStep(
                step_id="step_create_dir",
                skill_id="create_folder",
                input_mappings={"path": "folder_path"},
                output_mappings={"status": "create_status"},
            )
        ]
        return self.orchestrator.execute_workflow(context, steps)

    def run_scenario_3(self) -> ExecutionResult:
        """Scenario 3: Open terminal, run git status."""
        context = ExecutionContext(
            execution_id="scenario_3",
            session_id="session_3",
            goal_id="goal_3",
            plan_id="plan_3",
            variables={"exec": "git", "args": ["status"], "cwd": "WORKSPACE"},
        )

        steps = [
            WorkflowStep(
                step_id="step_run_git",
                skill_id="terminal_execute",
                input_mappings={"executable": "exec", "arguments": "args", "cwd": "cwd"},
                output_mappings={"exit_code": "exit_code", "stdout": "git_stdout"},
            )
        ]
        return self.orchestrator.execute_workflow(context, steps)

    def run_scenario_4(self) -> ExecutionResult:
        """Scenario 4: Open browser, navigate, verify loaded."""
        context = ExecutionContext(
            execution_id="scenario_4",
            session_id="session_4",
            goal_id="goal_4",
            plan_id="plan_4",
            variables={"url": "https://localhost:3000"},
        )

        steps = [
            WorkflowStep(
                step_id="step_open_browser",
                skill_id="browser_open",
                input_mappings={},
                output_mappings={"status": "browser_status"},
            ),
            WorkflowStep(
                step_id="step_navigate_browser",
                skill_id="browser_navigate",
                input_mappings={"url": "url"},
                output_mappings={"status": "navigate_status"},
            ),
        ]
        return self.orchestrator.execute_workflow(context, steps)
