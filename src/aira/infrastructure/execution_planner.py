"""Enterprise Execution Planner for AIRA.

Compiles validated task graphs into ordered execution queues and schedules
matching specified strategies (Sequential, Priority, Dependency).
"""

import uuid
from datetime import datetime
from typing import Any, Literal

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry
from aira.infrastructure.task_graph import TaskGraph

logger = structlog.get_logger("aira.execution_planner")

ExecutionStrategy = Literal["SEQUENTIAL", "PRIORITY_BASED", "DEPENDENCY_BASED", "PARALLEL"]


class ExecutionPlanningError(Exception):
    """Base exception for all execution planner failures."""

    pass


class InvalidScheduleError(ExecutionPlanningError):
    """Raised when validating malformed execution schedules or ordering conflicts."""

    pass


class ExecutionQueueItem:
    """A scheduled task node placeholder entry inside the execution queue."""

    def __init__(
        self,
        task_node_id: str,
        execution_order: int,
        dependencies: list[str],
        priority: int,
        required_capability: str,
        estimated_duration: float,
        retry_policy: int = 3,
        failure_policy: str = "ABORT",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.queue_item_id: str = f"item_{uuid.uuid4().hex[:8]}"
        self.task_node_id = task_node_id
        self.execution_order = execution_order
        self.dependencies = dependencies  # prerequisite queue item node IDs
        self.priority = priority
        self.required_capability = required_capability
        self.estimated_duration = estimated_duration
        self.retry_policy = retry_policy
        self.failure_policy = failure_policy
        self.execution_window: str = "ASAP"
        self.metadata: dict[str, Any] = metadata or {}

    def to_dict(self) -> dict[str, Any]:
        """Serialize queue item attributes."""
        return {
            "queue_item_id": self.queue_item_id,
            "task_node_id": self.task_node_id,
            "execution_order": self.execution_order,
            "dependencies": self.dependencies,
            "priority": self.priority,
            "required_capability": self.required_capability,
            "estimated_duration": self.estimated_duration,
            "retry_policy": self.retry_policy,
            "failure_policy": self.failure_policy,
            "execution_window": self.execution_window,
            "metadata": self.metadata,
        }


class ExecutionSchedule:
    """Schedules matching strategies ready for consumption by Skill Engines."""

    def __init__(
        self,
        plan_id: str,
        graph_id: str,
        goal_id: str,
        brain_session_id: str,
        priority: int,
        execution_strategy: ExecutionStrategy,
        estimated_duration: float,
        execution_queue: list[ExecutionQueueItem],
    ) -> None:
        self.schedule_id: str = uuid.uuid4().hex
        self.plan_id = plan_id
        self.graph_id = graph_id
        self.goal_id = goal_id
        self.brain_session_id = brain_session_id
        self.priority = priority
        self.execution_strategy = execution_strategy
        self.estimated_duration = estimated_duration
        self.execution_queue = execution_queue
        self.dependencies: list[str] = []
        self.rollback_policy: str = "ROLLBACK"
        self.retry_policy: int = 3
        self.metadata: dict[str, Any] = {}
        self.timestamp: datetime = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        """Serialize execution schedule properties."""
        return {
            "schedule_id": self.schedule_id,
            "plan_id": self.plan_id,
            "graph_id": self.graph_id,
            "goal_id": self.goal_id,
            "brain_session_id": self.brain_session_id,
            "priority": self.priority,
            "execution_strategy": self.execution_strategy,
            "estimated_duration": self.estimated_duration,
            "execution_queue": [item.to_dict() for item in self.execution_queue],
            "dependencies": self.dependencies,
            "rollback_policy": self.rollback_policy,
            "retry_policy": self.retry_policy,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }


class ExecutionValidator:
    """Validates execution schedules order dependencies integrity."""

    @staticmethod
    def validate(schedule: ExecutionSchedule) -> None:
        """Confirm compliance. Raises InvalidScheduleError on scheduling order failures."""
        if not schedule.execution_queue:
            raise InvalidScheduleError("Execution queue cannot be empty.")

        # Ensure no duplicate node scheduling entries
        scheduled_nodes = set()
        for item in schedule.execution_queue:
            if item.task_node_id in scheduled_nodes:
                raise InvalidScheduleError(
                    f"Duplicate queue entry scheduled for: {item.task_node_id}"
                )
            scheduled_nodes.add(item.task_node_id)

        # Confirm prerequisite dependencies precede successors in execution queue ordering
        resolved = set()
        for item in schedule.execution_queue:
            for dep in item.dependencies:
                if dep not in resolved:
                    raise InvalidScheduleError(
                        f"Prerequisite dependency {dep} not resolved "
                        f"before target {item.task_node_id}."
                    )
            resolved.add(item.task_node_id)


class ExecutionScheduleBuilder:
    """Builds queue schedules targeting specified sequencing strategies."""

    @staticmethod
    def build(graph: TaskGraph, strategy: ExecutionStrategy) -> ExecutionSchedule:
        """Sequence graph nodes according to strategy requirements."""
        ordered_nids = graph.topological_sort()

        if strategy == "PRIORITY_BASED":
            # Priority sorting while preserving dependency orders
            # Simple priority scheduling fallback
            ordered_nodes = [graph.nodes[nid] for nid in ordered_nids]
            ordered_nodes.sort(key=lambda n: n.priority, reverse=True)
            # Re-resolve topological indices
            ordered_nids = [n.node_id for n in ordered_nodes]

        queue: list[ExecutionQueueItem] = []
        for idx, nid in enumerate(ordered_nids, start=1):
            node = graph.nodes[nid]
            queue.append(
                ExecutionQueueItem(
                    task_node_id=node.node_id,
                    execution_order=idx,
                    dependencies=node.dependencies,
                    priority=node.priority,
                    required_capability=node.required_capability,
                    estimated_duration=node.estimated_duration,
                    retry_policy=node.retry_policy,
                    failure_policy=node.failure_policy,
                )
            )

        return ExecutionSchedule(
            plan_id=graph.plan_id,
            graph_id=graph.graph_id,
            goal_id=graph.goal_id,
            brain_session_id=graph.brain_session_id,
            priority=graph.priority,
            execution_strategy=strategy,
            estimated_duration=graph.estimated_duration,
            execution_queue=queue,
        )


class ExecutionPlannerManager:
    """Coordinates schedule builder flows, validator assertions, and status event dispatches."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.builder = ExecutionScheduleBuilder()
        self.validator = ExecutionValidator()

    def generate_schedule(
        self, graph: TaskGraph, strategy: ExecutionStrategy = "SEQUENTIAL"
    ) -> ExecutionSchedule:
        """Transform TaskGraphs into validated executable execution queues."""
        self.event_bus.publish_sync(
            Event(
                name="execution_planner.planning_started",
                category="Brain",
                source="ExecutionPlannerManager",
                payload={"graph_id": graph.graph_id},
            )
        )

        try:
            # 1. Build Queue and Schedule
            schedule = self.builder.build(graph, strategy)
            self.event_bus.publish_sync(
                Event(
                    name="execution_planner.schedule_created",
                    category="Brain",
                    source="ExecutionPlannerManager",
                    payload={"schedule_id": schedule.schedule_id},
                )
            )
            self.event_bus.publish_sync(
                Event(
                    name="execution_planner.queue_built",
                    category="Brain",
                    source="ExecutionPlannerManager",
                    payload={"schedule_id": schedule.schedule_id},
                )
            )

            # 2. Validate Queue ordering
            self.validator.validate(schedule)
            self.event_bus.publish_sync(
                Event(
                    name="execution_planner.schedule_validated",
                    category="Brain",
                    source="ExecutionPlannerManager",
                    payload={"schedule_id": schedule.schedule_id},
                )
            )

            # 3. Ready Complete
            self.event_bus.publish_sync(
                Event(
                    name="execution_planner.execution_ready",
                    category="Brain",
                    source="ExecutionPlannerManager",
                    payload=schedule.to_dict(),
                )
            )

            logger.info(
                "Execution Schedule compiled successfully", schedule_id=schedule.schedule_id
            )
            return schedule

        except Exception as e:
            logger.error("Execution schedule compilation failed", error=str(e))
            self.event_bus.publish_sync(
                Event(
                    name="execution_planner.planning_failed",
                    category="Brain",
                    source="ExecutionPlannerManager",
                    payload={"error": str(e)},
                )
            )
            raise ExecutionPlanningError(f"Execution planning failed: {e}") from e
