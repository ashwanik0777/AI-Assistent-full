"""Enterprise Federated Identity, Organization Trust & Tenant Federation Platform for AIRA.

Provides identity registries, trust evaluation engines,
and isolation boundary checkers.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.tenant_federation")


class IdentityFederationError(Exception):
    """Exception raised for identity errors, trust downgrades, or isolation leaks."""

    pass


@dataclass
class FederationAgreement:
    """Agreement detail tracking trust levels, capabilities allowed, and validity status."""

    agreement_id: str
    org_a: str
    org_b: str
    trust_level: str  # Verified, Trusted, Restricted, Partner, Strategic Partner, Suspended
    allowed_capabilities: list[str] = field(default_factory=list)
    data_sharing_policy: str = "Restricted"
    governance_policy: str = "Standard"
    valid: bool = True
    version: str = "1.0.0"
    metadata: dict[str, Any] = field(default_factory=dict)


class FederatedIdentityRegistry:
    """Tracks verified organization profiles details and trust mappings."""

    def __init__(self) -> None:
        self.verified_orgs: dict[str, dict[str, Any]] = {}

    def register_org(self, org_id: str, trust_level: str) -> None:
        """Save organization context details."""
        self.verified_orgs[org_id] = {"trust_level": trust_level}


class OrganizationTrustEngine:
    """Validates trust transition rules and processes organizational downgrades."""

    def transition_trust(self, current_trust: str, next_trust: str) -> None:
        """Evaluate alignment transitions limits."""
        allowed = {
            "Verified": {"Trusted", "Restricted", "Partner", "Suspended"},
            "Trusted": {"Verified", "Restricted", "Strategic Partner", "Suspended"},
            "Restricted": {"Verified", "Suspended"},
            "Partner": {"Strategic Partner", "Suspended"},
            "Strategic Partner": {"Partner", "Suspended"},
            "Suspended": {"Verified", "Restricted"},
        }

        if next_trust not in allowed.get(current_trust, set()) and current_trust != next_trust:
            raise IdentityFederationError(
                f"Trust level transition rejected: Cannot transition from "
                f"'{current_trust}' to '{next_trust}'."
            )


class FederationAgreementManager:
    """Issues and invalidates cross-organization collaboration agreements."""

    def __init__(self) -> None:
        self.agreements: dict[str, FederationAgreement] = {}

    def create_agreement(self, agreement: FederationAgreement) -> None:
        """Save active agreement mapping."""
        self.agreements[agreement.agreement_id] = agreement

    def revoke_agreement(self, agreement_id: str) -> None:
        """Transition valid status flag to false."""
        ag = self.agreements.get(agreement_id)
        if not ag:
            raise IdentityFederationError(f"Agreement not found: '{agreement_id}'")
        ag.valid = False


class TenantIsolationManager:
    """Enforces boundaries isolation checks between organizational workloads."""

    def verify_isolation(self, org_a: str, org_b: str) -> bool:
        """Enforce strict identity isolation boundary check."""
        return org_a != org_b


class CrossOrganizationAccessManager:
    """Checks trust level and authorizes explicit capability requests."""

    def authorize_capability(self, agreement: FederationAgreement, capability: str) -> bool:
        """Assert validity and capability inclusion."""
        if not agreement.valid:
            return False

        if agreement.trust_level == "Suspended":
            return False

        return capability in agreement.allowed_capabilities


class TenantFederationPlatform:
    """Coordinating manager resolving identity, trust, agreements, and isolation."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.identity_registry = FederatedIdentityRegistry()
        self.trust_engine = OrganizationTrustEngine()
        self.agreement_manager = FederationAgreementManager()
        self.isolation_manager = TenantIsolationManager()
        self.access_manager = CrossOrganizationAccessManager()

    def verify_organization(self, org_id: str, trust_level: str) -> None:
        """Save organizational registry record and publish events."""
        self.identity_registry.register_org(org_id, trust_level)

        self.event_bus.publish_sync(
            Event(
                name="federation.org.verified",
                category="TenantFederation",
                source="TenantFederationPlatform",
                payload={"org_id": org_id, "trust_level": trust_level},
            )
        )

    def update_organization_trust(self, org_id: str, next_trust: str) -> None:
        """Validate trust transition rules and publish events."""
        org = self.identity_registry.verified_orgs.get(org_id)
        if not org:
            raise IdentityFederationError(f"Organization not verified: '{org_id}'")

        current = org["trust_level"]
        self.trust_engine.transition_trust(current, next_trust)
        org["trust_level"] = next_trust

        self.event_bus.publish_sync(
            Event(
                name="federation.trust.updated",
                category="TenantFederation",
                source="TenantFederationPlatform",
                payload={"org_id": org_id, "trust_level": next_trust},
            )
        )

        # Automatically suspend agreements if trust is suspended
        if next_trust == "Suspended":
            for ag in self.agreement_manager.agreements.values():
                if ag.org_a == org_id or ag.org_b == org_id:
                    self.revoke_agreement(ag.agreement_id)

    def establish_agreement(
        self,
        agreement_id: str,
        org_a: str,
        org_b: str,
        trust_level: str,
        allowed_capabilities: list[str],
    ) -> FederationAgreement:
        """Verify trust registries, create agreement mapping, and publish events."""
        if org_a not in self.identity_registry.verified_orgs:
            raise IdentityFederationError(f"Unverified organization: '{org_a}'")
        if org_b not in self.identity_registry.verified_orgs:
            raise IdentityFederationError(f"Unverified organization: '{org_b}'")

        agreement = FederationAgreement(
            agreement_id=agreement_id,
            org_a=org_a,
            org_b=org_b,
            trust_level=trust_level,
            allowed_capabilities=allowed_capabilities,
        )

        self.agreement_manager.create_agreement(agreement)

        self.event_bus.publish_sync(
            Event(
                name="federation.agreement.created",
                category="TenantFederation",
                source="TenantFederationPlatform",
                payload={"agreement_id": agreement_id},
            )
        )

        return agreement

    def revoke_agreement(self, agreement_id: str) -> None:
        """Invalidate active agreement mapping and publish events."""
        self.agreement_manager.revoke_agreement(agreement_id)

        self.event_bus.publish_sync(
            Event(
                name="federation.agreement.revoked",
                category="TenantFederation",
                source="TenantFederationPlatform",
                payload={"agreement_id": agreement_id},
            )
        )

    def request_cross_org_access(
        self, agreement_id: str, requesting_org: str, target_org: str, capability: str
    ) -> bool:
        """Assert isolation, verify agreement, and authorize capability access."""
        # 1. Enforce isolation boundaries check
        if not self.isolation_manager.verify_isolation(requesting_org, target_org):
            raise IdentityFederationError("Isolation check failed: Same organization loop.")

        # 2. Verify agreement details
        ag = self.agreement_manager.agreements.get(agreement_id)
        if not ag:
            raise IdentityFederationError(f"Federation agreement not found: '{agreement_id}'")

        # 3. Access check authorization
        authorized = self.access_manager.authorize_capability(ag, capability)
        if authorized:
            self.event_bus.publish_sync(
                Event(
                    name="federation.access.authorized",
                    category="TenantFederation",
                    source="TenantFederationPlatform",
                    payload={"agreement_id": agreement_id, "capability": capability},
                )
            )

        return authorized
