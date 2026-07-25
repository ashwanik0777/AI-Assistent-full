"""Enterprise Task Graph Builder for AIRA.

Compiles execution plans into Directed Acyclic Graphs (DAG), validating dependencies
and verifying topological execution orders.
"""

import uuid
from datetime import datetime
from typing import Any, Literal

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.planner import ExecutionPlan
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.task_graph")

DependencyType = Literal["HARD", "SOFT"]


class TaskGraphError(Exception):
    """Base exception for all Task Graph failures."""

    pass


class InvalidGraphError(TaskGraphError):
    """Raised when validating malformed task graphs or circular dependency loops."""

    pass


class TaskNode:
    """A single execution node representing a plan step inside the DAG."""

    def __init__(
        self,
        task_id: str,
        title: str,
        description: str,
        dependencies: list[str],
        required_capability: str,
        estimated_duration: float = 1.0,
        priority: int = 1,
        retry_policy: int = 3,
        failure_policy: str = "ABORT",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.node_id: str = f"node_{uuid.uuid4().hex[:8]}"
        self.task_id = task_id
        self.title = title
        self.description = description
        self.dependencies = dependencies  # prerequisite node IDs
        self.dependents: list[str] = []  # successor node IDs

        self.required_capability = required_capability
        self.estimated_duration = estimated_duration
        self.priority = priority
        self.retry_policy = retry_policy
        self.failure_policy = failure_policy
        self.execution_status: str = "PENDING"
        self.metadata: dict[str, Any] = metadata or {}

    def to_dict(self) -> dict[str, Any]:
        """Serialize task node attributes."""
        return {
            "node_id": self.node_id,
            "task_id": self.task_id,
            "title": self.title,
            "description": self.description,
            "dependencies": self.dependencies,
            "dependents": self.dependents,
            "required_capability": self.required_capability,
            "estimated_duration": self.estimated_duration,
            "priority": self.priority,
            "retry_policy": self.retry_policy,
            "failure_policy": self.failure_policy,
            "execution_status": self.execution_status,
            "metadata": self.metadata,
        }


class TaskEdge:
    """Directed connection mapping dependencies between task nodes."""

    def __init__(
        self,
        source_node_id: str,
        target_node_id: str,
        dependency_type: DependencyType = "HARD",
        constraint: str | None = None,
        optional_flag: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.edge_id: str = f"edge_{uuid.uuid4().hex[:8]}"
        self.source_node_id = source_node_id
        self.target_node_id = target_node_id
        self.dependency_type = dependency_type
        self.constraint = constraint
        self.optional_flag = optional_flag
        self.metadata: dict[str, Any] = metadata or {}

    def to_dict(self) -> dict[str, Any]:
        """Serialize task edge attributes."""
        return {
            "edge_id": self.edge_id,
            "source_node_id": self.source_node_id,
            "target_node_id": self.target_node_id,
            "dependency_type": self.dependency_type,
            "constraint": self.constraint,
            "optional_flag": self.optional_flag,
            "metadata": self.metadata,
        }


class TaskGraph:
    """Container hosting DAG nodes and edges representing the complete objective plan."""

    def __init__(
        self, plan_id: str, goal_id: str, brain_session_id: str, priority: int = 1
    ) -> None:
        self.graph_id: str = uuid.uuid4().hex
        self.plan_id = plan_id
        self.goal_id = goal_id
        self.brain_session_id = brain_session_id
        self.creation_timestamp: datetime = datetime.now()
        self.priority = priority
        self.estimated_duration: float = 0.0

        self.nodes: dict[str, TaskNode] = {}
        self.edges: list[TaskEdge] = []
        self.metadata: dict[str, Any] = {}

    def add_node(self, node: TaskNode) -> None:
        """Add node to graph."""
        if node.node_id in self.nodes:
            raise InvalidGraphError(f"Duplicate node ID registered: {node.node_id}")
        self.nodes[node.node_id] = node

    def add_edge(self, edge: TaskEdge) -> None:
        """Connect nodes with directed edge."""
        if edge.source_node_id not in self.nodes or edge.target_node_id not in self.nodes:
            raise InvalidGraphError("Edge targets missing nodes references.")
        self.edges.append(edge)
        # Update node link tracking
        self.nodes[edge.target_node_id].dependencies.append(edge.source_node_id)
        self.nodes[edge.source_node_id].dependents.append(edge.target_node_id)

    def topological_sort(self) -> list[str]:
        """Verify cycle-free DAG and return topological ordering of node IDs."""
        # 0=unvisited, 1=visiting, 2=visited
        visited: dict[str, int] = {nid: 0 for nid in self.nodes}
        order: list[str] = []

        def dfs(node_id: str) -> None:
            visited[node_id] = 1
            node = self.nodes[node_id]
            for dep in node.dependencies:
                # Deduplicate check
                if dep not in visited:
                    raise InvalidGraphError(f"Step references missing dependency: {dep}")
                if visited[dep] == 1:
                    raise InvalidGraphError("Circular dependency loop detected inside task graph.")
                if visited[dep] == 0:
                    dfs(dep)
            visited[node_id] = 2
            order.append(node_id)

        for nid in self.nodes:
            if visited[nid] == 0:
                dfs(nid)

        return order

    def to_dict(self) -> dict[str, Any]:
        """Serialize task graph properties."""
        return {
            "graph_id": self.graph_id,
            "plan_id": self.plan_id,
            "goal_id": self.goal_id,
            "brain_session_id": self.brain_session_id,
            "creation_timestamp": self.creation_timestamp.isoformat(),
            "priority": self.priority,
            "estimated_duration": self.estimated_duration,
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
            "nodes": {nid: n.to_dict() for nid, n in self.nodes.items()},
            "edges": [e.to_dict() for e in self.edges],
            "metadata": self.metadata,
        }


class GraphValidator:
    """Validates structural properties including orphans checks and circular dependency loops."""

    @staticmethod
    def validate(graph: TaskGraph) -> None:
        """Confirm DAG conformity. Raises InvalidGraphError."""
        if not graph.nodes:
            raise InvalidGraphError("Graph contains no task nodes.")

        # DFS topological checking to trigger cycle detection
        graph.topological_sort()

        # Orphan check (node with no dependencies and dependents is allowed
        # ONLY if it's the sole node in the graph)
        if len(graph.nodes) > 1:
            for nid, node in graph.nodes.items():
                if not node.dependencies and not node.dependents:
                    raise InvalidGraphError(f"Orphan node detected: {nid}")


class GraphOptimizer:
    """Performs duration calculations and critical path approximations."""

    @staticmethod
    def optimize(graph: TaskGraph) -> None:
        """Calculate durations and append optimizations to metadata."""
        total_duration = sum(n.estimated_duration for n in graph.nodes.values())
        graph.estimated_duration = total_duration
        graph.metadata["optimized_at"] = datetime.now().isoformat()


class TaskGraphBuilder:
    """Translates linear ExecutionPlans into structured topological DAG models."""

    @staticmethod
    def build(plan: ExecutionPlan) -> TaskGraph:
        """Construct TaskGraph instances from ExecutionPlans."""
        graph = TaskGraph(
            plan_id=plan.plan_id,
            goal_id=plan.goal or "unknown_goal",
            brain_session_id=plan.brain_session_id,
            priority=plan.priority,
        )

        step_map: dict[str, TaskNode] = {}

        # 1. Create nodes
        for step in plan.ordered_steps:
            node = TaskNode(
                task_id=step.step_id,
                title=step.title,
                description=step.description,
                dependencies=[],  # populated by edges
                required_capability=step.required_capability,
                estimated_duration=1.0,
                priority=plan.priority,
                retry_policy=step.retry_policy,
                failure_policy=step.failure_policy,
            )
            # Override generated ID with unique step key identifier mapping
            node.node_id = f"node_{step.step_id}"
            graph.add_node(node)
            step_map[step.step_id] = node

        # 2. Construct edges from step dependencies
        for step in plan.ordered_steps:
            for dep_id in step.dependencies:
                if dep_id in step_map:
                    edge = TaskEdge(
                        source_node_id=step_map[dep_id].node_id,
                        target_node_id=step_map[step.step_id].node_id,
                        dependency_type="HARD",
                    )
                    graph.add_edge(edge)

        return graph


class TaskGraphManager:
    """Coordinates builders pipeline executions, runs validations, and publishes status events."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.builder = TaskGraphBuilder()
        self.validator = GraphValidator()
        self.optimizer = GraphOptimizer()

    def generate_graph(self, plan: ExecutionPlan) -> TaskGraph:
        """Generate, validate, and optimize task graph instances from plans."""
        self.event_bus.publish_sync(
            Event(
                name="task_graph.created",
                category="Brain",
                source="TaskGraphManager",
                payload={"plan_id": plan.plan_id},
            )
        )

        try:
            # 1. Build Graph
            graph = self.builder.build(plan)

            # 2. Validate DAG
            self.validator.validate(graph)
            self.event_bus.publish_sync(
                Event(
                    name="task_graph.validated",
                    category="Brain",
                    source="TaskGraphManager",
                    payload={"graph_id": graph.graph_id},
                )
            )

            # 3. Optimize Graph
            self.optimizer.optimize(graph)
            self.event_bus.publish_sync(
                Event(
                    name="task_graph.optimized",
                    category="Brain",
                    source="TaskGraphManager",
                    payload={"graph_id": graph.graph_id},
                )
            )

            # 4. Ready Complete
            self.event_bus.publish_sync(
                Event(
                    name="task_graph.ready",
                    category="Brain",
                    source="TaskGraphManager",
                    payload=graph.to_dict(),
                )
            )

            logger.info("Task Graph generated successfully", graph_id=graph.graph_id)
            return graph

        except Exception as e:
            logger.error("Task Graph pipeline failed", error=str(e))
            self.event_bus.publish_sync(
                Event(
                    name="task_graph.failed",
                    category="Brain",
                    source="TaskGraphManager",
                    payload={"error": str(e)},
                )
            )
            raise TaskGraphError(f"Task Graph compiling failed: {e}") from e
