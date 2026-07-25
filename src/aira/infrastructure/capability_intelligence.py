"""Enterprise Capability Intelligence, Composition & Recommendation Platform for AIRA.

Provides capability discoverers, composite builders, gap analyzers, and recommendation lifecycles.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.capability_intelligence")


class CapabilityIntelligenceError(Exception):
    """Base exception raised for composition or invalid lifecycle changes failures."""

    pass


@dataclass
class CapabilityRecommendation:
    """Recommendation record specifying suggested capability upgrades for target goals."""

    recommendation_id: str
    target_goal: str
    required_capabilities: list[str]
    available_capabilities: list[str]
    capability_gaps: list[str]
    suggested_extensions: list[str]
    suggested_knowledge_packs: list[str]
    expected_impact: str
    confidence: float
    # Discovered, Validated, Recommended, Approved, Installed, Deprecated, Archived
    approval_status: str = "Discovered"
    version: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)


class CapabilityDiscoveryEngine:
    """Discovers and catalogs active capabilities from registry/engine mappings."""

    def __init__(self, registry: ServiceRegistry) -> None:
        self.registry = registry

    def discover_capabilities(self) -> list[str]:
        """Query CapabilityEngine if registered and return list of active capability IDs."""
        try:
            engine = self.registry.get_service("CapabilityEngine")
        except Exception:
            engine = None

        has_registry = hasattr(engine, "registry")
        has_caps = hasattr(engine.registry, "active_capabilities") if has_registry else False  # type: ignore
        if engine and has_registry and has_caps:
            return list(engine.registry.active_capabilities.keys())  # type: ignore

        # Fallback catalog stubs
        return ["Browser", "Vision", "Memory", "FileSystem"]


class CompositionEngine:
    """Combines individual capabilities into composite reusable bundles."""

    def compose_bundle(self, bundle_name: str, capabilities: list[str]) -> dict[str, Any]:
        """Package capabilities list into a composite bundle record."""
        if not bundle_name or not capabilities:
            raise CapabilityIntelligenceError(
                "Composition failed: Bundle name and non-empty capabilities list are required."
            )
        return {
            "bundle_id": f"bundle_{bundle_name.lower().replace(' ', '_')}",
            "bundle_name": bundle_name,
            "composed_capabilities": capabilities.copy(),
        }


class GapAnalyzer:
    """Evaluates required lists against available catalogs to identify missing requirements."""

    def analyze_gaps(self, required: list[str], available: list[str]) -> list[str]:
        """Compare lists and return list of missing capability IDs."""
        return [c for c in required if c not in available]


class CapabilityLifecycleManager:
    """Coordinates lifecycle transitions and prevents invalid workflow paths."""

    def __init__(self) -> None:
        self.recommendations: dict[str, CapabilityRecommendation] = {}

    def save_recommendation(self, rec: CapabilityRecommendation) -> None:
        """Catalog recommendation record."""
        self.recommendations[rec.recommendation_id] = rec

    def transition_lifecycle(self, recommendation_id: str, to_state: str) -> None:
        """Move recommendation status to target lifecycle state and check compatibility."""
        rec = self.recommendations.get(recommendation_id)
        if not rec:
            raise CapabilityIntelligenceError(
                f"Transition failed: Recommendation '{recommendation_id}' not found."
            )

        allowed = {
            "Discovered",
            "Validated",
            "Recommended",
            "Approved",
            "Installed",
            "Deprecated",
            "Archived",
        }
        if to_state not in allowed:
            raise CapabilityIntelligenceError(
                f"Transition failed: Lifecycle state '{to_state}' is not supported."
            )

        # Enforce rule: cannot approve a recommendation with large gaps (advisory safety limit)
        if to_state == "Approved" and rec.capability_gaps:
            raise CapabilityIntelligenceError(
                f"Approval rejected: Recommendation '{recommendation_id}' has unresolved gaps: "
                f"{rec.capability_gaps}"
            )

        rec.approval_status = to_state


class CapabilityIntelligenceManager:
    """Coordinating manager running discoveries and managing lifecycles."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.discovery = CapabilityDiscoveryEngine(registry)
        self.composition = CompositionEngine()
        self.gap_analyzer = GapAnalyzer()
        self.lifecycle = CapabilityLifecycleManager()

    def discover_and_analyze(
        self, recommendation_id: str, target_goal: str, required: list[str]
    ) -> CapabilityRecommendation:
        """Discover active capabilities, identify gaps, and create recommended updates."""
        available = self.discovery.discover_capabilities()

        # Publish discovery event for each capability discovered
        for cap in available:
            self.event_bus.publish_sync(
                Event(
                    name="capability.discovered",
                    category="CapabilityIntelligence",
                    source="CapabilityIntelligenceManager",
                    payload={"capability_id": cap},
                )
            )

        # Check gaps
        gaps = self.gap_analyzer.analyze_gaps(required, available)
        if gaps:
            self.event_bus.publish_sync(
                Event(
                    name="gap.identified",
                    category="CapabilityIntelligence",
                    source="CapabilityIntelligenceManager",
                    payload={"target_goal": target_goal, "gaps": gaps},
                )
            )

        # Suggest updates based on gaps
        suggested_ext = []
        suggested_kp = []
        if "SecurityScanner" in gaps:
            suggested_ext.append("SecurityScannerExtension")
            suggested_kp.append("SecurityAuditKnowledgePack")

        rec = CapabilityRecommendation(
            recommendation_id=recommendation_id,
            target_goal=target_goal,
            required_capabilities=required,
            available_capabilities=available,
            capability_gaps=gaps,
            suggested_extensions=suggested_ext,
            suggested_knowledge_packs=suggested_kp,
            expected_impact="High optimization of target execution flow",
            confidence=0.95 if not gaps else 0.8,
        )

        self.lifecycle.save_recommendation(rec)

        self.event_bus.publish_sync(
            Event(
                name="recommendation.created",
                category="CapabilityIntelligence",
                source="CapabilityIntelligenceManager",
                payload={"recommendation_id": recommendation_id, "goal": target_goal},
            )
        )

        return rec

    def register_composite_bundle(
        self, bundle_name: str, capabilities: list[str]
    ) -> dict[str, Any]:
        """Create composite capability bundle and publish composition records."""
        bundle = self.composition.compose_bundle(bundle_name, capabilities)

        self.event_bus.publish_sync(
            Event(
                name="composition.generated",
                category="CapabilityIntelligence",
                source="CapabilityIntelligenceManager",
                payload={"bundle_id": bundle["bundle_id"], "composed": capabilities},
            )
        )

        return bundle

    def update_recommendation_status(self, recommendation_id: str, state: str) -> None:
        """Promote recommendation lifecycle status and publish event details."""
        self.lifecycle.transition_lifecycle(recommendation_id, state)

        self.event_bus.publish_sync(
            Event(
                name="lifecycle.updated",
                category="CapabilityIntelligence",
                source="CapabilityIntelligenceManager",
                payload={"recommendation_id": recommendation_id, "new_state": state},
            )
        )
