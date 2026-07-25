"""Enterprise Distributed Execution Platform & Remote Runtime for AIRA.

Provides provider contracts, registries, schedulers, health monitors, and failover managers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.distributed_execution")


class DistributedExecutionError(Exception):
    """Base exception raised for scheduling issues, provider offline failures, or failovers."""

    pass


@dataclass
class ProviderManifest:
    """Configuration detailing capabilities target ranges and health status flags."""

    provider_id: str
    provider_type: str  # Local, Remote, Cloud, Edge
    supported_capabilities: list[str]
    resource_limits: dict[str, Any] = field(default_factory=dict)
    health_status: str = "Healthy"
    trust_level: float = 5.0
    compatibility: str = ">=0.9.0"
    metadata: dict[str, Any] = field(default_factory=dict)
    version: str = "1.0.0"


@dataclass
class ExecutionSession:
    """Active session metadata details mapping checkpoints."""

    session_id: str
    provider_id: str
    status: str = "Running"
    execution_metadata: dict[str, Any] = field(default_factory=dict)


class ExecutionProviderInterface(ABC):
    """Lifecycle interface that interchangeable execution runtimes must implement."""

    def __init__(self, manifest: ProviderManifest) -> None:
        self.manifest = manifest

    @abstractmethod
    def execute_workload(self, workload: dict[str, Any]) -> dict[str, Any]:
        """Perform operations E2E."""
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Return True if the provider is healthy."""
        pass


class ProviderRegistry:
    """Manages active registered provider records."""

    def __init__(self) -> None:
        self.providers: dict[str, ProviderManifest] = {}

    def register_provider(self, manifest: ProviderManifest) -> None:
        """Add record entry."""
        self.providers[manifest.provider_id] = manifest

    def get_provider(self, provider_id: str) -> ProviderManifest | None:
        """Fetch record properties."""
        return self.providers.get(provider_id)


class ProviderScheduler:
    """Resolves target providers based on capability demands, health, and trust constraints."""

    def schedule_workload(self, required_caps: list[str], registry: ProviderRegistry) -> str:
        """Find the healthiest provider matching requirements."""
        for provider in registry.providers.values():
            if provider.health_status != "Healthy":
                continue
            matches_all = all(c in provider.supported_capabilities for c in required_caps)
            if matches_all:
                return provider.provider_id

        raise DistributedExecutionError(
            f"Scheduling failed: No healthy provider supports capabilities: {required_caps}."
        )


class DistributedSessionManager:
    """Tracks active workloads checkpoint states."""

    def __init__(self) -> None:
        self.sessions: dict[str, ExecutionSession] = {}

    def start_session(self, session_id: str, provider_id: str) -> ExecutionSession:
        """Save a new session registry entry."""
        sess = ExecutionSession(session_id=session_id, provider_id=provider_id)
        self.sessions[session_id] = sess
        return sess

    def get_session(self, session_id: str) -> ExecutionSession | None:
        """Fetch session registry properties."""
        return self.sessions.get(session_id)


class ProviderHealthMonitor:
    """Monitors heartbeat stats and updates health fields flags."""

    def record_heartbeat(self, manifest: ProviderManifest, status: str) -> None:
        """Update active record parameters status."""
        manifest.health_status = status


class FailoverManager:
    """Orchestrates checkpoint migrations upon provider failures."""

    def perform_failover(
        self,
        session: ExecutionSession,
        registry: ProviderRegistry,
        scheduler: ProviderScheduler,
        required_caps: list[str],
    ) -> str:
        """Identify backup and resume session."""
        # 1. Evict failed provider from selections
        failed_id = session.provider_id
        manifest = registry.get_provider(failed_id)
        if manifest:
            manifest.health_status = "Unhealthy"

        # 2. Reschedule
        backup_id = scheduler.schedule_workload(required_caps, registry)
        session.provider_id = backup_id
        session.status = "Resumed"
        return backup_id


class DistributedExecutionManager:
    """Coordinating manager verifying execution pipelines and executing failovers."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.provider_registry = ProviderRegistry()
        self.scheduler = ProviderScheduler()
        self.session_manager = DistributedSessionManager()
        self.health_monitor = ProviderHealthMonitor()
        self.failover_manager = FailoverManager()

    def register_provider(self, manifest: ProviderManifest) -> None:
        """Register provider profiles and notify bus events."""
        self.provider_registry.register_provider(manifest)
        self.event_bus.publish_sync(
            Event(
                name="provider.registered",
                category="DistributedExecution",
                source="DistributedExecutionManager",
                payload={
                    "provider_id": manifest.provider_id,
                    "provider_type": manifest.provider_type,
                },
            )
        )

    def initiate_session(self, session_id: str, required_caps: list[str]) -> ExecutionSession:
        """Schedule workload, start checkpoint track session, and publish events."""
        provider_id = self.scheduler.schedule_workload(required_caps, self.provider_registry)
        self.event_bus.publish_sync(
            Event(
                name="provider.selected",
                category="DistributedExecution",
                source="DistributedExecutionManager",
                payload={"provider_id": provider_id, "session_id": session_id},
            )
        )

        sess = self.session_manager.start_session(session_id, provider_id)
        self.event_bus.publish_sync(
            Event(
                name="session.started",
                category="DistributedExecution",
                source="DistributedExecutionManager",
                payload={"session_id": session_id, "provider_id": provider_id},
            )
        )
        return sess

    def handle_provider_failure(self, session_id: str, required_caps: list[str]) -> None:
        """Mark provider failed, trigger failover migrations, and resume execution."""
        sess = self.session_manager.get_session(session_id)
        if not sess:
            raise DistributedExecutionError(f"Failure failed: Session '{session_id}' not found.")

        old_id = sess.provider_id
        self.event_bus.publish_sync(
            Event(
                name="provider.failed",
                category="DistributedExecution",
                source="DistributedExecutionManager",
                payload={"provider_id": old_id},
            )
        )

        self.event_bus.publish_sync(
            Event(
                name="failover.triggered",
                category="DistributedExecution",
                source="DistributedExecutionManager",
                payload={"session_id": session_id, "failed_provider_id": old_id},
            )
        )

        new_id = self.failover_manager.perform_failover(
            sess, self.provider_registry, self.scheduler, required_caps
        )

        self.event_bus.publish_sync(
            Event(
                name="session.resumed",
                category="DistributedExecution",
                source="DistributedExecutionManager",
                payload={"session_id": session_id, "new_provider_id": new_id},
            )
        )
