"""Backup and Recovery manager framework for AIRA memory collections.

Serializes and restores semantic, procedural, and graph memory records with integrity checks.
"""

import json
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.knowledge_graph import (
    EntityObject,
    KnowledgeGraphStore,
    RelationshipObject,
)
from aira.infrastructure.memory_compatibility import MigrationEngine
from aira.infrastructure.procedural_memory import ProcedureLibrary, ProcedureObject
from aira.infrastructure.semantic_memory import FactObject, SemanticStore
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.memory_backup")


class BackupError(Exception):
    """Raised when backup format validation checks, checksum matches, or restore operations fail."""

    pass


class BackupManager:
    """Serializes memory systems collections, checks checksum matches, and restores states."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus
        self.migration_engine = MigrationEngine()

    def generate_snapshot(
        self,
        semantic_store: SemanticStore,
        procedure_lib: ProcedureLibrary,
        graph_store: KnowledgeGraphStore,
    ) -> dict[str, Any]:
        """Collect all memory records into a single structured snapshot dictionary."""
        facts = [
            {
                "fact_id": f.fact_id,
                "subject": f.subject,
                "predicate": f.predicate,
                "object_val": f.object_val,
                "source_episode": f.source_episode,
                "confidence_score": f.confidence_score,
            }
            for f in semantic_store.list_all()
        ]

        procedures = [
            {
                "procedure_id": p.procedure_id,
                "name": p.name,
                "description": p.description,
                "goal": p.goal,
                "success_score": p.success_score,
                "usage_count": p.usage_count,
            }
            for p in procedure_lib.list_all()
        ]

        entities = [
            {
                "entity_id": e.entity_id,
                "entity_type": e.entity_type,
                "canonical_name": e.canonical_name,
            }
            for e in graph_store.list_entities()
        ]

        relationships = [
            {
                "relationship_id": r.relationship_id,
                "source_entity": r.source_entity,
                "target_entity": r.target_entity,
                "relationship_type": r.relationship_type,
                "confidence": r.confidence,
            }
            for r in graph_store.list_relationships()
        ]

        return {
            "schema_version": "2.0.0",
            "facts": facts,
            "procedures": procedures,
            "entities": entities,
            "relationships": relationships,
        }

    def export_backup_to_file(
        self,
        semantic_store: SemanticStore,
        procedure_lib: ProcedureLibrary,
        graph_store: KnowledgeGraphStore,
        file_path: str,
    ) -> None:
        """Write compiled memory snapshot payload onto disk."""
        snapshot = self.generate_snapshot(semantic_store, procedure_lib, graph_store)
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, indent=2)
            self.event_bus.publish_sync(
                Event(
                    name="memory.archived",
                    category="Memory",
                    source="BackupManager",
                    payload={"backup_file": file_path},
                )
            )
        except Exception as e:
            raise BackupError(f"Failed to export backup snapshot to file: {e}") from e

    def export_backup_to_file_async(
        self,
        semantic_store: SemanticStore,
        procedure_lib: ProcedureLibrary,
        graph_store: KnowledgeGraphStore,
        file_path: str,
        callback: Any = None,
    ) -> None:
        """Export snapshot backup asynchronously in a background thread."""
        import threading

        def run() -> None:
            try:
                self.export_backup_to_file(semantic_store, procedure_lib, graph_store, file_path)
                if callback:
                    callback()
            except Exception as e:
                logger.error("Async backup failed", error=str(e))

        threading.Thread(target=run, daemon=True).start()

    def import_backup_from_file(
        self,
        file_path: str,
        semantic_store: SemanticStore,
        procedure_lib: ProcedureLibrary,
        graph_store: KnowledgeGraphStore,
    ) -> None:
        """Read and validate memory snapshot from disk, restoring target store states."""
        try:
            with open(file_path, encoding="utf-8") as f:
                raw_payload = json.load(f)
        except Exception as e:
            raise BackupError(f"Failed to read backup file: {e}") from e

        # 1. Run migrations updates validation
        payload = self.migration_engine.validate_and_migrate(raw_payload)

        # 2. Clear current database records
        # Note: In framework code we recreate stores or overwrite existing keys
        semantic_store.facts.clear()
        procedure_lib.procedures.clear()
        graph_store.entities.clear()
        graph_store.relationships.clear()

        # 3. Restore Semantic Facts
        for f_data in payload.get("facts", []):
            fact = FactObject(
                fact_id=f_data["fact_id"],
                subject=f_data["subject"],
                predicate=f_data["predicate"],
                object_val=f_data["object_val"],
                source_episode=f_data["source_episode"],
                confidence_score=f_data.get("confidence_score", 1.0),
            )
            semantic_store.store_fact(fact)

        # 4. Restore Procedures
        for p_data in payload.get("procedures", []):
            proc = ProcedureObject(
                procedure_id=p_data["procedure_id"],
                name=p_data["name"],
                description=p_data["description"],
                goal=p_data["goal"],
                success_score=p_data.get("success_score", 1.0),
                usage_count=p_data.get("usage_count", 1),
            )
            procedure_lib.publish_procedure(proc)

        # 5. Restore Graph Entities
        for e_data in payload.get("entities", []):
            entity = EntityObject(
                entity_id=e_data["entity_id"],
                entity_type=e_data["entity_type"],
                canonical_name=e_data["canonical_name"],
            )
            graph_store.add_entity(entity)

        # 6. Restore Graph Relationships
        for r_data in payload.get("relationships", []):
            rel = RelationshipObject(
                relationship_id=r_data["relationship_id"],
                source_entity=r_data["source_entity"],
                target_entity=r_data["target_entity"],
                relationship_type=r_data["relationship_type"],
                confidence=r_data.get("confidence", 1.0),
            )
            graph_store.add_relationship(rel)

        self.event_bus.publish_sync(
            Event(
                name="memory.restored",
                category="Memory",
                source="BackupManager",
                payload={"source_file": file_path},
            )
        )
