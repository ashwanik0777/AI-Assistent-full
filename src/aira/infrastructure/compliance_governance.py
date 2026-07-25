"""Enterprise Compliance, Regulatory Profiles & Unified Governance Framework for AIRA.

Provides profile registries, policy engines, governance validators, and evidence generators.
"""

from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.compliance_governance")


class ComplianceGovernanceError(Exception):
    """Exception raised for compliance failures, validation faults, or retention errors."""

    pass


@dataclass
class ComplianceProfileDescriptor:
    """Descriptor layout specifying industry, jurisdiction, policies, and retention constraints."""

    profile_id: str
    industry: str  # Healthcare, Finance, Government, Education, Retail, Research
    jurisdiction: str
    policy_set: list[str] = field(default_factory=list)
    evidence_rules: list[str] = field(default_factory=list)
    audit_requirements: list[str] = field(default_factory=list)
    retention_rules: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    version: str = "1.0.0"


class ComplianceProfileRegistry:
    """Registry repository catalog managing configurable compliance profiles."""

    def __init__(self) -> None:
        self.profiles: dict[str, ComplianceProfileDescriptor] = {}

    def register_profile(self, profile: ComplianceProfileDescriptor) -> None:
        """Register profile details configuration."""
        self.profiles[profile.profile_id] = profile


class RegulatoryPolicyEngine:
    """Evaluates compliance policies against runtime execution actions."""

    def verify_policy_compliance(
        self, profile: ComplianceProfileDescriptor, policy_key: str
    ) -> bool:
        """Verify policy presence in profile policy set list."""
        return policy_key in profile.policy_set


class GovernanceValidator:
    """Intercepts runtime workflows and blocks non-compliant requests."""

    def is_action_allowed(
        self,
        profile: ComplianceProfileDescriptor,
        action: str,
        policy_engine: RegulatoryPolicyEngine,
    ) -> bool:
        """Evaluate if action complies with governance rules."""
        # Simple rule checks: action must match a valid policy configuration
        policy_key = f"Allow-{action}"
        return policy_engine.verify_policy_compliance(profile, policy_key)


class EvidenceGenerator:
    """Produces audit-ready evidence artifacts checkpoints logs."""

    def generate_evidence(self, profile_id: str, action: str, status: str) -> dict[str, Any]:
        """Construct evidence artifact detail."""
        return {
            "evidence_id": f"ev_{profile_id}_{action.lower()}",
            "profile_id": profile_id,
            "action": action,
            "status": status,
            "timestamp": datetime.utcnow().isoformat(),
            "checksum": f"hash_{profile_id}_{action}_{status}",
        }


class RetentionManager:
    """Enforces storage and retention lifecycles rules."""

    def verify_retention_period(
        self, profile: ComplianceProfileDescriptor, retention_years: int
    ) -> bool:
        """Validate if specified period matches profile rules limits."""
        # Assume rules contains string like "Min-7-Years"
        min_years = 0
        for rule in profile.retention_rules:
            if "Min-" in rule:
                with suppress(ValueError):
                    min_years = int(rule.split("-")[1])

        return retention_years >= min_years


class ComplianceGovernancePlatform:
    """Coordinating manager resolving profiles registry, policy engine, and evidence generation."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.profile_registry = ComplianceProfileRegistry()
        self.policy_engine = RegulatoryPolicyEngine()
        self.validator = GovernanceValidator()
        self.evidence_generator = EvidenceGenerator()
        self.retention_manager = RetentionManager()

        self.compliance_reports: dict[str, list[dict[str, Any]]] = {}

    def activate_compliance_profile(
        self,
        profile_id: str,
        industry: str,
        jurisdiction: str,
        policy_set: list[str],
        evidence_rules: list[str],
        retention_rules: list[str],
    ) -> ComplianceProfileDescriptor:
        """Verify parameters, register profile, and publish events."""
        if not profile_id or not industry:
            raise ComplianceGovernanceError(
                "Profile activation failed: Profiles require profile_id and industry."
            )

        profile = ComplianceProfileDescriptor(
            profile_id=profile_id,
            industry=industry,
            jurisdiction=jurisdiction,
            policy_set=policy_set,
            evidence_rules=evidence_rules,
            retention_rules=retention_rules,
        )

        self.profile_registry.register_profile(profile)

        self.event_bus.publish_sync(
            Event(
                name="compliance.profile.activated",
                category="ComplianceGovernance",
                source="ComplianceGovernancePlatform",
                payload={"profile_id": profile_id, "industry": industry},
            )
        )

        return profile

    def validate_action_compliance(self, profile_id: str, action: str) -> bool:
        """Check validation, generate evidence, log report updates, and publish events."""
        profile = self.profile_registry.profiles.get(profile_id)
        if not profile:
            raise ComplianceGovernanceError(f"Compliance profile not found: '{profile_id}'")

        allowed = self.validator.is_action_allowed(profile, action, self.policy_engine)

        self.event_bus.publish_sync(
            Event(
                name="compliance.policy.validated",
                category="ComplianceGovernance",
                source="ComplianceGovernancePlatform",
                payload={"profile_id": profile_id, "action": action, "allowed": allowed},
            )
        )

        # Generate Evidence
        status = "Approved" if allowed else "Blocked"
        evidence = self.evidence_generator.generate_evidence(profile_id, action, status)

        self.event_bus.publish_sync(
            Event(
                name="compliance.evidence.generated",
                category="ComplianceGovernance",
                source="ComplianceGovernancePlatform",
                payload={"evidence_id": evidence["evidence_id"]},
            )
        )

        # Update reporting summaries
        self.compliance_reports.setdefault(profile_id, []).append(evidence)

        return allowed

    def publish_governance_report(self, profile_id: str, reporter: str) -> None:
        """Publish preparing reports and trigger event notifications."""
        reports = self.compliance_reports.get(profile_id)
        if not reports:
            raise ComplianceGovernanceError(
                f"No compliance reports found for profile: '{profile_id}'"
            )

        self.event_bus.publish_sync(
            Event(
                name="compliance.audit.prepared",
                category="ComplianceGovernance",
                source="ComplianceGovernancePlatform",
                payload={"profile_id": profile_id},
            )
        )

        self.event_bus.publish_sync(
            Event(
                name="compliance.report.published",
                category="ComplianceGovernance",
                source="ComplianceGovernancePlatform",
                payload={"profile_id": profile_id, "reporter": reporter},
            )
        )
