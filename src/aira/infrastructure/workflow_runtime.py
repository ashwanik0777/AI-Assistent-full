"""Enterprise Workflow Runtime & Orchestration Engine for AIRA.

Provides workflow session containers, execution cursors tracking pointers,
outcome aggregations, and events propagation.
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry
from aira.infrastructure.skill_runtime import ExecutionContext, SkillRuntimeManager, WorkflowStep
from aira.infrastructure.wdl_parser import StepDefinition, WorkflowDefinition

logger = structlog.get_logger("aira.workflow_runtime")


class WorkflowLifecycle(Enum):
    """Supported states within the workflow execution runtime lifecycle."""

    CREATED = "CREATED"
    VALIDATING = "VALIDATING"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    ARCHIVED = "ARCHIVED"


@dataclass
class WorkflowSession:
    """Active runtime representation of an executing workflow definition blueprint."""

    session_id: str
    workflow_id: str
    execution_token: str
    brain_session_id: str
    goal_id: str
    execution_plan_id: str
    current_step_id: str
    state: WorkflowLifecycle = WorkflowLifecycle.CREATED
    priority: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)
    creation_time: float = field(default_factory=time.time)
    last_update: float = field(default_factory=time.time)


class ExecutionCursor:
    """Manages progression pointers, historical traces, and step listings."""

    def __init__(self, steps: list[StepDefinition]) -> None:
        self.steps = steps
        self.index = 0
        self.execution_history: list[str] = []

    def current_step(self) -> StepDefinition | None:
        """Fetch step definition at the current index pointer."""
        if 0 <= self.index < len(self.steps):
            return self.steps[self.index]
        return None

    def advance(self) -> None:
        """Move cursor pointer forward one step."""
        current = self.current_step()
        if current:
            self.execution_history.append(current.step_id)
        self.index += 1

    def next_step(self) -> StepDefinition | None:
        """Preview step definition after the current index pointer."""
        nxt = self.index + 1
        if 0 <= nxt < len(self.steps):
            return self.steps[nxt]
        return None

    def previous_step(self) -> StepDefinition | None:
        """Fetch step definition prior to the current index pointer."""
        prev = self.index - 1
        if 0 <= prev < len(self.steps):
            return self.steps[prev]
        return None

    def history(self) -> list[str]:
        """Fetch ordered step identifiers representing completed executions."""
        return self.execution_history


class WorkflowRuntimeError(Exception):
    """Raised when session creation, cursor movements, or token operations fail."""

    pass


class WorkflowRuntimeManager:
    """Coordinates session creation, cursor movements, and skill orchestrations."""

    def __init__(
        self,
        config: AppConfig,
        registry: ServiceRegistry,
        event_bus: EventBus,
        skill_runtime: SkillRuntimeManager,
    ) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus
        self.skill_runtime = skill_runtime

    def execute_workflow(self, definition: WorkflowDefinition) -> dict[str, Any]:
        """Run workflow steps sequentially by mapping to Skill Runtime orchestrations."""
        start_time = time.time()
        token = f"token_{int(time.time())}"
        session_id = f"session_{definition.workflow_id}"

        session = WorkflowSession(
            session_id=session_id,
            workflow_id=definition.workflow_id,
            execution_token=token,
            brain_session_id=definition.brain_session_id,
            goal_id=definition.goal_id,
            execution_plan_id=definition.execution_plan_id,
            current_step_id="",
        )

        session.state = WorkflowLifecycle.VALIDATING
        self.event_bus.publish_sync(
            Event(
                name="workflow.started",
                category="Workflow",
                source="WorkflowRuntimeManager",
                payload={"workflow_id": definition.workflow_id, "execution_token": token},
            )
        )

        cursor = ExecutionCursor(definition.steps)
        session.state = WorkflowLifecycle.RUNNING

        completed_steps = []
        failed_steps = []
        results = {}
        logs = []

        while cursor.current_step() is not None:
            step = cursor.current_step()
            if not step:
                break

            session.current_step_id = step.step_id
            session.last_update = time.time()

            self.event_bus.publish_sync(
                Event(
                    name="workflow.step_started",
                    category="Workflow",
                    source="WorkflowRuntimeManager",
                    payload={"workflow_id": definition.workflow_id, "step_id": step.step_id},
                )
            )

            # Adapt WDL StepDefinition to Skill Orchestrator WorkflowStep
            orchestrator_step = WorkflowStep(
                step_id=step.step_id,
                skill_id=step.skill,
                input_mappings=step.input_mappings,
                output_mappings=step.output_mappings,
            )

            # Build temporary context variables from parsed steps input parameters
            variables = {}
            for target_key, src_key in step.input_mappings.items():
                variables[src_key] = target_key  # Seed values to satisfy parameter resolution

            # Run individual step through Skill Runtime orchestrator
            exec_ctx = ExecutionContext(
                execution_id=step.step_id,
                session_id=session.session_id,
                goal_id=session.goal_id,
                plan_id=session.execution_plan_id,
                variables=variables,
            )

            try:
                res = self.skill_runtime.orchestrator.execute_workflow(
                    exec_ctx, [orchestrator_step]
                )

                if res.status == "COMPLETED":
                    completed_steps.append(step.step_id)
                    results[step.step_id] = res.results
                    logs.extend(res.logs)

                    self.event_bus.publish_sync(
                        Event(
                            name="workflow.step_completed",
                            category="Workflow",
                            source="WorkflowRuntimeManager",
                            payload={
                                "workflow_id": definition.workflow_id,
                                "step_id": step.step_id,
                            },
                        )
                    )
                else:
                    failed_steps.append(step.step_id)
                    logs.extend(res.logs)

                    self.event_bus.publish_sync(
                        Event(
                            name="workflow.step_failed",
                            category="Workflow",
                            source="WorkflowRuntimeManager",
                            payload={
                                "workflow_id": definition.workflow_id,
                                "step_id": step.step_id,
                            },
                        )
                    )
                    break  # Halts on step failures
            except Exception as ex:
                failed_steps.append(step.step_id)
                err_msg = f"Step execution error: {ex!s}"
                logs.append(err_msg)

                self.event_bus.publish_sync(
                    Event(
                        name="workflow.step_failed",
                        category="Workflow",
                        source="WorkflowRuntimeManager",
                        payload={"workflow_id": definition.workflow_id, "step_id": step.step_id},
                    )
                )
                break

            cursor.advance()

        session.state = (
            WorkflowLifecycle.COMPLETED if len(failed_steps) == 0 else WorkflowLifecycle.FAILED
        )

        event_name = (
            "workflow.completed"
            if session.state == WorkflowLifecycle.COMPLETED
            else "workflow.failed"
        )

        self.event_bus.publish_sync(
            Event(
                name=event_name,
                category="Workflow",
                source="WorkflowRuntimeManager",
                payload={"workflow_id": definition.workflow_id, "execution_token": token},
            )
        )

        return {
            "session_id": session.session_id,
            "execution_token": token,
            "status": session.state.value,
            "completed_steps": completed_steps,
            "failed_steps": failed_steps,
            "results": results,
            "logs": logs,
            "execution_time": time.time() - start_time,
        }
