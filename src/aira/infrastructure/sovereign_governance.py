"""Enterprise Sovereign AI, Data Residency & Regional Governance Platform for AIRA.

Provides policy registries, residency managers, AI engines, and enforcement gateways.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.sovereign_governance")


class SovereignGovernanceError(Exception):
    """Exception raised for governance validation drifts, residency errors, or policy conflicts."""

    pass


@dataclass
class SovereignGovernanceProfile:
    """Governance profile detailing regional rules, retention constraints, and policies."""

    profile_id: str
    region: str
    organization: str
    data_residency_rules: list[str] = field(default_factory=list)
    ai_usage_policies: list[str] = field(default_factory=list)
    retention_policies: list[str] = field(default_factory=list)
    sharing_constraints: list[str] = field(default_factory=list)
    compliance_metadata: dict[str, Any] = field(default_factory=dict)
    version: str = "1.0.0"


class SovereignPolicyRegistry:
    """Manages regional governance profiles inventory."""

    def __init__(self) -> None:
        self.profiles: dict[str, SovereignGovernanceProfile] = {}

    def register_profile(self, profile: SovereignGovernanceProfile) -> None:
        """Save governance profile configuration settings."""
        self.profiles[profile.profile_id] = profile


class DataResidencyManager:
    """Enforces data storage location boundaries checks."""

    def verify_residency(self, profile: SovereignGovernanceProfile, data_location: str) -> bool:
        """Validate if data remains inside approved regions rules."""
        # Simple policy check rule: target location must match allowed list
        return data_location in profile.data_residency_rules


class SovereignAiPolicyEngine:
    """Governs AI operations and limits execution to approved jurisdictions."""

    def authorize_inference(
        self, profile: SovereignGovernanceProfile, execution_region: str, model_name: str
    ) -> bool:
        """Check execution region compatibility targets."""
        if execution_region != profile.region:
            return False

        # Verify allowed AI usage patterns (e.g. GPU local allocations)
        policy_key = f"Allow-{model_name}"
        return policy_key in profile.ai_usage_policies


class ResidencyAuditManager:
    """Logs data transfer traces and compiles compliance evidence logs."""

    def __init__(self) -> None:
        self.audit_log: list[dict[str, Any]] = []

    def record_evidence(
        self, profile_id: str, action: str, source: str, dest: str, status: str
    ) -> None:
        """Append trace compliance log entry."""
        self.audit_log.append(
            {
                "profile_id": profile_id,
                "action": action,
                "source": source,
                "dest": dest,
                "status": status,
            }
        )


class PolicyEnforcementGateway:
    """Intercepts and evaluates cross-region operations before execution."""

    def verify_cross_region_request(
        self, profile: SovereignGovernanceProfile, target_region: str, transfer_scope: str
    ) -> bool:
        """Enforce strict cross-border sharing constraints."""
        block_key = f"Block-{target_region}"
        if block_key in profile.sharing_constraints:
            return False

        return transfer_scope in profile.sharing_constraints


class SovereignGovernancePlatform:
    """Coordinating manager resolving policy registries, residency validations, and gateways."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.policy_registry = SovereignPolicyRegistry()
        self.residency_manager = DataResidencyManager()
        self.ai_policy_engine = SovereignAiPolicyEngine()
        self.audit_manager = ResidencyAuditManager()
        self.enforcement_gateway = PolicyEnforcementGateway()

    def publish_governance_profile(
        self,
        profile_id: str,
        region: str,
        organization: str,
        data_residency_rules: list[str],
        ai_usage_policies: list[str],
        sharing_constraints: list[str],
    ) -> SovereignGovernanceProfile:
        """Verify inputs, register profile details, and publish events."""
        if not profile_id or not region:
            raise SovereignGovernanceError(
                "Profile publication failed: Profiles require profile_id and region."
            )

        profile = SovereignGovernanceProfile(
            profile_id=profile_id,
            region=region,
            organization=organization,
            data_residency_rules=data_residency_rules,
            ai_usage_policies=ai_usage_policies,
            sharing_constraints=sharing_constraints,
        )

        self.policy_registry.register_profile(profile)

        self.event_bus.publish_sync(
            Event(
                name="sovereign.profile.published",
                category="SovereignGovernance",
                source="SovereignGovernancePlatform",
                payload={"profile_id": profile_id},
            )
        )

        return profile

    def validate_data_residency(self, profile_id: str, data_location: str) -> bool:
        """Validate storage residency rules, update audits, and publish events."""
        profile = self.policy_registry.profiles.get(profile_id)
        if not profile:
            raise SovereignGovernanceError(f"Governance profile not found: '{profile_id}'")

        valid = self.residency_manager.verify_residency(profile, data_location)

        self.event_bus.publish_sync(
            Event(
                name="sovereign.residency.validated",
                category="SovereignGovernance",
                source="SovereignGovernancePlatform",
                payload={"profile_id": profile_id, "valid": valid},
            )
        )

        return valid

    def evaluate_cross_region_transfer(
        self, profile_id: str, target_region: str, transfer_scope: str
    ) -> bool:
        """Audit cross-border requests, log results, and publish events."""
        profile = self.policy_registry.profiles.get(profile_id)
        if not profile:
            raise SovereignGovernanceError(f"Governance profile not found: '{profile_id}'")

        self.event_bus.publish_sync(
            Event(
                name="sovereign.cross_region.evaluated",
                category="SovereignGovernance",
                source="SovereignGovernancePlatform",
                payload={"profile_id": profile_id, "target_region": target_region},
            )
        )

        permitted = self.enforcement_gateway.verify_cross_region_request(
            profile, target_region, transfer_scope
        )

        status = "Permitted" if permitted else "Blocked"
        self.audit_manager.record_evidence(
            profile_id, "CrossRegionTransfer", profile.region, target_region, status
        )

        self.event_bus.publish_sync(
            Event(
                name="sovereign.compliance.recorded",
                category="SovereignGovernance",
                source="SovereignGovernancePlatform",
                payload={
                    "profile_id": profile_id,
                    "action": "CrossRegionTransfer",
                    "status": status,
                },
            )
        )

        return permitted
