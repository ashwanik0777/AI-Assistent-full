"""Enterprise Multi-Region Deployment, Global Routing & Intelligent Traffic Platform for AIRA.

Provides routing policy engines, region selectors, failover managers, and topology managers.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.global_routing")


class RoutingPlatformError(Exception):
    """Base exception raised for routing failures, policy drifts, or failover violations."""

    pass


@dataclass
class GlobalRoutingDescriptor:
    """Descriptor layout specifying route attributes, compliance limits, and latency profiles."""

    route_id: str
    source_region: str
    target_region: str
    # Policies: Policy-Based, Latency-Aware, Capacity-Aware
    # Trust-Aware, Compliance-Aware, Emergency
    routing_policy: str
    priority: int = 1
    compliance_constraints: list[str] = field(default_factory=list)
    latency_profile: dict[str, Any] = field(default_factory=dict)
    availability: float = 1.0
    version: str = "1.0.0"
    metadata: dict[str, Any] = field(default_factory=dict)


class GlobalTopologyManager:
    """Tracks known regional connections nodes and active failover chains configurations."""

    def __init__(self) -> None:
        self.regions: dict[str, dict[str, Any]] = {}
        self.failover_chains: dict[str, list[str]] = {}

    def register_region(self, region_id: str, status: str = "Online") -> None:
        """Save regional node status details."""
        self.regions[region_id] = {"status": status}

    def configure_failover(self, primary: str, secondary: str) -> None:
        """Register failover target link."""
        self.failover_chains[primary] = [secondary]


class CapacityAwarenessService:
    """Tracks regional load indexes and active requests workload capacity bounds."""

    def __init__(self) -> None:
        self.capacity_indices: dict[str, float] = {}

    def set_load_index(self, region_id: str, load_index: float) -> None:
        """Update current load index for target region."""
        self.capacity_indices[region_id] = load_index


class RoutingPolicyEngine:
    """Evaluates routing strategies matching compliance or trust policy constraints."""

    def evaluate_route(
        self, descriptor: GlobalRoutingDescriptor, required_compliance: str, max_latency_ms: int
    ) -> bool:
        """Assert compliance constraints and latency boundaries."""
        # 1. Compliance constraint gate
        if required_compliance not in descriptor.compliance_constraints:
            return False

        # 2. Latency profile gate
        latency = int(descriptor.latency_profile.get("latency_ms", 999))
        return latency <= max_latency_ms


class FailoverManager:
    """Manages multi-region backup rerouting chains and automatic path recalculations."""

    def find_fallback_region(self, primary_region: str, topology: GlobalTopologyManager) -> str:
        """Resolve backup route target if primary node is unavailable."""
        chain = topology.failover_chains.get(primary_region, [])
        for fallback in chain:
            status = topology.regions.get(fallback, {}).get("status", "Offline")
            if status == "Online":
                return fallback

        raise RoutingPlatformError(
            f"Failover failed: No available backup regions configured for '{primary_region}'."
        )


class RegionSelector:
    """Filters eligible nodes list using policy evaluation constraints."""

    def select_region(
        self,
        engine: RoutingPolicyEngine,
        routes: list[GlobalRoutingDescriptor],
        required_compliance: str,
        max_latency_ms: int,
    ) -> str:
        """Search routes list and select the target region."""
        for route in routes:
            if engine.evaluate_route(route, required_compliance, max_latency_ms):
                return route.target_region

        raise RoutingPlatformError("Region selection failed: No eligible target region found.")


class GlobalRoutingGateway:
    """Coordinating routing gateway orchestrating selections, failovers, and topology queries."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.topology = GlobalTopologyManager()
        self.capacity_service = CapacityAwarenessService()
        self.policy_engine = RoutingPolicyEngine()
        self.failover_manager = FailoverManager()
        self.region_selector = RegionSelector()

        self.routes: dict[str, GlobalRoutingDescriptor] = {}

    def register_route(
        self,
        route_id: str,
        source_region: str,
        target_region: str,
        routing_policy: str,
        compliance_constraints: list[str],
        latency_profile: dict[str, Any],
    ) -> GlobalRoutingDescriptor:
        """Initialize route descriptor and publish events."""
        desc = GlobalRoutingDescriptor(
            route_id=route_id,
            source_region=source_region,
            target_region=target_region,
            routing_policy=routing_policy,
            compliance_constraints=compliance_constraints,
            latency_profile=latency_profile,
        )

        self.routes[route_id] = desc

        self.event_bus.publish_sync(
            Event(
                name="routing.route.created",
                category="GlobalRouting",
                source="GlobalRoutingGateway",
                payload={"route_id": route_id},
            )
        )

        return desc

    def update_region_load(self, region_id: str, load_index: float) -> None:
        """Update region load capacity indexes and publish events."""
        self.capacity_service.set_load_index(region_id, load_index)

        self.event_bus.publish_sync(
            Event(
                name="routing.capacity.updated",
                category="GlobalRouting",
                source="GlobalRoutingGateway",
                payload={"region_id": region_id, "load_index": load_index},
            )
        )

    def route_request(
        self, source_region: str, required_compliance: str, max_latency_ms: int
    ) -> str:
        """Evaluate policies list, select best node, handle failovers, and publish events."""
        # Query active routes matching source region
        active_routes = [r for r in self.routes.values() if r.source_region == source_region]

        try:
            target = self.region_selector.select_region(
                self.policy_engine, active_routes, required_compliance, max_latency_ms
            )

            # Assert node availability state
            status = self.topology.regions.get(target, {}).get("status", "Online")
            if status != "Online":
                # Trigger failover
                self.event_bus.publish_sync(
                    Event(
                        name="routing.failover.triggered",
                        category="GlobalRouting",
                        source="GlobalRoutingGateway",
                        payload={"unavailable_region": target},
                    )
                )

                fallback = self.failover_manager.find_fallback_region(target, self.topology)
                target = fallback

            self.event_bus.publish_sync(
                Event(
                    name="routing.region.selected",
                    category="GlobalRouting",
                    source="GlobalRoutingGateway",
                    payload={"selected_region": target},
                )
            )

            self.event_bus.publish_sync(
                Event(
                    name="routing.policy.applied",
                    category="GlobalRouting",
                    source="GlobalRoutingGateway",
                    payload={"policy": "Compliance-Aware"},
                )
            )

            return target

        except Exception as e:
            logger.error("Routing execution failed", error=str(e))
            raise RoutingPlatformError(f"Request routing failed: {e}") from e
