"""Enterprise AI Cloud, Federated Runtime Foundation & Global Control Plane for AIRA.

Provides runtime registries, federation policies, discovery engines, and health monitors.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.federated_runtime")


class FederationPlatformError(Exception):
    """Base exception raised for registration failures, policy violations, or health drifts."""

    pass


@dataclass
class RuntimeDescriptor:
    """Descriptor layout representing regional runtime capabilities and policies."""

    runtime_id: str
    organization: str
    region: str
    deployment_type: str  # Regional Federation, Cloud Federation, Private Cloud, Public Cloud, Edge
    capabilities: list[str]
    api_version: str
    # Policies: Connected, Restricted, Isolated, Trusted, Read-Only, Emergency Mode
    federation_policy: str = "Connected"
    trust_level: str = "Low"
    health: str = "Healthy"
    version: str = "1.0.0"
    metadata: dict[str, Any] = field(default_factory=dict)


class GlobalRuntimeRegistry:
    """Maintains active federated runtimes descriptors inventory."""

    def __init__(self) -> None:
        self.runtimes: dict[str, RuntimeDescriptor] = {}

    def register_runtime(self, descriptor: RuntimeDescriptor) -> None:
        """Save runtime descriptor context."""
        self.runtimes[descriptor.runtime_id] = descriptor


class RuntimeDiscoveryService:
    """Enables discovery of compatible runtimes based on capabilities and compatibility."""

    def discover_runtimes(
        self, registry: GlobalRuntimeRegistry, required_capability: str, target_version: str
    ) -> list[RuntimeDescriptor]:
        """Find compatible runtimes that match required criteria."""
        return [
            rt
            for rt in registry.runtimes.values()
            if required_capability in rt.capabilities and rt.api_version == target_version
        ]


class FederationPolicyManager:
    """Enforces policy state machine transitions and gates access rules."""

    def transition_policy(self, rt: RuntimeDescriptor, next_policy: str) -> None:
        """Validate policy changes sequence constraints."""
        current = rt.federation_policy

        allowed = {
            "Connected": {"Restricted", "Isolated", "Emergency Mode"},
            "Restricted": {"Connected", "Isolated", "Emergency Mode"},
            "Isolated": {"Connected", "Restricted", "Emergency Mode"},
            "Trusted": {"Connected", "Restricted", "Isolated", "Emergency Mode"},
            "Read-Only": {"Connected", "Restricted", "Isolated", "Emergency Mode"},
            "Emergency Mode": {"Connected", "Restricted", "Isolated"},
        }

        # Handle initialization or direct transition validation check
        if next_policy not in allowed.get(current, set()) and current != next_policy:
            raise FederationPlatformError(
                f"Policy transition rejected: Cannot transition runtime '{rt.runtime_id}' "
                f"from policy '{current}' to '{next_policy}'."
            )

        rt.federation_policy = next_policy


class FederationHealthMonitor:
    """Tracks availability metrics and adjusts routing traffic metadata on failure."""

    def __init__(self) -> None:
        self.health_history: dict[str, list[str]] = {}

    def record_health(self, runtime_id: str, status: str) -> None:
        """Append health check trace log."""
        self.health_history.setdefault(runtime_id, []).append(status)


class FederationLayer:
    """Establishes relationship contracts and checks compatibility versions."""

    def establish_connection(
        self, local_version: str, remote_descriptor: RuntimeDescriptor
    ) -> bool:
        """Raise error if API version mismatch triggers compatibility gaps."""
        if remote_descriptor.api_version != local_version:
            raise FederationPlatformError(
                f"Federation rejected: Version mismatch. Local is '{local_version}', "
                f"remote is '{remote_descriptor.api_version}'."
            )
        return True


class GlobalControlPlane:
    """Coordinating control plane managing global registry and policy updates."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.global_registry = GlobalRuntimeRegistry()
        self.discovery = RuntimeDiscoveryService()
        self.policy_manager = FederationPolicyManager()
        self.health_monitor = FederationHealthMonitor()
        self.federation_layer = FederationLayer()

    def register_federated_runtime(
        self,
        runtime_id: str,
        organization: str,
        region: str,
        deployment_type: str,
        capabilities: list[str],
        api_version: str,
    ) -> RuntimeDescriptor:
        """Validate descriptor details, register runtime context, and publish events."""
        # Simple descriptor format check
        if not runtime_id or not region:
            raise FederationPlatformError(
                "Registration failed: Runtime descriptors must specify runtime_id and region."
            )

        descriptor = RuntimeDescriptor(
            runtime_id=runtime_id,
            organization=organization,
            region=region,
            deployment_type=deployment_type,
            capabilities=capabilities,
            api_version=api_version,
        )

        self.global_registry.register_runtime(descriptor)

        self.event_bus.publish_sync(
            Event(
                name="federation.runtime.registered",
                category="FederationPlatform",
                source="GlobalControlPlane",
                payload={"runtime_id": runtime_id},
            )
        )

        # Publish initial capabilities
        for cap in capabilities:
            self.event_bus.publish_sync(
                Event(
                    name="federation.capability.published",
                    category="FederationPlatform",
                    source="GlobalControlPlane",
                    payload={"runtime_id": runtime_id, "capability": cap},
                )
            )

        return descriptor

    def connect_runtime(self, local_version: str, runtime_id: str) -> None:
        """Establish governed relationship and publish events."""
        rt = self.global_registry.runtimes.get(runtime_id)
        if not rt:
            raise FederationPlatformError(f"Runtime descriptor not found: '{runtime_id}'")

        # Verify version compatibility
        self.federation_layer.establish_connection(local_version, rt)

        self.event_bus.publish_sync(
            Event(
                name="federation.established",
                category="FederationPlatform",
                source="GlobalControlPlane",
                payload={"runtime_id": runtime_id},
            )
        )

    def update_runtime_policy(self, runtime_id: str, next_policy: str) -> None:
        """Advance policy state and publish events."""
        rt = self.global_registry.runtimes.get(runtime_id)
        if not rt:
            raise FederationPlatformError(f"Runtime descriptor not found: '{runtime_id}'")

        self.policy_manager.transition_policy(rt, next_policy)

        self.event_bus.publish_sync(
            Event(
                name="federation.policy.updated",
                category="FederationPlatform",
                source="GlobalControlPlane",
                payload={"runtime_id": runtime_id, "policy": next_policy},
            )
        )

    def update_runtime_health(self, runtime_id: str, status: str) -> None:
        """Scan health state, update descriptor metrics, and publish events."""
        rt = self.global_registry.runtimes.get(runtime_id)
        if not rt:
            raise FederationPlatformError(f"Runtime descriptor not found: '{runtime_id}'")

        old_health = rt.health
        rt.health = status
        self.health_monitor.record_health(runtime_id, status)

        if old_health != status:
            self.event_bus.publish_sync(
                Event(
                    name="federation.health.changed",
                    category="FederationPlatform",
                    source="GlobalControlPlane",
                    payload={"runtime_id": runtime_id, "health": status},
                )
            )
