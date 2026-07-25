"""Enterprise Perception Engine & Observation Framework for AIRA.

Provides core dataclass definitions, validators, registries, and graphs for perception telemetry.
"""

import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.perception_engine")


class PerceptionEngineError(Exception):
    """Raised when perception engine operations or validation constraints fail."""

    pass


class ObservationState(StrEnum):
    """Represents the lifecycle transition state of an Observation Object."""

    CREATED = "Created"
    VALIDATED = "Validated"
    ACTIVE = "Active"
    CACHED = "Cached"
    ARCHIVED = "Archived"
    DELETED = "Deleted"


@dataclass
class ObservationObject:
    """Standardized representation of a single perception capture instance."""

    observation_id: str
    source: str  # Screen, Browser, OCR, Desktop, Accessibility, Clipboard, Documents, Images
    observation_type: str
    confidence: float  # 0.0 to 1.0
    structured_content: dict[str, Any]
    # Relationships list: [{'target_id': target_id, 'type': relationship_type}]
    relationships: list[dict[str, str]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    state: ObservationState = ObservationState.CREATED
    version: str = "1.0.0"


class ObservationBuilder:
    """Builder assistant to simplify standardized Observation Object creations."""

    def __init__(self, observation_id: str, source: str, observation_type: str) -> None:
        self.observation_id = observation_id
        self.source = source
        self.observation_type = observation_type
        self.confidence = 1.0
        self.structured_content: dict[str, Any] = {}
        self.relationships: list[dict[str, str]] = []
        self.metadata: dict[str, Any] = {}

    def set_confidence(self, confidence: float) -> "ObservationBuilder":
        """Set detection confidence score."""
        self.confidence = confidence
        return self

    def set_content(self, content: dict[str, Any]) -> "ObservationBuilder":
        """Set structured content payload."""
        self.structured_content = content
        return self

    def add_relationship(self, target_id: str, relationship_type: str) -> "ObservationBuilder":
        """Add relationship pointer link to another observation node."""
        self.relationships.append({"target_id": target_id, "type": relationship_type})
        return self

    def set_metadata(self, key: str, value: Any) -> "ObservationBuilder":
        """Set custom metadata key values."""
        self.metadata[key] = value
        return self

    def build(self) -> ObservationObject:
        """Compile builder properties into finalized ObservationObject."""
        return ObservationObject(
            observation_id=self.observation_id,
            source=self.source,
            observation_type=self.observation_type,
            confidence=self.confidence,
            structured_content=self.structured_content,
            relationships=self.relationships,
            metadata=self.metadata,
        )


class ObservationValidator:
    """Enforces validation rules on Observation Objects properties."""

    def validate(self, observation: ObservationObject) -> None:
        """Enforce validation rules checking details metadata."""
        if not observation.observation_id:
            raise PerceptionEngineError("Observation ID is required.")

        if not observation.source:
            raise PerceptionEngineError("Observation source is required.")

        if not (0.0 <= observation.confidence <= 1.0):
            raise PerceptionEngineError("Observation confidence must be between 0.0 and 1.0.")

        valid_sources = {
            "Screen",
            "Browser",
            "OCR",
            "Desktop",
            "Accessibility",
            "Clipboard",
            "Documents",
            "Images",
        }
        if observation.source not in valid_sources:
            raise PerceptionEngineError(f"Unsupported observation source: {observation.source}")


class ObservationRegistry:
    """Thread-safe catalog repository storing active observation objects."""

    def __init__(self) -> None:
        self.observations: dict[str, ObservationObject] = {}

    def register(self, observation: ObservationObject) -> None:
        """Register node in catalog."""
        self.observations[observation.observation_id] = observation

    def get(self, observation_id: str) -> ObservationObject | None:
        """Query catalog store by ID."""
        return self.observations.get(observation_id)


class ObservationGraph:
    """Tracks relationship connection edges linking window application layers."""

    def __init__(self) -> None:
        self.nodes: dict[str, ObservationObject] = {}
        # Map of node_id -> list of target_ids
        self.edges: dict[str, list[str]] = {}

    def add_node(self, observation: ObservationObject) -> None:
        """Register node in graph."""
        self.nodes[observation.observation_id] = observation
        if observation.observation_id not in self.edges:
            self.edges[observation.observation_id] = []

        # Parse pre-existing relationships links
        for rel in observation.relationships:
            target_id = rel.get("target_id")
            if target_id:
                self.link(observation.observation_id, target_id)

    def link(self, source_id: str, target_id: str) -> None:
        """Link relationship edge between two nodes."""
        if source_id in self.edges and target_id not in self.edges[source_id]:
            self.edges[source_id].append(target_id)

    def get_related_nodes(self, node_id: str) -> list[ObservationObject]:
        """Query graph edges to return connected observation instances."""
        targets = self.edges.get(node_id, [])
        return [self.nodes[tid] for tid in targets if tid in self.nodes]


class ObservationSession:
    """Scoped session context containing active workspace and application properties."""

    def __init__(self, session_id: str, workspace_id: str) -> None:
        self.session_id = session_id
        self.workspace_id = workspace_id
        self.active_observations: list[str] = []
        self.metadata: dict[str, Any] = {}
        self.is_active = True

    def associate_observation(self, observation_id: str) -> None:
        """Map active observation identifier to session history list."""
        if observation_id not in self.active_observations:
            self.active_observations.append(observation_id)


class PerceptionEngine:
    """Primary coordinator managing perception workflows, sessions, and registry updates."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.validator = ObservationValidator()
        self.observation_registry = ObservationRegistry()
        self.graph = ObservationGraph()
        self.active_sessions: dict[str, ObservationSession] = {}

    def start_session(self, session_id: str, workspace_id: str) -> ObservationSession:
        """Spawn active session context and notify Event Bus."""
        if session_id in self.active_sessions:
            raise PerceptionEngineError(f"Session '{session_id}' already exists.")

        session = ObservationSession(session_id, workspace_id)
        self.active_sessions[session_id] = session

        self.event_bus.publish_sync(
            Event(
                name="session.started",
                category="Perception",
                source="PerceptionEngine",
                payload={"session_id": session_id, "workspace_id": workspace_id},
            )
        )
        return session

    def close_session(self, session_id: str) -> None:
        """Deactivate session state and notify Event Bus."""
        if session_id not in self.active_sessions:
            raise PerceptionEngineError(f"Session '{session_id}' not found.")

        session = self.active_sessions[session_id]
        session.is_active = False

        self.event_bus.publish_sync(
            Event(
                name="session.closed",
                category="Perception",
                source="PerceptionEngine",
                payload={"session_id": session_id},
            )
        )

    def process_observation(
        self, observation: ObservationObject, session_id: str | None = None
    ) -> None:
        """Validate, register, update graphs status, and publish event milestones."""
        # 1. Create event
        self.event_bus.publish_sync(
            Event(
                name="observation.created",
                category="Perception",
                source="PerceptionEngine",
                payload={"observation_id": observation.observation_id},
            )
        )

        # 2. Validate
        self.validator.validate(observation)
        observation.state = ObservationState.VALIDATED

        self.event_bus.publish_sync(
            Event(
                name="observation.validated",
                category="Perception",
                source="PerceptionEngine",
                payload={"observation_id": observation.observation_id},
            )
        )

        # 3. Register & Graph Updates
        observation.state = ObservationState.ACTIVE
        self.observation_registry.register(observation)
        self.graph.add_node(observation)

        if session_id and session_id in self.active_sessions:
            self.active_sessions[session_id].associate_observation(observation.observation_id)

        self.event_bus.publish_sync(
            Event(
                name="observation.activated",
                category="Perception",
                source="PerceptionEngine",
                payload={"observation_id": observation.observation_id},
            )
        )

    def archive_observation(self, observation_id: str) -> None:
        """Mark observation state transition to archived."""
        obs = self.observation_registry.get(observation_id)
        if not obs:
            raise PerceptionEngineError(f"Observation '{observation_id}' not found in registry.")

        obs.state = ObservationState.ARCHIVED

        self.event_bus.publish_sync(
            Event(
                name="observation.archived",
                category="Perception",
                source="PerceptionEngine",
                payload={"observation_id": observation_id},
            )
        )
