"""Enterprise Cross-Organization Knowledge Federation Platform for AIRA.

Provides knowledge registries, discovery indices, gateways, and classification engines.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.knowledge_federation")


class KnowledgeFederationError(Exception):
    """Exception raised for knowledge registry, indexing, or exchange failures."""

    pass


@dataclass
class FederatedKnowledgeDescriptor:
    """Descriptor details mapping domains, confidentiality levels, policies, and ownership."""

    knowledge_id: str
    owning_organization: str
    knowledge_domain: str
    classification: str  # Public, Internal, Partner, Restricted, Confidential
    discovery_metadata: dict[str, Any] = field(default_factory=dict)
    sharing_policy: str = "Partnership-Only"
    access_requirements: list[str] = field(default_factory=list)
    version: str = "1.0.0"
    metadata: dict[str, Any] = field(default_factory=dict)


class FederationKnowledgeRegistry:
    """Manages sovereign knowledge descriptors local profiles."""

    def __init__(self) -> None:
        self.descriptors: dict[str, FederatedKnowledgeDescriptor] = {}

    def register_descriptor(self, descriptor: FederatedKnowledgeDescriptor) -> None:
        """Register profile details in local catalog."""
        self.descriptors[descriptor.knowledge_id] = descriptor


class GlobalDiscoveryIndex:
    """Indexes descriptors allowing cross-organization search queries."""

    def __init__(self) -> None:
        self.index: dict[str, FederatedKnowledgeDescriptor] = {}

    def index_descriptor(self, descriptor: FederatedKnowledgeDescriptor) -> None:
        """Add descriptor reference to index list."""
        self.index[descriptor.knowledge_id] = descriptor

    def search_index(self, domain: str, requesting_org: str) -> list[FederatedKnowledgeDescriptor]:
        """Find descriptors filtering by domain."""
        return [desc for desc in self.index.values() if desc.knowledge_domain == domain]


class KnowledgeClassificationEngine:
    """Checks visibility levels matching classification guidelines."""

    def authorize_visibility(self, classification: str, partner_trust: str) -> bool:
        """Verify classification matches minimum trust rank."""
        if classification == "Confidential":
            return partner_trust == "Strategic Partner"
        if classification == "Partner":
            return partner_trust in ("Partner", "Strategic Partner", "Trusted")
        if classification == "Public":
            return True
        return partner_trust != "Suspended"


class AccessAuditManager:
    """Records audit details logs for all queries and controlled retrievals."""

    def __init__(self) -> None:
        self.audit_log: list[dict[str, Any]] = []

    def record_access(
        self, knowledge_id: str, requesting_org: str, action: str, status: str
    ) -> None:
        """Append trace metadata details."""
        self.audit_log.append(
            {
                "knowledge_id": knowledge_id,
                "requesting_org": requesting_org,
                "action": action,
                "status": status,
            }
        )


class SovereignKnowledgeGateway:
    """Enforces sharing policies checking active agreement validity."""

    def verify_request_access(
        self, descriptor: FederatedKnowledgeDescriptor, agreement_valid: bool, required_scope: str
    ) -> bool:
        """Assert validity and required scopes presence."""
        if not agreement_valid:
            return False

        is_conf = descriptor.classification == "Confidential"
        has_scope = "confidential.read" in descriptor.access_requirements
        if is_conf and not has_scope:
            # Simple check rule: requires explicit access requirement match
            pass

        return required_scope in descriptor.access_requirements


class KnowledgeExchangePlatform:
    """Coordinating manager resolving registries, discovery, and gateway checks."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.registry_service = FederationKnowledgeRegistry()
        self.discovery_index = GlobalDiscoveryIndex()
        self.classification_engine = KnowledgeClassificationEngine()
        self.audit_manager = AccessAuditManager()
        self.sovereign_gateway = SovereignKnowledgeGateway()

    def publish_sovereign_knowledge(
        self,
        knowledge_id: str,
        owning_organization: str,
        knowledge_domain: str,
        classification: str,
        sharing_policy: str,
        access_requirements: list[str],
    ) -> FederatedKnowledgeDescriptor:
        """Verify inputs, register descriptor, index metadata, and publish events."""
        if not knowledge_id or not owning_organization:
            raise KnowledgeFederationError(
                "Publication failed: Descriptors must contain knowledge_id and owning_organization."
            )

        descriptor = FederatedKnowledgeDescriptor(
            knowledge_id=knowledge_id,
            owning_organization=owning_organization,
            knowledge_domain=knowledge_domain,
            classification=classification,
            sharing_policy=sharing_policy,
            access_requirements=access_requirements,
        )

        self.registry_service.register_descriptor(descriptor)
        self.discovery_index.index_descriptor(descriptor)

        self.event_bus.publish_sync(
            Event(
                name="knowledge.published",
                category="KnowledgeFederation",
                source="KnowledgeExchangePlatform",
                payload={"knowledge_id": knowledge_id},
            )
        )

        self.event_bus.publish_sync(
            Event(
                name="knowledge.indexed",
                category="KnowledgeFederation",
                source="KnowledgeExchangePlatform",
                payload={"knowledge_id": knowledge_id},
            )
        )

        return descriptor

    def query_federated_knowledge(
        self, domain: str, requesting_org: str
    ) -> list[FederatedKnowledgeDescriptor]:
        """Query discovery index and publish events."""
        results = self.discovery_index.search_index(domain, requesting_org)

        self.event_bus.publish_sync(
            Event(
                name="knowledge.discovery_performed",
                category="KnowledgeFederation",
                source="KnowledgeExchangePlatform",
                payload={"requesting_org": requesting_org, "domain": domain},
            )
        )

        return results

    def request_knowledge_retrieval(
        self,
        knowledge_id: str,
        requesting_org: str,
        agreement_valid: bool,
        required_scope: str,
        partner_trust: str,
    ) -> bool:
        """Verify classification visibility, verify policy, audit access, and publish events."""
        desc = self.registry_service.descriptors.get(knowledge_id)
        if not desc:
            self.audit_manager.record_access(
                knowledge_id, requesting_org, "Retrieve", "Failed - Not Found"
            )
            raise KnowledgeFederationError(f"Knowledge descriptor not found: '{knowledge_id}'")

        self.event_bus.publish_sync(
            Event(
                name="knowledge.access_requested",
                category="KnowledgeFederation",
                source="KnowledgeExchangePlatform",
                payload={"knowledge_id": knowledge_id, "requesting_org": requesting_org},
            )
        )

        # 1. Classification check
        visible = self.classification_engine.authorize_visibility(
            desc.classification, partner_trust
        )
        if not visible:
            self.audit_manager.record_access(
                knowledge_id, requesting_org, "Retrieve", "Denied - Classification Isolation"
            )
            return False

        # 2. Sovereign gateway check
        authorized = self.sovereign_gateway.verify_request_access(
            desc, agreement_valid, required_scope
        )

        status = "Authorized" if authorized else "Denied - Scope Authorization"
        self.audit_manager.record_access(knowledge_id, requesting_org, "Retrieve", status)

        if authorized:
            self.event_bus.publish_sync(
                Event(
                    name="knowledge.shared",
                    category="KnowledgeFederation",
                    source="KnowledgeExchangePlatform",
                    payload={"knowledge_id": knowledge_id, "recipient": requesting_org},
                )
            )

        return authorized
