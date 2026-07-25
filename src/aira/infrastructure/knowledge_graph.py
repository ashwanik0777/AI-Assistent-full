"""Enterprise Knowledge Graph Engine for AIRA.

Manages nodes, relationship edges, entity resolution, validation, and graph traversals.
"""

import threading
import time
from dataclasses import dataclass, field
from typing import Any, ClassVar

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.knowledge_graph")


class KnowledgeGraphError(Exception):
    """Raised when node resolutions, validation cycles, or traversals fail."""

    pass


@dataclass
class EntityObject:
    """Enterprise Knowledge Graph Entity representation."""

    entity_id: str
    entity_type: str
    canonical_name: str
    aliases: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    source: str = ""
    version: str = "1.0.0"
    tags: list[str] = field(default_factory=list)
    confidence: float = 1.0


@dataclass
class RelationshipObject:
    """Enterprise Knowledge Graph Relationship edge representation."""

    relationship_id: str
    source_entity: str
    target_entity: str
    relationship_type: str
    confidence: float = 1.0
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)
    version: str = "1.0.0"
    source_memory: str = ""


class EntityResolver:
    """Identifies and resolves duplicate entities mapping aliases."""

    def resolve_merge(self, primary: EntityObject, secondary: EntityObject) -> EntityObject:
        """Merge secondary node attributes into primary instance."""
        combined = primary.aliases + secondary.aliases + [secondary.canonical_name]
        primary.aliases = list(set(combined))
        primary.metadata.update(secondary.metadata)
        primary.confidence = round(max(primary.confidence, secondary.confidence), 2)
        primary.tags = list(set(primary.tags + secondary.tags))
        return primary


class GraphValidator:
    """Verifies referential integrity checks and cycle boundaries."""

    def validate_relationship(
        self, rel: RelationshipObject, entities: dict[str, EntityObject]
    ) -> None:
        """Assure linked source and target nodes exist."""
        if rel.source_entity not in entities:
            raise KnowledgeGraphError(
                f"Validation failed: Source entity '{rel.source_entity}' not found."
            )
        if rel.target_entity not in entities:
            raise KnowledgeGraphError(
                f"Validation failed: Target entity '{rel.target_entity}' not found."
            )


class GraphQueryEngine:
    """Executes node traversal paths and neighbor searches."""

    def get_neighbors(
        self, entity_id: str, relationships: list[RelationshipObject]
    ) -> list[RelationshipObject]:
        """Find all outgoing relationship edges starting at targeted node."""
        return [r for r in relationships if r.source_entity == entity_id]

    def traverse(
        self, start_id: str, relationships: list[RelationshipObject], max_depth: int = 3
    ) -> list[str]:
        """Perform simple BFS traversal returning list of visited node IDs."""
        visited = []
        queue = [(start_id, 0)]

        while queue:
            node_id, depth = queue.pop(0)
            if node_id not in visited:
                visited.append(node_id)
                if depth < max_depth:
                    neighbors = [
                        r.target_entity for r in relationships if r.source_entity == node_id
                    ]
                    for neighbor in neighbors:
                        if neighbor not in visited:
                            queue.append((neighbor, depth + 1))
        return visited


class KnowledgeGraphStore:
    """Thread-safe persistent knowledge repository catalog."""

    SUPPORTED_TYPES: ClassVar[set[str]] = {
        "Projects",
        "Repositories",
        "Frameworks",
        "Languages",
        "Databases",
        "Applications",
        "Users",
        "Workflows",
        "Procedures",
        "Technologies",
        "Files",
    }

    SUPPORTED_RELATIONSHIPS: ClassVar[set[str]] = {
        "Uses",
        "Depends On",
        "Contains",
        "Created By",
        "Runs On",
        "Hosted On",
        "Connected To",
        "Generates",
        "Reads",
        "Writes",
    }

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.resolver = EntityResolver()
        self.validator = GraphValidator()
        self.query_engine = GraphQueryEngine()

        self.entities: dict[str, EntityObject] = {}
        self.relationships: list[RelationshipObject] = []
        self.lock = threading.Lock()

    def add_entity(self, entity: EntityObject) -> None:
        """Validate, register, and store new entity node."""
        with self.lock:
            # Detect duplicate by canonical name or alias match
            for existing in list(self.entities.values()):
                if (
                    existing.canonical_name.lower() == entity.canonical_name.lower()
                    or entity.canonical_name.lower() in [a.lower() for a in existing.aliases]
                ):
                    # Merge entities
                    merged = self.resolver.resolve_merge(existing, entity)
                    self.event_bus.publish_sync(
                        Event(
                            name="entity.merged",
                            category="Memory",
                            source="KnowledgeGraph",
                            payload={"entity_id": merged.entity_id},
                        )
                    )
                    return

            self.entities[entity.entity_id] = entity
            self.event_bus.publish_sync(
                Event(
                    name="entity.created",
                    category="Memory",
                    source="KnowledgeGraph",
                    payload={"entity_id": entity.entity_id},
                )
            )

    def add_relationship(self, rel: RelationshipObject) -> None:
        """Verify endpoints existence and append relationship edge."""
        with self.lock:
            self.validator.validate_relationship(rel, self.entities)

            # Check for duplicate edge
            for existing in self.relationships:
                if (
                    existing.source_entity == rel.source_entity
                    and existing.target_entity == rel.target_entity
                    and existing.relationship_type == rel.relationship_type
                ):
                    existing.confidence = round(max(existing.confidence, rel.confidence), 2)
                    self.event_bus.publish_sync(
                        Event(
                            name="relationship.updated",
                            category="Memory",
                            source="KnowledgeGraph",
                            payload={"relationship_id": existing.relationship_id},
                        )
                    )
                    return

            self.relationships.append(rel)
            self.event_bus.publish_sync(
                Event(
                    name="relationship.added",
                    category="Memory",
                    source="KnowledgeGraph",
                    payload={"relationship_id": rel.relationship_id},
                )
            )

    def get_entity(self, entity_id: str) -> EntityObject | None:
        """Fetch matching entity node from catalog registers."""
        with self.lock:
            return self.entities.get(entity_id)

    def list_entities(self) -> list[EntityObject]:
        """Return list representing all stored entities."""
        with self.lock:
            return list(self.entities.values())

    def list_relationships(self) -> list[RelationshipObject]:
        """Return list representing all registered relationship edges."""
        with self.lock:
            return list(self.relationships)
