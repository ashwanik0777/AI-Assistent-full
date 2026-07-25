"""Enterprise Agent Messaging, Communication Bus & Coordination Protocol for AIRA.

Provides message schemas, validation, routers, conversation histories, and correlation trackers.
"""

import time
from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.agent_messaging")


class AgentMessagingError(Exception):
    """Raised when message verification, queueing rules, or routing limits are violated."""

    pass


@dataclass
class AgentMessage:
    """Standard message payload contract for agent communication channels."""

    message_id: str
    correlation_id: str
    conversation_id: str
    sender_agent_id: str
    receiver_agent_id: str
    msg_type: str  # Request, Response, Event, Notification, Broadcast, Acknowledgement, Error
    priority: int
    lease_ref: str | None
    payload: dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)
    payload_version: str = "1.0.0"


class MessageValidator:
    """Enforces schema standards, permissions boundaries, and lease validity checks."""

    def validate_message(self, msg: AgentMessage, lease_manager: Any = None) -> None:
        """Verify sender constraints and lease bounds if reference is attached."""
        if not msg.message_id or not msg.sender_agent_id:
            raise AgentMessagingError("Validation failed: Message ID and Sender ID must be set.")

        # If lease reference is attached, check with Lease Manager if present
        has_invalid_lease = (
            msg.lease_ref and lease_manager and not lease_manager.validate_lease(msg.lease_ref)
        )
        if has_invalid_lease:
            raise AgentMessagingError(
                f"Validation failed: Attached lease '{msg.lease_ref}' is invalid or expired."
            )


class MessageRouter:
    """Queues, prioritizes, and routes messages to receiver buffers."""

    def __init__(self) -> None:
        self.queues: dict[str, list[AgentMessage]] = {}
        self.dlq: list[AgentMessage] = []

    def route_message(self, msg: AgentMessage) -> None:
        """Route message to receiver queue buffer, sorting by priority desc."""
        receiver = msg.receiver_agent_id
        if not receiver:
            # Drop to Dead Letter Queue if destination is missing
            self.dlq.append(msg)
            raise AgentMessagingError("Routing failed: Receiver Agent ID is missing.")

        if receiver not in self.queues:
            self.queues[receiver] = []

        self.queues[receiver].append(msg)
        self.queues[receiver].sort(key=lambda m: m.priority, reverse=True)


class ConversationManager:
    """Maintains participants history records, workflow links, and active states."""

    def __init__(self) -> None:
        self.conversations: dict[str, dict[str, Any]] = {}

    def start_conversation(self, conversation_id: str, participants: list[str]) -> None:
        """Register a new conversation channel."""
        self.conversations[conversation_id] = {
            "conversation_id": conversation_id,
            "participants": participants,
            "messages": [],
            "state": "Active",
        }

    def append_message(self, conversation_id: str, msg: AgentMessage) -> None:
        """Record message trace into active conversation history."""
        conv = self.conversations.get(conversation_id)
        if not conv:
            raise AgentMessagingError(
                f"Conversation update failed: Conversation ID '{conversation_id}' not found."
            )
        conv["messages"].append(msg)


class CorrelationTracker:
    """Traces requests/responses linkage, tracking completions timelines."""

    def __init__(self) -> None:
        # Maps correlation_id -> status summary
        self.spans: dict[str, dict[str, Any]] = {}

    def register_span(self, correlation_id: str, root_request_id: str) -> None:
        """Initialize trace tracking context."""
        self.spans[correlation_id] = {
            "root_request_id": root_request_id,
            "responses_count": 0,
            "completed": False,
        }

    def record_response(self, correlation_id: str, response_id: str) -> None:
        """Increment response logs counts."""
        span = self.spans.get(correlation_id)
        if span:
            span["responses_count"] += 1

    def finalize_correlation(self, correlation_id: str) -> None:
        """Mark span correlation trace as completed."""
        span = self.spans.get(correlation_id)
        if span:
            span["completed"] = True


class AgentCommunicationBus:
    """Subsystem coordinator validating, routing, and tracking correlations of agent messages."""

    def __init__(
        self,
        config: AppConfig,
        registry: ServiceRegistry,
        event_bus: EventBus,
        lease_manager: Any = None,
    ) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus
        self.lease_manager = lease_manager

        self.validator = MessageValidator()
        self.router = MessageRouter()
        self.conversation_manager = ConversationManager()
        self.correlation_tracker = CorrelationTracker()

    def send_message(self, msg: AgentMessage) -> None:
        """Process send request: validate -> start conversation/span -> route."""
        # 1. Publish event message.sent
        self.event_bus.publish_sync(
            Event(
                name="message.sent",
                category="Communication",
                source="AgentMessaging",
                payload={"message_id": msg.message_id, "sender": msg.sender_agent_id},
            )
        )

        # 2. Validate
        self.validator.validate_message(msg, self.lease_manager)
        self.event_bus.publish_sync(
            Event(
                name="message.validated",
                category="Communication",
                source="AgentMessaging",
                payload={"message_id": msg.message_id},
            )
        )

        # 3. Handle conversation mapping
        if msg.conversation_id not in self.conversation_manager.conversations:
            self.conversation_manager.start_conversation(
                msg.conversation_id, [msg.sender_agent_id, msg.receiver_agent_id]
            )
        self.conversation_manager.append_message(msg.conversation_id, msg)
        self.event_bus.publish_sync(
            Event(
                name="conversation.updated",
                category="Communication",
                source="AgentMessaging",
                payload={"conversation_id": msg.conversation_id},
            )
        )

        # 4. Handle correlation tracking
        if msg.correlation_id not in self.correlation_tracker.spans:
            self.correlation_tracker.register_span(msg.correlation_id, msg.message_id)

        if msg.msg_type == "Response":
            self.correlation_tracker.record_response(msg.correlation_id, msg.message_id)
            self.correlation_tracker.finalize_correlation(msg.correlation_id)
            self.event_bus.publish_sync(
                Event(
                    name="correlation.completed",
                    category="Communication",
                    source="AgentMessaging",
                    payload={"correlation_id": msg.correlation_id},
                )
            )

        # 5. Route
        self.router.route_message(msg)
        self.event_bus.publish_sync(
            Event(
                name="message.routed",
                category="Communication",
                source="AgentMessaging",
                payload={"message_id": msg.message_id, "receiver": msg.receiver_agent_id},
            )
        )
        self.event_bus.publish_sync(
            Event(
                name="message.received",
                category="Communication",
                source="AgentMessaging",
                payload={"message_id": msg.message_id, "receiver": msg.receiver_agent_id},
            )
        )
