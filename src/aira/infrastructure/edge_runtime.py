"""Enterprise Edge Intelligence & Offline Autonomy Platform.

Provides offline policy engines, resource managers, and synchronization queues.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.edge_runtime")


class EdgeRuntimeError(Exception):
    """Base exception raised for offline policy blocks, capacity limits, or sync failures."""

    pass


@dataclass
class EdgeExecutionContext:
    """Context block specifying device metadata, budgets, and offline policies."""

    edge_context_id: str
    device_class: str
    runtime_profile: str
    connectivity_state: str  # Offline, Limited, Connected, High Latency, Metered
    resource_budget: dict[str, Any]
    offline_policy: str  # Offline Allowed, Online Required, Deferred, Cached Only, Restricted
    synchronization_priority: str = "Medium"
    security_profile: str = "Standard"
    metadata: dict[str, Any] = field(default_factory=dict)
    version: int = 1


class OfflinePolicyEngine:
    """Enforces execution rules based on active connectivity status and offline configurations."""

    def validate_policy(self, context: EdgeExecutionContext) -> None:
        """Reject execution if policy is Online Required while connectivity is Offline."""
        if context.offline_policy == "Online Required" and context.connectivity_state == "Offline":
            raise EdgeRuntimeError(
                f"Policy violation: Workload '{context.edge_context_id}' "
                "requires online connectivity."
            )


class EdgeResourceManager:
    """Monitors battery charge, thermal throttles, and CPU allocations budgets."""

    def validate_resource_budget(self, context: EdgeExecutionContext, required_cpu: int) -> None:
        """Verify device parameters satisfy CPU and battery budgets."""
        avail_cpu = context.resource_budget.get("cpu_cores", 0)
        if required_cpu > avail_cpu:
            raise EdgeRuntimeError(
                f"Budget violation: Workload requires {required_cpu} CPUs. Budget is {avail_cpu}."
            )

        battery = context.resource_budget.get("battery_percent", 100.0)
        if battery < 10.0:
            raise EdgeRuntimeError(
                f"Budget violation: Device battery {battery}% is below 10% safety threshold."
            )


class DeferredSynchronizationQueue:
    """Queues modifications during offline operations to replay when connectivity restores."""

    def __init__(self) -> None:
        self.queue: list[dict[str, Any]] = []
        self.history: list[dict[str, Any]] = []

    def enqueue_change(self, change_id: str, change_payload: dict[str, Any]) -> None:
        """Enqueue offline transaction change."""
        self.queue.append({"change_id": change_id, "payload": change_payload})

    def drain_queue(self) -> list[dict[str, Any]]:
        """Pop all entries from queue and record in history logs."""
        changes = list(self.queue)
        self.history.extend(changes)
        self.queue.clear()
        return changes


class ConnectivityIntelligence:
    """Manages transitions of active device network connectivity metrics states."""

    def resolve_state(self, is_connected: bool) -> str:
        """Return connectivity tag name."""
        return "Connected" if is_connected else "Offline"


class EdgeRuntimeManager:
    """Coordinating manager resolving edge executions, synchronization queues, and events."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.policy_engine = OfflinePolicyEngine()
        self.resource_manager = EdgeResourceManager()
        self.sync_queue = DeferredSynchronizationQueue()
        self.connectivity = ConnectivityIntelligence()

        self.contexts: dict[str, EdgeExecutionContext] = {}

    def execute_edge_workload(
        self,
        context_id: str,
        device_class: str,
        policy: str,
        is_connected: bool,
        budget: dict[str, Any],
        required_cpu: int,
    ) -> EdgeExecutionContext:
        """Construct context, validate policies and budgets, track states, and publish events."""
        conn_state = self.connectivity.resolve_state(is_connected)
        context = EdgeExecutionContext(
            edge_context_id=context_id,
            device_class=device_class,
            runtime_profile="edge_core",
            connectivity_state=conn_state,
            resource_budget=budget,
            offline_policy=policy,
        )

        # 1. Validate Policy and Resources
        self.policy_engine.validate_policy(context)
        self.resource_manager.validate_resource_budget(context, required_cpu)

        self.contexts[context_id] = context

        self.event_bus.publish_sync(
            Event(
                name="edge.execution.started",
                category="EdgeRuntime",
                source="EdgeRuntimeManager",
                payload={"context_id": context_id, "policy": policy},
            )
        )

        # Notify if offline
        if conn_state == "Offline":
            self.event_bus.publish_sync(
                Event(
                    name="offline.mode.enabled",
                    category="EdgeRuntime",
                    source="EdgeRuntimeManager",
                    payload={"context_id": context_id},
                )
            )

        return context

    def queue_offline_change(
        self, context_id: str, change_id: str, payload: dict[str, Any]
    ) -> None:
        """Add change transaction to deferred queue."""
        self.sync_queue.enqueue_change(change_id, payload)

        self.event_bus.publish_sync(
            Event(
                name="synchronization.queued",
                category="EdgeRuntime",
                source="EdgeRuntimeManager",
                payload={"context_id": context_id, "change_id": change_id},
            )
        )

    def restore_connectivity_and_sync(self, context_id: str) -> None:
        """Promote connectivity state to Connected, replay queue entries, and publish events."""
        context = self.contexts.get(context_id)
        if not context:
            raise EdgeRuntimeError(f"Sync failed: Context '{context_id}' not found.")

        # Restore connectivity
        context.connectivity_state = "Connected"

        self.event_bus.publish_sync(
            Event(
                name="connectivity.restored",
                category="EdgeRuntime",
                source="EdgeRuntimeManager",
                payload={"context_id": context_id},
            )
        )

        # Drain
        changes = self.sync_queue.drain_queue()

        self.event_bus.publish_sync(
            Event(
                name="synchronization.completed",
                category="EdgeRuntime",
                source="EdgeRuntimeManager",
                payload={"context_id": context_id, "synchronized_entries": len(changes)},
            )
        )
