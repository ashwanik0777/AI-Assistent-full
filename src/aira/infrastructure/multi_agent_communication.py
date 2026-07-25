"""Enterprise Multi-Agent Communication, Coordination & Protocol Platform for AIRA.

Provides message models, protocol layers, routers, coordination engines, and auditors.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.multi_agent_communication")


class MultiAgentCommunicationError(Exception):
    """Base exception raised for protocol validation errors or message delivery failures."""

    pass


@dataclass
class AgentMessage:
    """Message representing sender, receiver, payload, and delivery status metadata."""

    message_id: str
    conversation_id: str
    sender: str
    receiver: str
    message_type: str  # Request, Response, Event, Broadcast, Notification, Heartbeat
    payload_ref: dict[str, Any]
    protocol_version: str = "1.0"
    priority: int = 1
    delivery_status: str = "Queued"  # Queued, Sent, Delivered, Acknowledged, Expired, Failed
    metadata: dict[str, Any] = field(default_factory=dict)
    version: int = 1


class ProtocolLayer:
    """Validates structural message formatting integrity and protocol constraints compatibility."""

    def validate_message(self, message: AgentMessage) -> None:
        """Verify protocol version compatibility and basic structure fields."""
        if message.protocol_version != "1.0":
            raise MultiAgentCommunicationError(
                f"Protocol mismatch: Version '{message.protocol_version}' is not supported."
            )
        if not message.sender or not message.receiver:
            raise MultiAgentCommunicationError(
                "Invalid message format: Senders and receivers fields must be defined."
            )


class MessageRouter:
    """Routes messages depending on receiver identity and organization scopes constraints."""

    def validate_route(self, message: AgentMessage, allowed_receivers: set[str]) -> bool:
        """Check if receiver is authorized and registered inside routing tables."""
        return message.receiver in allowed_receivers


class CoordinationEngine:
    """Coordinates task handoffs, synchronization steps, and dependencies management."""

    def __init__(self) -> None:
        self.dependencies: dict[str, list[str]] = {}

    def register_handoff_dependency(self, task_id: str, dependent_task_id: str) -> None:
        """Register task dependency lock."""
        self.dependencies.setdefault(task_id, []).append(dependent_task_id)


class DeliveryManager:
    """Manages queue states transitions of messages lifecycle."""

    def transition_state(self, message: AgentMessage, to_state: str) -> None:
        """Verify delivery states flow constraints rules."""
        allowed = {"Queued", "Sent", "Delivered", "Acknowledged", "Expired", "Failed"}
        if to_state not in allowed:
            raise MultiAgentCommunicationError(f"Unsupported delivery status: '{to_state}'")

        # Basic verification rules
        current = message.delivery_status
        if current == "Acknowledged" and to_state != "Acknowledged":
            raise MultiAgentCommunicationError("Cannot transition from Acknowledged state.")

        message.delivery_status = to_state


class CommunicationAuditManager:
    """Tracks complete communication logs lineages and conservation contexts."""

    def __init__(self) -> None:
        self.audit_log: list[AgentMessage] = []

    def audit_message(self, message: AgentMessage) -> None:
        """Record copy of message trace."""
        self.audit_log.append(message)


class MultiAgentCommunicationPlatform:
    """Coordinating manager resolving multi-agent protocols, routing, and delivery."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.protocol = ProtocolLayer()
        self.router = MessageRouter()
        self.coordination = CoordinationEngine()
        self.delivery = DeliveryManager()
        self.audit = CommunicationAuditManager()

        self.registered_agents: set[str] = set()

    def register_agent_route(self, agent_id: str) -> None:
        """Add agent to valid routing coordinates table."""
        self.registered_agents.add(agent_id)

    def dispatch_agent_message(self, message: AgentMessage) -> None:
        """Execute validation, routing check, delivery flow, and dispatch events."""
        # 1. Protocol Validation
        self.protocol.validate_message(message)

        # 2. Routing check
        if not self.router.validate_route(message, self.registered_agents):
            self.delivery.transition_state(message, "Failed")
            self.audit.audit_message(message)
            raise MultiAgentCommunicationError(
                f"Routing failed: Receiver '{message.receiver}' is unregistered or suspended."
            )

        # 3. Deliver
        self.delivery.transition_state(message, "Sent")
        self.event_bus.publish_sync(
            Event(
                name="message.sent",
                category="MultiAgentCommunication",
                source="MultiAgentCommunicationPlatform",
                payload={"message_id": message.message_id, "receiver": message.receiver},
            )
        )

        self.delivery.transition_state(message, "Delivered")
        self.event_bus.publish_sync(
            Event(
                name="message.delivered",
                category="MultiAgentCommunication",
                source="MultiAgentCommunicationPlatform",
                payload={"message_id": message.message_id},
            )
        )

        # Audit
        self.audit.audit_message(message)

    def acknowledge_delivery(self, message: AgentMessage) -> None:
        """Promote message state to Acknowledged and publish updates."""
        self.delivery.transition_state(message, "Acknowledged")
        self.event_bus.publish_sync(
            Event(
                name="delivery.acknowledged",
                category="MultiAgentCommunication",
                source="MultiAgentCommunicationPlatform",
                payload={"message_id": message.message_id},
            )
        )
