"""Global Resource Discovery, Registry & Topology Intelligence Platform for AIRA.

Provides discovery engines, topology builders, global registries, and health monitors.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.global_resource_discovery")


class GlobalResourceDiscoveryError(Exception):
    """Base exception raised for discovery failures or invalid transitions."""

    pass


@dataclass
class ResourceDescriptor:
    """Descriptor representing execution node hardware profiles and capabilities."""

    resource_id: str
    resource_type: str  # Local, On-Prem, Private, Public, Cluster, Simulation
    region: str
    availability_zone: str
    capabilities: list[str]
    hardware_profile: dict[str, Any] = field(default_factory=dict)
    health_status: str = "Healthy"  # Healthy, Degraded, Unreachable
    trust_level: str = "Trusted"
    compliance_region: str = "US"
    metadata: dict[str, Any] = field(default_factory=dict)
    version: int = 1
    lifecycle_state: str = "Discovered"  # Discovered, Validated, Registered, Available, Maintenance


class DiscoveryEngine:
    """Discovers compute, storage, and accelerator resources, formulating descriptors."""

    def discover_node(
        self, resource_id: str, node_type: str, caps: list[str]
    ) -> ResourceDescriptor:
        """Formulate a new ResourceDescriptor in Discovered state."""
        if not resource_id:
            raise GlobalResourceDiscoveryError("Discovery failed: Resource ID is required.")

        return ResourceDescriptor(
            resource_id=resource_id,
            resource_type=node_type,
            region="us-west-2",
            availability_zone="us-west-2a",
            capabilities=caps,
            hardware_profile={"cpu_cores": 16, "accelerator": "TPU-v5"},
        )


class TopologyBuilder:
    """Builds and maintains parent-child infrastructure topology structures maps."""

    def __init__(self) -> None:
        self.relationships: dict[str, str] = {}

    def link_node_to_parent(self, node_id: str, parent_id: str) -> None:
        """Map structural node parent links."""
        self.relationships[node_id] = parent_id


class GlobalRegistry:
    """Validates metadata profiles and manages state transitions checks."""

    def __init__(self) -> None:
        self.resources: dict[str, ResourceDescriptor] = {}

    def save_resource(self, descriptor: ResourceDescriptor) -> None:
        """Catalog resource."""
        self.resources[descriptor.resource_id] = descriptor

    def transition_state(self, resource_id: str, to_state: str) -> None:
        """Update lifecycle state checking allowed boundary values."""
        descriptor = self.resources.get(resource_id)
        if not descriptor:
            raise GlobalResourceDiscoveryError(
                f"Transition failed: Resource '{resource_id}' not found."
            )

        allowed = {"Discovered", "Validated", "Registered", "Available", "Maintenance", "Retired"}
        if to_state not in allowed:
            raise GlobalResourceDiscoveryError(
                f"Transition failed: Status state '{to_state}' is not supported."
            )

        # Enforce rule: cannot transition to Available if health status is Degraded
        if to_state == "Available" and descriptor.health_status == "Degraded":
            raise GlobalResourceDiscoveryError(
                f"Transition to Available rejected: Resource '{resource_id}' health is Degraded."
            )

        descriptor.lifecycle_state = to_state


class CapabilityCatalog:
    """Maintains active capability indexes mapping capability tags."""

    def __init__(self) -> None:
        self.catalog: dict[str, list[str]] = {}

    def update_catalog(self, resource_id: str, capabilities: list[str]) -> None:
        """Map capability tags."""
        self.catalog[resource_id] = capabilities


class HealthMonitor:
    """Tracks heartbeats indicators and triggers maintenance routines on expirations."""

    def evaluate_heartbeat(self, descriptor: ResourceDescriptor, has_heartbeat: bool) -> None:
        """Update health tags on heartbeat status loss."""
        if not has_heartbeat:
            descriptor.health_status = "Degraded"
        else:
            descriptor.health_status = "Healthy"


class GlobalResourceDiscoveryManager:
    """Coordinating manager resolving discovery steps, registry databases, and events."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.discovery_engine = DiscoveryEngine()
        self.topology_builder = TopologyBuilder()
        self.global_registry = GlobalRegistry()
        self.capability_catalog = CapabilityCatalog()
        self.health_monitor = HealthMonitor()

    def discover_and_catalog(
        self, resource_id: str, node_type: str, caps: list[str], parent_cluster: str
    ) -> ResourceDescriptor:
        """Run discovery flow, validate state, map topology, and catalog capability indexes."""
        # 1. Discover
        desc = self.discovery_engine.discover_node(resource_id, node_type, caps)
        self.global_registry.save_resource(desc)

        self.event_bus.publish_sync(
            Event(
                name="resource.discovered",
                category="GlobalResourceDiscovery",
                source="GlobalResourceDiscoveryManager",
                payload={"resource_id": resource_id, "type": node_type},
            )
        )

        # 2. Promote state to Registered
        self.global_registry.transition_state(resource_id, "Registered")

        self.event_bus.publish_sync(
            Event(
                name="resource.registered",
                category="GlobalResourceDiscovery",
                source="GlobalResourceDiscoveryManager",
                payload={"resource_id": resource_id},
            )
        )

        # 3. Topology Link
        self.topology_builder.link_node_to_parent(resource_id, parent_cluster)

        self.event_bus.publish_sync(
            Event(
                name="topology.updated",
                category="GlobalResourceDiscovery",
                source="GlobalResourceDiscoveryManager",
                payload={"resource_id": resource_id, "parent": parent_cluster},
            )
        )

        # 4. Capability Catalog index update
        self.capability_catalog.update_catalog(resource_id, caps)

        self.event_bus.publish_sync(
            Event(
                name="capability.catalog.updated",
                category="GlobalResourceDiscovery",
                source="GlobalResourceDiscoveryManager",
                payload={"resource_id": resource_id, "capabilities": caps},
            )
        )

        return desc

    def evaluate_node_health(self, resource_id: str, has_heartbeat: bool) -> None:
        """Evaluate heartbeat status, degrade status if expired, and archive transitions."""
        desc = self.global_registry.resources.get(resource_id)
        if not desc:
            raise GlobalResourceDiscoveryError(
                f"Operation failed: Resource '{resource_id}' not found."
            )

        # Evaluate
        self.health_monitor.evaluate_heartbeat(desc, has_heartbeat)

        self.event_bus.publish_sync(
            Event(
                name="health.updated",
                category="GlobalResourceDiscovery",
                source="GlobalResourceDiscoveryManager",
                payload={"resource_id": resource_id, "health": desc.health_status},
            )
        )

        # Degraded triggers Maintenance state promotion
        if desc.health_status == "Degraded":
            self.global_registry.transition_state(resource_id, "Maintenance")
