"""Enterprise Memory Engine Foundation for AIRA.

Defines base memory object layouts, registers, validators, and lifecycles managers.
"""

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.memory_engine")


class MemoryEngineError(Exception):
    """Raised when memory validation, registrations, or lifecycle transitions fail."""

    pass


class MemoryType(Enum):
    """Supported classifications of memory data."""

    WORKING = "WORKING"
    EPISODIC = "EPISODIC"
    SEMANTIC = "SEMANTIC"
    PROCEDURAL = "PROCEDURAL"
    KNOWLEDGE_GRAPH = "KNOWLEDGE_GRAPH"
    SHARED = "SHARED"


class MemoryState(Enum):
    """Supported state representations during memory lifetimes."""

    CREATED = "CREATED"
    VALIDATED = "VALIDATED"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"
    EXPIRED = "EXPIRED"
    DELETED = "DELETED"


@dataclass
class MemoryObject:
    """Enterprise memory data schema representation."""

    memory_id: str
    memory_type: MemoryType
    version: str
    source: str
    owner: str
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    state: MemoryState = MemoryState.CREATED
    timestamp: float = field(default_factory=time.time)


class MemoryValidator:
    """Validates parameters format and version structure compatibility."""

    def validate(self, memory: MemoryObject) -> None:
        """Enforce standard checks on variables schema."""
        if not memory.memory_id:
            raise MemoryEngineError("Memory validation failed: Missing Memory ID.")

        if memory.version != "1.0.0":
            raise MemoryEngineError(
                f"Unsupported memory schema version compatibility: '{memory.version}'."
            )

        if not memory.source:
            raise MemoryEngineError("Memory validation failed: Missing Source descriptor.")


class MemoryRegistry:
    """Thread-safe catalog for registered memory objects references."""

    def __init__(self) -> None:
        self.memories: dict[str, MemoryObject] = {}
        self.lock = threading.Lock()

    def register(self, memory: MemoryObject) -> None:
        """Register object reference thread-safely."""
        with self.lock:
            if memory.memory_id in self.memories:
                raise MemoryEngineError(
                    f"Memory with ID '{memory.memory_id}' is already registered."
                )
            self.memories[memory.memory_id] = memory

    def get(self, memory_id: str) -> MemoryObject | None:
        """Fetch memory object matching target identifier."""
        with self.lock:
            return self.memories.get(memory_id)

    def list_all(self) -> list[MemoryObject]:
        """Return lists of all currently registered memories."""
        with self.lock:
            return list(self.memories.values())

    def remove(self, memory_id: str) -> None:
        """Remove memory object matching target identifier."""
        with self.lock:
            if memory_id in self.memories:
                del self.memories[memory_id]


class MemoryLifecycleManager:
    """Drives state transitions through valid state machines setups."""

    # Valid transitions dictionary maps
    _VALID_TRANSITIONS: ClassVar[dict[MemoryState, set[MemoryState]]] = {
        MemoryState.CREATED: {MemoryState.VALIDATED},
        MemoryState.VALIDATED: {MemoryState.ACTIVE},
        MemoryState.ACTIVE: {MemoryState.ARCHIVED, MemoryState.EXPIRED, MemoryState.DELETED},
        MemoryState.ARCHIVED: {MemoryState.DELETED},
        MemoryState.EXPIRED: {MemoryState.DELETED},
        MemoryState.DELETED: set(),
    }

    def transition_state(self, memory: MemoryObject, target: MemoryState) -> None:
        """Verify transitions validity and update states flags."""
        allowed = self._VALID_TRANSITIONS.get(memory.state, set())
        if target not in allowed:
            raise MemoryEngineError(
                f"Invalid memory state transition proposed: {memory.state.name} -> {target.name}"
            )
        memory.state = target


class MemoryOrchestrator:
    """Unified entry coordinator for Memory Engine Foundation."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.validator = MemoryValidator()
        self.memory_registry = MemoryRegistry()
        self.lifecycle_manager = MemoryLifecycleManager()

    def create_memory(
        self,
        memory_id: str,
        memory_type: MemoryType,
        source: str,
        owner: str,
        tags: list[str],
        metadata: dict[str, Any],
        version: str = "1.0.0",
    ) -> MemoryObject:
        """Assemble memory model, perform validation checks, and register thread-safely."""
        mem = MemoryObject(
            memory_id=memory_id,
            memory_type=memory_type,
            version=version,
            source=source,
            owner=owner,
            tags=tags,
            metadata=metadata,
        )

        self.event_bus.publish_sync(
            Event(
                name="memory.created",
                category="Memory",
                source="MemoryOrchestrator",
                payload={"memory_id": memory_id, "type": memory_type.name},
            )
        )

        # 1. Validate Memory
        self.validator.validate(mem)
        self.lifecycle_manager.transition_state(mem, MemoryState.VALIDATED)

        self.event_bus.publish_sync(
            Event(
                name="memory.validated",
                category="Memory",
                source="MemoryOrchestrator",
                payload={"memory_id": memory_id},
            )
        )

        # 2. Transition Active & Register
        self.lifecycle_manager.transition_state(mem, MemoryState.ACTIVE)
        self.memory_registry.register(mem)

        self.event_bus.publish_sync(
            Event(
                name="memory.registered",
                category="Memory",
                source="MemoryOrchestrator",
                payload={"memory_id": memory_id},
            )
        )

        return mem

    def archive_memory(self, memory_id: str) -> None:
        """Transition target memory into ARCHIVED state."""
        mem = self.memory_registry.get(memory_id)
        if not mem:
            raise MemoryEngineError(f"Memory with ID '{memory_id}' not found for archive.")

        self.lifecycle_manager.transition_state(mem, MemoryState.ARCHIVED)

        self.event_bus.publish_sync(
            Event(
                name="memory.archived",
                category="Memory",
                source="MemoryOrchestrator",
                payload={"memory_id": memory_id},
            )
        )

    def delete_memory(self, memory_id: str) -> None:
        """Transition target memory into DELETED state and remove from registry catalog."""
        mem = self.memory_registry.get(memory_id)
        if not mem:
            raise MemoryEngineError(f"Memory with ID '{memory_id}' not found for delete.")

        self.lifecycle_manager.transition_state(mem, MemoryState.DELETED)
        self.memory_registry.remove(memory_id)

        self.event_bus.publish_sync(
            Event(
                name="memory.deleted",
                category="Memory",
                source="MemoryOrchestrator",
                payload={"memory_id": memory_id},
            )
        )
