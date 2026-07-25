"""Enterprise Global Knowledge Distribution & Regional Governance Platform.

Provides distribution policy engines, regional planners, and audit managers.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.global_knowledge_distribution")


class GlobalKnowledgeDistributionError(Exception):
    """Base exception raised for distribution validation failures or regional compliance blocks."""

    pass


@dataclass
class DistributionManifest:
    """Manifest representing knowledge distribution parameters and rollout lifecycle states."""

    distribution_id: str
    knowledge_pack_id: str
    target_regions: list[str]
    distribution_policy: str  # Global, Regional, Organization, Canary, Staged, Emergency Rollback
    localization_profile: dict[str, Any] = field(default_factory=dict)
    compliance_rules: list[str] = field(default_factory=list)
    rollout_strategy: str = "Linear"
    health_status: str = "Healthy"
    version: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)
    lifecycle_state: str = "Planned"  # Planned, Rolling Out, Completed, Rolled Back


class DistributionPolicyEngine:
    """Validates distribution manifests against active corporate policies."""

    def validate_manifest(self, manifest: DistributionManifest) -> None:
        """Reject plans with unsupported policies."""
        allowed = {"Global", "Regional", "Organization", "Canary", "Staged", "Emergency Rollback"}
        if manifest.distribution_policy not in allowed:
            raise GlobalKnowledgeDistributionError(
                f"Policy validation failed: Policy '{manifest.distribution_policy}' "
                f"is not supported."
            )


class RegionalPlanner:
    """Calculates rollout ordering lists and ensures compliance constraints are evaluated."""

    def plan_rollout(self, regions: list[str], compliance_rules: list[str]) -> list[str]:
        """Verify region eligibility compliance boundaries."""
        # Enforce rule: Pause rollout if EU region contains non-compliant privacy flags
        res = []
        for r in regions:
            if r == "Europe" and "restrict-eu-data" in compliance_rules:
                raise GlobalKnowledgeDistributionError(
                    "Planning failed: Regional compliance rules block Europe distribution."
                )
            res.append(r)
        return res


class LocalizationManager:
    """Manures localized contents and adapts regional vocabulary variations."""

    def localize_pack(self, pack_id: str, locale: str, profile: dict[str, Any]) -> dict[str, Any]:
        """Return localized dictionary stubs."""
        lang = profile.get(locale, "en")
        return {
            "pack_id": pack_id,
            "locale": locale,
            "language": lang,
            "adapted_content": f"Content adapted to language '{lang}'.",
        }


class DistributionHealthMonitor:
    """Evaluates distribution metrics and updates rollout status flags."""

    def check_health(self, manifest: DistributionManifest, node_failures: int) -> None:
        """Update health status tag to Degraded if failures count exceeds threshold limit."""
        if node_failures > 2:
            manifest.health_status = "Degraded"
        else:
            manifest.health_status = "Healthy"


class DistributionAuditManager:
    """Logs rollout steps milestones and regional completion indicators records."""

    def __init__(self) -> None:
        self.audit_trail: list[dict[str, Any]] = []

    def log_event(
        self, dist_id: str, event_name: str, region: str, details: dict[str, Any]
    ) -> None:
        """Append audit log entry."""
        self.audit_trail.append(
            {"distribution_id": dist_id, "event": event_name, "region": region, "details": details}
        )


class GlobalKnowledgeDistributionManager:
    """Coordinating manager resolving staged rollouts, localization files, and events."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.policy_engine = DistributionPolicyEngine()
        self.regional_planner = RegionalPlanner()
        self.localization_manager = LocalizationManager()
        self.health_monitor = DistributionHealthMonitor()
        self.audit_manager = DistributionAuditManager()

        self.distributions: dict[str, DistributionManifest] = {}

    def plan_distribution(
        self,
        dist_id: str,
        pack_id: str,
        regions: list[str],
        policy: str,
        compliance_rules: list[str],
        localization_profile: dict[str, Any],
    ) -> DistributionManifest:
        """Plan staged rollout, check compliance region limits, and publish planned events."""
        # 1. Create manifest
        manifest = DistributionManifest(
            distribution_id=dist_id,
            knowledge_pack_id=pack_id,
            target_regions=regions,
            distribution_policy=policy,
            compliance_rules=compliance_rules,
            localization_profile=localization_profile,
        )

        # 2. Validate Policy and Plan Rollout
        self.policy_engine.validate_manifest(manifest)
        self.regional_planner.plan_rollout(regions, compliance_rules)

        self.distributions[dist_id] = manifest

        self.event_bus.publish_sync(
            Event(
                name="distribution.planned",
                category="GlobalKnowledgeDistribution",
                source="GlobalKnowledgeDistributionManager",
                payload={"distribution_id": dist_id, "pack_id": pack_id},
            )
        )

        return manifest

    def execute_distribution_rollout(self, dist_id: str) -> None:
        """Execute distribution steps, manage localization, and publish rollout completed events."""
        manifest = self.distributions.get(dist_id)
        if not manifest:
            raise GlobalKnowledgeDistributionError(
                f"Rollout failed: Distribution '{dist_id}' not found."
            )

        manifest.lifecycle_state = "Rolling Out"
        self.event_bus.publish_sync(
            Event(
                name="distribution.started",
                category="GlobalKnowledgeDistribution",
                source="GlobalKnowledgeDistributionManager",
                payload={"distribution_id": dist_id},
            )
        )

        # Staged rollout region loop
        for r in manifest.target_regions:
            # Localize
            self.localization_manager.localize_pack(
                manifest.knowledge_pack_id, r, manifest.localization_profile
            )

            # Audit
            self.audit_manager.log_event(dist_id, "Region Dispatched", r, {"status": "Success"})

            self.event_bus.publish_sync(
                Event(
                    name="region.updated",
                    category="GlobalKnowledgeDistribution",
                    source="GlobalKnowledgeDistributionManager",
                    payload={"distribution_id": dist_id, "region": r},
                )
            )

        manifest.lifecycle_state = "Completed"

        self.event_bus.publish_sync(
            Event(
                name="rollout.completed",
                category="GlobalKnowledgeDistribution",
                source="GlobalKnowledgeDistributionManager",
                payload={"distribution_id": dist_id},
            )
        )

    def trigger_rollback(self, dist_id: str) -> None:
        """Execute emergency rollback of active distribution version."""
        manifest = self.distributions.get(dist_id)
        if not manifest:
            raise GlobalKnowledgeDistributionError(
                f"Rollback failed: Distribution '{dist_id}' not found."
            )

        manifest.lifecycle_state = "Rolled Back"
        self.audit_manager.log_event(
            dist_id, "Rollback Triggered", "Global", {"reason": "Emergency"}
        )

        self.event_bus.publish_sync(
            Event(
                name="rollback.initiated",
                category="GlobalKnowledgeDistribution",
                source="GlobalKnowledgeDistributionManager",
                payload={"distribution_id": dist_id},
            )
        )
