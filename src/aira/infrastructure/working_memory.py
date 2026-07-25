"""Enterprise Working Memory Engine for AIRA.

Provides temporary cognitive workspace and context sessions for the AI Operating System.
"""

import threading
import time
from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.working_memory")


class WorkingMemoryError(Exception):
    """Raised when context validation checks, size bounds checks, or session mismatches occur."""

    pass


@dataclass
class WorkingMemorySession:
    """Represents an isolated temporary memory workspace context."""

    session_id: str
    conversation_context: list[dict[str, Any]] = field(default_factory=list)
    execution_context: dict[str, Any] = field(default_factory=dict)
    temporary_knowledge: dict[str, Any] = field(default_factory=dict)
    scratchpad: list[str] = field(default_factory=list)
    active_variables: dict[str, Any] = field(default_factory=dict)
    last_accessed: float = field(default_factory=time.time)
    lifetime: float = 3600.0  # Default 1 hour lifetime bounds limit


class CapacityManager:
    """Manages active counts limits and drives Least Recently Used evictions."""

    def __init__(self, max_sessions: int = 5, default_lifetime: float = 3600.0) -> None:
        self.max_sessions = max_sessions
        self.default_lifetime = default_lifetime

    def check_eviction(
        self, sessions: dict[str, WorkingMemorySession], event_bus: EventBus
    ) -> list[str]:
        """Perform scan to identify and remove expired or LRU sessions."""
        evicted = []
        now = time.time()

        # 1. Check lifetime expiration updates
        for sid, sess in list(sessions.items()):
            if now - sess.last_accessed > sess.lifetime:
                evicted.append(sid)
                event_bus.publish_sync(
                    Event(
                        name="working_memory.expired",
                        category="Memory",
                        source="CapacityManager",
                        payload={"session_id": sid, "reason": "Lifetime expired"},
                    )
                )

        # 2. Check counts limits (LRU)
        active_remaining = [s for s in sessions.values() if s.session_id not in evicted]
        if len(active_remaining) >= self.max_sessions:
            # Sort by last_accessed ascending (oldest first)
            active_remaining.sort(key=lambda s: s.last_accessed)
            overage = len(active_remaining) - self.max_sessions + 1
            for i in range(overage):
                target = active_remaining[i]
                evicted.append(target.session_id)
                event_bus.publish_sync(
                    Event(
                        name="working_memory.expired",
                        category="Memory",
                        source="CapacityManager",
                        payload={"session_id": target.session_id, "reason": "LRU capacity limit"},
                    )
                )

        return evicted


class WorkingMemoryStore:
    """Thread-safe storage catalog for active WorkingMemorySession objects."""

    def __init__(self, capacity_manager: CapacityManager, event_bus: EventBus) -> None:
        self.capacity_manager = capacity_manager
        self.event_bus = event_bus
        self.sessions: dict[str, WorkingMemorySession] = {}
        self.lock = threading.Lock()

    def get_or_create(self, session_id: str) -> WorkingMemorySession:
        """Fetch matching session context or register a new session."""
        with self.lock:
            # Clean expired/LRU items first
            evicts = self.capacity_manager.check_eviction(self.sessions, self.event_bus)
            for sid in evicts:
                self.sessions.pop(sid, None)

            if session_id not in self.sessions:
                self.sessions[session_id] = WorkingMemorySession(session_id=session_id)
                self.event_bus.publish_sync(
                    Event(
                        name="working_memory.created",
                        category="Memory",
                        source="WorkingMemoryStore",
                        payload={"session_id": session_id},
                    )
                )
            else:
                self.sessions[session_id].last_accessed = time.time()

            return self.sessions[session_id]

    def close(self, session_id: str) -> None:
        """Evict session and fire close notifications."""
        with self.lock:
            if session_id in self.sessions:
                self.sessions.pop(session_id)
                self.event_bus.publish_sync(
                    Event(
                        name="working_memory.session_closed",
                        category="Memory",
                        source="WorkingMemoryStore",
                        payload={"session_id": session_id},
                    )
                )

    def clear_all(self) -> None:
        """Reset storage catalogs registers."""
        with self.lock:
            self.sessions.clear()
            self.event_bus.publish_sync(
                Event(
                    name="working_memory.cleared",
                    category="Memory",
                    source="WorkingMemoryStore",
                    payload={},
                )
            )


class WorkingMemoryManager:
    """Unified entry coordinator for Working Memory Engine."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        # Read config configurations settings
        kernel_settings = getattr(config, "kernel", None)
        max_limit = (
            getattr(kernel_settings, "max_working_memory_sessions", 5) if kernel_settings else 5
        )
        self.capacity_manager = CapacityManager(max_sessions=max_limit)
        self.store = WorkingMemoryStore(self.capacity_manager, self.event_bus)

    def write_conversation_context(self, session_id: str, message: dict[str, Any]) -> None:
        """Append message payloads to conversation context list."""
        sess = self.store.get_or_create(session_id)
        if "role" not in message or "content" not in message:
            raise WorkingMemoryError("Context update failed: Invalid message format structures.")

        sess.conversation_context.append(dict(message))
        self.event_bus.publish_sync(
            Event(
                name="working_memory.updated",
                category="Memory",
                source="WorkingMemoryManager",
                payload={"session_id": session_id, "section": "conversation_context"},
            )
        )

    def write_scratchpad(self, session_id: str, log_entry: str) -> None:
        """Append log instructions to scratchpad list buffer."""
        sess = self.store.get_or_create(session_id)
        if not log_entry:
            raise WorkingMemoryError("Context update failed: Empty scratchpad logs input.")

        sess.scratchpad.append(log_entry)
        self.event_bus.publish_sync(
            Event(
                name="working_memory.updated",
                category="Memory",
                source="WorkingMemoryManager",
                payload={"session_id": session_id, "section": "scratchpad"},
            )
        )

    def get_session(self, session_id: str) -> WorkingMemorySession | None:
        """Fetch session context matching target ID."""
        with self.store.lock:
            return self.store.sessions.get(session_id)
