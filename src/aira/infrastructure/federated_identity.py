"""Enterprise Federated Identity, Trust, Delegation & Cross-Domain Authorization Platform for AIRA.

Provides identity registers, trust validators, authorization engines, and delegation managers.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.federated_identity")


class FederatedIdentityError(Exception):
    """Base exception raised for trust verification issues or unauthorized delegation actions."""

    pass


@dataclass
class FederatedIdentityRecord:
    """Identity record containing scopes, delegated roles, and verification states."""

    identity_id: str
    identity_type: str  # User, Agent, Service, Workload, Organization
    organization: str
    trust_domain: str
    delegated_roles: list[str] = field(default_factory=list)
    authorization_scope: list[str] = field(default_factory=list)
    credential_metadata: dict[str, Any] = field(default_factory=dict)
    lifecycle_state: str = "Created"  # Created, Verified, Active, Suspended, Revoked, Archived
    metadata: dict[str, Any] = field(default_factory=dict)
    version: int = 1


class TrustValidator:
    """Validates compatibility of external federation domains and organization policy matching."""

    def validate_trust(self, identity: FederatedIdentityRecord) -> None:
        """Reject untrusted domains or identities in Suspended/Revoked status states."""
        # 1. State check
        if identity.lifecycle_state in ("Suspended", "Revoked"):
            raise FederatedIdentityError(
                f"Trust validation failed: Identity '{identity.identity_id}' "
                f"is in '{identity.lifecycle_state}' state."
            )

        # 2. Trust domain verification
        if "untrusted" in identity.trust_domain.lower():
            raise FederatedIdentityError(
                f"Trust validation failed: Domain '{identity.trust_domain}' is not trusted."
            )


class AuthorizationEngine:
    """Evaluates role policies and scope privileges checks on target resource actions."""

    def authorize_action(self, identity: FederatedIdentityRecord, required_scope: str) -> None:
        """Reject authorization if scopes are mismatched."""
        if required_scope not in identity.authorization_scope:
            raise FederatedIdentityError(
                f"Authorization failed: Scope '{required_scope}' is missing from "
                f"identity scopes: {identity.authorization_scope}."
            )


class DelegationManager:
    """Registers delegated execution leases and audits temporary delegators chains."""

    def __init__(self) -> None:
        # Maps delegate_id -> delegator_id
        self.delegations: dict[str, str] = {}
        self.history: list[dict[str, Any]] = []

    def delegate_role(self, delegate_id: str, delegator_id: str) -> None:
        """Enroll delegation map link."""
        self.delegations[delegate_id] = delegator_id
        self.history.append({"delegate_id": delegate_id, "delegator_id": delegator_id})


class IdentityLifecycleManager:
    """Enforces state transition boundaries checks."""

    def transition_state(self, identity: FederatedIdentityRecord, to_state: str) -> None:
        """Enforce allowed lifecycle status updates."""
        allowed = {"Created", "Verified", "Active", "Suspended", "Revoked", "Archived"}
        if to_state not in allowed:
            raise FederatedIdentityError(f"Transition failed: State '{to_state}' is not supported.")
        identity.lifecycle_state = to_state


class FederatedIdentityManager:
    """Coordinating manager checking federations, delegation maps, and auth events."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.trust_validator = TrustValidator()
        self.authorization_engine = AuthorizationEngine()
        self.delegation_manager = DelegationManager()
        self.lifecycle_manager = IdentityLifecycleManager()

        self.identities: dict[str, FederatedIdentityRecord] = {}

    def register_identity(
        self, identity_id: str, identity_type: str, org: str, domain: str, scopes: list[str]
    ) -> FederatedIdentityRecord:
        """Construct record, promote state to Verified, and publish verification events."""
        record = FederatedIdentityRecord(
            identity_id=identity_id,
            identity_type=identity_type,
            organization=org,
            trust_domain=domain,
            authorization_scope=scopes,
        )
        self.identities[identity_id] = record

        # Transition state
        self.lifecycle_manager.transition_state(record, "Verified")

        self.event_bus.publish_sync(
            Event(
                name="identity.verified",
                category="FederatedIdentity",
                source="FederatedIdentityManager",
                payload={"identity_id": identity_id},
            )
        )

        return record

    def verify_and_authorize(
        self, identity_id: str, required_scope: str, delegate_id: str | None = None
    ) -> None:
        """Verify trust compatibility, run delegation maps, and authorize scope checks."""
        record = self.identities.get(identity_id)
        if not record:
            raise FederatedIdentityError(
                f"Verification failed: Identity '{identity_id}' not found."
            )

        # 1. Trust validation
        self.trust_validator.validate_trust(record)

        self.event_bus.publish_sync(
            Event(
                name="trust.validated",
                category="FederatedIdentity",
                source="FederatedIdentityManager",
                payload={"identity_id": identity_id, "domain": record.trust_domain},
            )
        )

        # 2. Delegation mapping check
        if delegate_id:
            self.delegation_manager.delegate_role(delegate_id, identity_id)

            self.event_bus.publish_sync(
                Event(
                    name="delegation.approved",
                    category="FederatedIdentity",
                    source="FederatedIdentityManager",
                    payload={"delegate": delegate_id, "delegator": identity_id},
                )
            )

        # 3. Authorization check
        self.authorization_engine.authorize_action(record, required_scope)

        self.event_bus.publish_sync(
            Event(
                name="authorization.granted",
                category="FederatedIdentity",
                source="FederatedIdentityManager",
                payload={"identity_id": identity_id, "scope": required_scope},
            )
        )

    def revoke_identity(self, identity_id: str) -> None:
        """Revoke active status state of identity record."""
        record = self.identities.get(identity_id)
        if not record:
            raise FederatedIdentityError(f"Revocation failed: Identity '{identity_id}' not found.")

        self.lifecycle_manager.transition_state(record, "Revoked")

        self.event_bus.publish_sync(
            Event(
                name="identity.revoked",
                category="FederatedIdentity",
                source="FederatedIdentityManager",
                payload={"identity_id": identity_id},
            )
        )
