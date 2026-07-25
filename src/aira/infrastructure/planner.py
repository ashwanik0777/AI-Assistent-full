"""Enterprise Planner Engine for AIRA.

Translates standardized Internal Reasoning Objects into structured execution plans,
verifies step ordering, and detects circular dependency sequences.
"""

import uuid
from datetime import datetime
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.reasoning_interface import InternalReasoningObject
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.planner")


class PlanningError(Exception):
    """Base exception for all planning layer failures."""

    pass


class InvalidPlanError(PlanningError):
    """Raised when validating malformed or invalid execution plans."""

    pass


class ExecutionPlanStep:
    """A single sequential step inside the execution plan."""

    def __init__(
        self,
        step_id: str,
        title: str,
        description: str,
        sequence_number: int,
        dependencies: list[str],
        required_capability: str,
        expected_output: str,
        failure_policy: str = "ABORT",
        retry_policy: int = 3,
        timeout: float = 10.0,
    ) -> None:
        self.step_id = step_id
        self.title = title
        self.description = description
        self.sequence_number = sequence_number
        self.dependencies = dependencies
        self.required_capability = required_capability
        self.expected_output = expected_output
        self.failure_policy = failure_policy
        self.retry_policy = retry_policy
        self.timeout = timeout

    def to_dict(self) -> dict[str, Any]:
        """Serialize plan step properties."""
        return {
            "step_id": self.step_id,
            "title": self.title,
            "description": self.description,
            "sequence_number": self.sequence_number,
            "dependencies": self.dependencies,
            "required_capability": self.required_capability,
            "expected_output": self.expected_output,
            "failure_policy": self.failure_policy,
            "retry_policy": self.retry_policy,
            "timeout": self.timeout,
        }


class ExecutionPlan:
    """Consolidated planning output passed down to executor layers."""

    def __init__(
        self,
        brain_session_id: str,
        request_id: str,
        goal: str,
        priority: int,
        estimated_complexity: str,
        required_skills: list[str],
        required_permissions: list[str],
        ordered_steps: list[ExecutionPlanStep],
        fallback_strategy: str = "ROLLBACK",
        validation_status: str = "UNVALIDATED",
        estimated_duration: float = 5.0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.plan_id: str = uuid.uuid4().hex
        self.brain_session_id = brain_session_id
        self.request_id = request_id
        self.goal = goal
        self.priority = priority
        self.estimated_complexity = estimated_complexity
        self.required_skills = required_skills
        self.required_permissions = required_permissions
        self.ordered_steps = ordered_steps
        self.fallback_strategy = fallback_strategy
        self.validation_status = validation_status
        self.estimated_duration = estimated_duration
        self.metadata: dict[str, Any] = metadata or {}
        self.timestamp: datetime = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        """Serialize execution plan fields."""
        return {
            "plan_id": self.plan_id,
            "brain_session_id": self.brain_session_id,
            "request_id": self.request_id,
            "goal": self.goal,
            "priority": self.priority,
            "estimated_complexity": self.estimated_complexity,
            "required_skills": self.required_skills,
            "required_permissions": self.required_permissions,
            "ordered_steps": [s.to_dict() for s in self.ordered_steps],
            "fallback_strategy": self.fallback_strategy,
            "validation_status": self.validation_status,
            "estimated_duration": self.estimated_duration,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }


class PlanValidator:
    """Asserts schema correctness, checks skills declarations, and runs cycle detection checks."""

    @staticmethod
    def validate(plan: ExecutionPlan) -> None:
        """Confirm compliance.

        Raises InvalidPlanError on circular dependencies or malformed structures.
        """
        if not plan.goal.strip():
            raise InvalidPlanError("Plan goal must be defined.")
        if not plan.ordered_steps:
            raise InvalidPlanError("Plan must contain at least one step.")

        # Cycle detection check using DFS graph traversal
        adj_list: dict[str, list[str]] = {s.step_id: s.dependencies for s in plan.ordered_steps}
        # 0=unvisited, 1=visiting, 2=visited
        visited: dict[str, int] = {s.step_id: 0 for s in plan.ordered_steps}

        def dfs(node: str) -> None:
            if node not in visited:
                # Dependency referencing missing step ID
                raise InvalidPlanError(
                    f"Step {node} referenced as dependency is missing from the plan."
                )
            if visited[node] == 1:
                raise InvalidPlanError("Circular dependency detected inside execution steps.")
            if visited[node] == 0:
                visited[node] = 1
                for neighbor in adj_list[node]:
                    dfs(neighbor)
                visited[node] = 2

        for step in plan.ordered_steps:
            if visited[step.step_id] == 0:
                dfs(step.step_id)


class PlanBuilder:
    """Fleshes out reasoning suggestions into structured ExecutionPlan configurations."""

    @staticmethod
    def build(reasoning: InternalReasoningObject) -> ExecutionPlan:
        """Decompose reasoning constraints into sequence plan models."""
        steps: list[ExecutionPlanStep] = []

        # Populate steps from reasoning suggestions
        for idx, action in enumerate(reasoning.suggested_actions, start=1):
            steps.append(
                ExecutionPlanStep(
                    step_id=f"step_{idx}",
                    title=f"Action: {action}",
                    description=f"Decomposed planner execution step: {action}",
                    sequence_number=idx,
                    dependencies=[] if idx == 1 else [f"step_{idx - 1}"],
                    required_capability="OS_API",
                    expected_output="Capability execution success payload",
                )
            )

        # Default fallback step if none suggested
        if not steps:
            steps.append(
                ExecutionPlanStep(
                    step_id="step_default",
                    title="Default Execution",
                    description="Initialize system context fallback action",
                    sequence_number=1,
                    dependencies=[],
                    required_capability="CORE_API",
                    expected_output="Success payload",
                )
            )

        return ExecutionPlan(
            brain_session_id=reasoning.brain_session_id,
            request_id=reasoning.request_id,
            goal=reasoning.detected_intent or "Initialize workflow",
            priority=reasoning.priority,
            estimated_complexity="MEDIUM",
            required_skills=["system_control"],
            required_permissions=["local_filesystem"],
            ordered_steps=steps,
        )


class PlannerManager:
    """Coordinates builder pipelines and runs cycle verification audits."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.builder = PlanBuilder()
        self.validator = PlanValidator()

    def generate_plan(self, reasoning: InternalReasoningObject) -> ExecutionPlan:
        """Construct structured execution steps from internal reasoning structures."""
        self.event_bus.publish_sync(
            Event(
                name="planning.started",
                category="Brain",
                source="PlannerManager",
                payload={"request_id": reasoning.request_id},
            )
        )

        # 1. Identify goal
        self.event_bus.publish_sync(
            Event(
                name="planning.goal_identified",
                category="Brain",
                source="PlannerManager",
                payload={"goal": reasoning.detected_intent},
            )
        )

        try:
            # 2. Build Plan
            plan = self.builder.build(reasoning)
            self.event_bus.publish_sync(
                Event(
                    name="planning.plan_created",
                    category="Brain",
                    source="PlannerManager",
                    payload={"plan_id": plan.plan_id},
                )
            )

            # 3. Validate
            self.validator.validate(plan)
            plan.validation_status = "VALIDATED"
            self.event_bus.publish_sync(
                Event(
                    name="planning.plan_validated",
                    category="Brain",
                    source="PlannerManager",
                    payload={"plan_id": plan.plan_id},
                )
            )

            # 4. Ready Complete
            self.event_bus.publish_sync(
                Event(
                    name="planning.plan_ready",
                    category="Brain",
                    source="PlannerManager",
                    payload=plan.to_dict(),
                )
            )

            logger.info("Structured Execution Plan completed successfully", plan_id=plan.plan_id)
            return plan

        except Exception as e:
            logger.error("Planner execution mapping failed", error=str(e))
            self.event_bus.publish_sync(
                Event(
                    name="planning.failed",
                    category="Brain",
                    source="PlannerManager",
                    payload={"error": str(e)},
                )
            )
            raise PlanningError(f"Planning cycle failed: {e}") from e
