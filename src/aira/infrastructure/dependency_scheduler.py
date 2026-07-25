"""Enterprise Parallel Execution & Dependency Graph Scheduler for AIRA.

Provides DAG cycle validations, concurrent thread-pool worker coordinators,
and dependency-aware scheduling queue systems.
"""

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from enum import Enum
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.dependency_scheduler")


class DependencySchedulerError(Exception):
    """Raised when dependency cycles, worker crashes, or queue deadlocks occur."""

    pass


class TaskState(Enum):
    """Execution status indicators for schedule queue items."""

    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"


class DependencyGraph:
    """Directed Acyclic Graph (DAG) for tasks and dependency linkages validation."""

    def __init__(self) -> None:
        self.nodes: set[str] = set()
        self.dependencies: dict[str, set[str]] = {}  # task_id -> set of prerequisite task_ids

    def add_node(self, node_id: str) -> None:
        """Add node to graph."""
        self.nodes.add(node_id)
        if node_id not in self.dependencies:
            self.dependencies[node_id] = set()

    def add_dependency(self, node_id: str, depends_on: str) -> None:
        """Define dependency relationship between nodes."""
        self.add_node(node_id)
        self.add_node(depends_on)
        self.dependencies[node_id].add(depends_on)

    def validate(self) -> None:
        """Perform cycle detection scan using Depth-First Search."""
        visited: dict[str, int] = {
            node: 0 for node in self.nodes
        }  # 0=unvisited, 1=visiting, 2=visited

        def dfs(node: str) -> bool:
            visited[node] = 1
            for pre in self.dependencies.get(node, set()):
                if visited[pre] == 1:
                    return True  # Cycle detected
                if visited[pre] == 0 and dfs(pre):
                    return True
            visited[node] = 2
            return False

        for node in self.nodes:
            if visited[node] == 0 and dfs(node):
                raise DependencySchedulerError(
                    f"Circular dependency cycle detected at node '{node}'."
                )


class WorkerPool:
    """Thread pool manager allocated for parallel task scheduling."""

    def __init__(self, thread_count: int = 4) -> None:
        self.thread_count = thread_count
        self.executor: ThreadPoolExecutor | None = None

    def start(self) -> None:
        """Initialize executor pool."""
        self.executor = ThreadPoolExecutor(
            max_workers=self.thread_count, thread_name_prefix="aira_worker"
        )

    def shutdown(self) -> None:
        """Shutdown pool, clean up resources."""
        if self.executor:
            self.executor.shutdown(wait=True)
            self.executor = None


class ExecutionQueue:
    """Manages scheduler queue task execution states thread-safely."""

    def __init__(self) -> None:
        self.states: dict[str, TaskState] = {}
        self.lock = threading.Lock()

    def set_state(self, task_id: str, state: TaskState) -> None:
        """Update task state in the queue."""
        with self.lock:
            self.states[task_id] = state

    def get_state(self, task_id: str) -> TaskState:
        """Fetch task state."""
        with self.lock:
            return self.states.get(task_id, TaskState.PENDING)


class DependencySchedulerManager:
    """Orchestrates DAG building, thread worker delegation, and queue monitoring."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.worker_pool = WorkerPool()
        self.execution_queue = ExecutionQueue()

    def run_parallel_tasks(
        self, graph: DependencyGraph, tasks_map: dict[str, Callable[[], Any]]
    ) -> dict[str, Any]:
        """Execute independent tasks concurrently while honoring DAG sequence requirements."""
        graph.validate()
        self.worker_pool.start()

        # Initialize queue states
        for node in graph.nodes:
            self.execution_queue.set_state(node, TaskState.PENDING)

        results: dict[str, Any] = {}
        completed_nodes: set[str] = set()
        active_futures = {}

        try:
            while len(completed_nodes) < len(graph.nodes):
                # Submit ready nodes
                for node in graph.nodes:
                    if self.execution_queue.get_state(node) != TaskState.PENDING:
                        continue

                    # Check prerequisites
                    prereqs = graph.dependencies.get(node, set())
                    if prereqs.issubset(completed_nodes):
                        self.execution_queue.set_state(node, TaskState.READY)
                        self.event_bus.publish_sync(
                            Event(
                                name="scheduler.task_scheduled",
                                category="Scheduler",
                                source="DependencySchedulerManager",
                                payload={"task_id": node},
                            )
                        )

                        func = tasks_map.get(node)
                        if not func:
                            raise DependencySchedulerError(
                                f"No callable task registered for node '{node}'."
                            )

                        # Submit to executor pool
                        self.execution_queue.set_state(node, TaskState.RUNNING)
                        self.event_bus.publish_sync(
                            Event(
                                name="scheduler.task_started",
                                category="Scheduler",
                                source="DependencySchedulerManager",
                                payload={"task_id": node},
                            )
                        )

                        assert self.worker_pool.executor is not None
                        future = self.worker_pool.executor.submit(func)
                        active_futures[future] = node

                if not active_futures:
                    # Check for deadlocks/stalls
                    pending = [
                        n
                        for n in graph.nodes
                        if self.execution_queue.get_state(n) == TaskState.PENDING
                    ]
                    if pending:
                        raise DependencySchedulerError(
                            f"Scheduler deadlock detected. Pending nodes: {pending}"
                        )
                    break

                # Wait for at least one task completion iteration step
                for future in as_completed(active_futures, timeout=30.0):
                    node = active_futures.pop(future)
                    try:
                        res = future.result()
                        results[node] = res
                        self.execution_queue.set_state(node, TaskState.COMPLETED)
                        completed_nodes.add(node)

                        self.event_bus.publish_sync(
                            Event(
                                name="scheduler.task_completed",
                                category="Scheduler",
                                source="DependencySchedulerManager",
                                payload={"task_id": node},
                            )
                        )
                    except Exception as ex:
                        self.execution_queue.set_state(node, TaskState.FAILED)
                        self.event_bus.publish_sync(
                            Event(
                                name="scheduler.task_failed",
                                category="Scheduler",
                                source="DependencySchedulerManager",
                                payload={"task_id": node},
                            )
                        )
                        raise DependencySchedulerError(
                            f"Task node '{node}' failed in execution: {ex!s}"
                        ) from ex
                    break
        finally:
            self.worker_pool.shutdown()

        self.event_bus.publish_sync(
            Event(
                name="scheduler.workflow_continued",
                category="Scheduler",
                source="DependencySchedulerManager",
                payload={},
            )
        )

        return results
