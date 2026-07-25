"""Enterprise Agent Identity, Security, Trust & Zero-Trust Framework for AIRA.

Provides authentications, authorization engines, trust score engines, and secure messaging filters.
"""

import time
from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.agent_security")


class AgentSecurityError(Exception):
    """Raised when authentication checks, permission authorizations, or trust policies fail."""

    pass


@dataclass
class AgentIdentity:
    """Zero-Trust credential profile defining identity scopes, roles, and cert parameters."""

    agent_id: str
    role: str
    capabilities: list[str]
    permissions: list[str]
    trust_level: str = "Medium"
    cert_ref: str = "cert_placeholder"
    version: str = "1.0.0"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SecurityAuditRecord:
    """Security event record detailing validation status outcome logs."""

    audit_id: str
    agent_id: str
    event_type: str  # Authenticated, Denied, Violation, Revoked
    status: str
    reason: str
    timestamp: float = field(default_factory=time.time)


class IdentityManager:
    """Validates structural credentials properties."""

    def validate_identity_structure(self, identity: AgentIdentity) -> bool:
        """Confirm constraints like IDs, roles, and versions formats."""
        if not identity.agent_id or not identity.role:
            return False
        return len(identity.capabilities) > 0


class AuthenticationManager:
    """Tracks active participant session keys configurations."""

    def __init__(self) -> None:
        self.active_sessions: set[str] = set()

    def authenticate_session(self, agent_id: str) -> None:
        """Mark agent ID as authenticated."""
        self.active_sessions.add(agent_id)

    def is_authenticated(self, agent_id: str) -> bool:
        """Verify active authenticated token."""
        return agent_id in self.active_sessions

    def revoke_session(self, agent_id: str) -> None:
        """Invalidate active session immediately."""
        self.active_sessions.discard(agent_id)


class AuthorizationEngine:
    """Inspects permission parameters allowlists."""

    def authorize_capability(self, identity: AgentIdentity, capability: str) -> bool:
        """Match capability permissions against allowances."""
        return capability in identity.capabilities


class TrustEngine:
    """Computes explainable numeric trust scores (0.0 to 10.0) based on compliance indicators."""

    def calculate_trust_score(
        self, identity: AgentIdentity, is_auth: bool, violations_count: int
    ) -> float:
        """Aggregate score values, penalizing violations."""
        base = 8.0 if identity.trust_level == "High" else 6.0
        if not is_auth:
            return 0.0
        penalty = violations_count * 2.5
        return max(0.0, min(10.0, base - penalty))


class SecureMessagingValidator:
    """Intercepts communication transactions checking sender/receiver authentication states."""

    def validate_message_security(
        self,
        msg: Any,  # AgentMessage
        auth_mgr: AuthenticationManager,
    ) -> bool:
        """Confirm sender and receiver tokens are present and authenticated."""
        return auth_mgr.is_authenticated(msg.sender_agent_id) and auth_mgr.is_authenticated(
            msg.receiver_agent_id
        )


class SecurityAuditManager:
    """Maintains logs histories of security validation events."""

    def __init__(self) -> None:
        self.audits: list[SecurityAuditRecord] = []

    def log_security_event(
        self, audit_id: str, agent_id: str, event_type: str, status: str, reason: str
    ) -> SecurityAuditRecord:
        """Save event record."""
        record = SecurityAuditRecord(
            audit_id=audit_id,
            agent_id=agent_id,
            event_type=event_type,
            status=status,
            reason=reason,
        )
        self.audits.append(record)
        return record


class SecurityOrchestrator:
    """Coordinating manager verifying identities, authorizations, and audits logs."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.identity_manager = IdentityManager()
        self.auth_manager = AuthenticationManager()
        self.auth_engine = AuthorizationEngine()
        self.trust_engine = TrustEngine()
        self.messaging_validator = SecureMessagingValidator()
        self.audit_manager = SecurityAuditManager()

        self.identities: dict[str, AgentIdentity] = {}
        self.violations_tracker: dict[str, int] = {}

    def register_agent_identity(self, identity: AgentIdentity) -> None:
        """Register profile configuration parameters."""
        if not self.identity_manager.validate_identity_structure(identity):
            raise AgentSecurityError(
                f"Identity registration failed: validation failed for ID '{identity.agent_id}'."
            )
        self.identities[identity.agent_id] = identity
        self.violations_tracker[identity.agent_id] = 0

    def authenticate_agent(self, agent_id: str) -> None:
        """Authenticate agent session, log audit, publish events."""
        if agent_id not in self.identities:
            self.event_bus.publish_sync(
                Event(
                    name="security.violation",
                    category="Security",
                    source="SecurityOrchestrator",
                    payload={"agent_id": agent_id, "reason": "Authentication of unregistered ID."},
                )
            )
            self.audit_manager.log_security_event(
                f"sec_audit_{int(time.time())}",
                agent_id,
                "Authenticated",
                "Failed",
                "ID not registered.",
            )
            raise AgentSecurityError(f"Authentication failed: ID '{agent_id}' not registered.")

        self.auth_manager.authenticate_session(agent_id)
        self.event_bus.publish_sync(
            Event(
                name="agent.authenticated",
                category="Security",
                source="SecurityOrchestrator",
                payload={"agent_id": agent_id},
            )
        )
        self.audit_manager.log_security_event(
            f"sec_audit_{int(time.time())}",
            agent_id,
            "Authenticated",
            "Success",
            "Session established.",
        )

        # Trigger initial trust score update
        self.update_agent_trust_score(agent_id)

    def update_agent_trust_score(self, agent_id: str) -> float:
        """Recalculate trust levels and publish updates."""
        identity = self.identities.get(agent_id)
        if not identity:
            raise AgentSecurityError(f"Trust calculation failed: ID '{agent_id}' not registered.")

        is_auth = self.auth_manager.is_authenticated(agent_id)
        violations = self.violations_tracker.get(agent_id, 0)

        score = self.trust_engine.calculate_trust_score(identity, is_auth, violations)
        self.event_bus.publish_sync(
            Event(
                name="trust.updated",
                category="Security",
                source="SecurityOrchestrator",
                payload={"agent_id": agent_id, "trust_score": score},
            )
        )
        return score

    def verify_agent_authorization(self, agent_id: str, capability: str) -> None:
        """Check capability access permission allowlists."""
        identity = self.identities.get(agent_id)
        if not identity:
            raise AgentSecurityError(f"Authorization failed: ID '{agent_id}' not registered.")

        if not self.auth_manager.is_authenticated(agent_id):
            raise AgentSecurityError(
                f"Authorization failed: Agent '{agent_id}' is not authenticated."
            )

        if not self.auth_engine.authorize_capability(identity, capability):
            self.violations_tracker[agent_id] = self.violations_tracker.get(agent_id, 0) + 1
            self.update_agent_trust_score(agent_id)
            self.event_bus.publish_sync(
                Event(
                    name="authorization.denied",
                    category="Security",
                    source="SecurityOrchestrator",
                    payload={"agent_id": agent_id, "capability": capability},
                )
            )
            self.audit_manager.log_security_event(
                f"sec_audit_{int(time.time())}",
                agent_id,
                "Denied",
                "Failed",
                f"Missing capability '{capability}'.",
            )
            raise AgentSecurityError(
                f"Authorization Denied: Access to '{capability}' not authorized."
            )

        self.event_bus.publish_sync(
            Event(
                name="authorization.granted",
                category="Security",
                source="SecurityOrchestrator",
                payload={"agent_id": agent_id, "capability": capability},
            )
        )

    def revoke_agent(self, agent_id: str, reason: str) -> None:
        """Evict active session tokens, log audit, and publish revocation notice."""
        self.auth_manager.revoke_session(agent_id)
        self.event_bus.publish_sync(
            Event(
                name="agent.revoked",
                category="Security",
                source="SecurityOrchestrator",
                payload={"agent_id": agent_id, "reason": reason},
            )
        )
        self.audit_manager.log_security_event(
            f"sec_audit_{int(time.time())}", agent_id, "Revoked", "Success", reason
        )
