"""Enterprise Memory Intelligence, Retention & Knowledge Lifecycle Platform for AIRA.

Provides memory importance engines, retention checkers, consolidation tools, and conflict resolvers.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.memory_intelligence")


class MemoryIntelligenceError(Exception):
    """Base exception raised for retention errors, consolidation clashes, or archive failures."""

    pass


@dataclass
class MemoryIntelligenceRecord:
    """Record representing a structured metadata wrapper around persistent memory facts."""

    memory_id: str
    memory_type: str
    importance_score: float
    confidence: float
    retention_policy: str  # Permanent, Long-Term, Short-Term, Session, Temporary
    lifecycle_state: str = "Active"  # Active, Inactive, Archived, Expired
    evidence_links: list[str] = field(default_factory=list)
    quality_score: float = 1.0
    version: int = 1
    facts: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class MemoryImportanceEngine:
    """Calculates relative memory records importance based on metadata properties."""

    def score_importance(self, facts_count: int, confidence: float) -> float:
        """Calculate score metric (ratio of facts count multiplied by confidence level)."""
        base = facts_count * 0.25 + confidence * 0.5
        return min(max(base, 0.0), 1.0)


class RetentionPolicyEngine:
    """Evaluates retention criteria and checks lifecycle transitions correctness."""

    def is_expired(self, record: MemoryIntelligenceRecord, age_seconds: float) -> bool:
        """Return True if age exceeds the retention policy rules threshold limit."""
        policy_limits = {
            "Temporary": 60.0,
            "Session": 3600.0,
            "Short-Term": 86400.0,
            "Long-Term": 2592000.0,
            "Permanent": float("inf"),
        }
        limit = policy_limits.get(record.retention_policy, float("inf"))
        return age_seconds > limit


class MemoryConsolidationEngine:
    """Detects and merges duplicate context segments to optimize storage."""

    def consolidate(
        self, primary: MemoryIntelligenceRecord, secondary: MemoryIntelligenceRecord
    ) -> None:
        """Consolidate facts, append references, and increase confidence."""
        # Add new facts
        for fact in secondary.facts:
            if fact not in primary.facts:
                primary.facts.append(fact)

        # Merge evidence refs
        for ref in secondary.evidence_links:
            if ref not in primary.evidence_links:
                primary.evidence_links.append(ref)

        # Increment version and confidence
        primary.version += 1
        primary.confidence = min(primary.confidence + 0.1, 1.0)


class MemoryConflictResolver:
    """Composes detailed conflict warnings if factual conflicts are discovered."""

    def detect_and_report_conflict(
        self, record: MemoryIntelligenceRecord, new_fact: str
    ) -> str | None:
        """Evaluate new fact and return conflict explanation details if conflict exists."""
        # Simple string-level contradiction checker for demo purposes
        for fact in record.facts:
            is_deadline = "deadline" in fact.lower() and "deadline" in new_fact.lower()
            if is_deadline and fact.lower() != new_fact.lower():
                return (
                    f"Conflict detected: Memory has '{fact}', "
                    f"but new evidence suggests '{new_fact}'."
                )
        return None


class MemoryArchiveManager:
    """Manages backing up memories to archive and restoring from it."""

    def __init__(self) -> None:
        self.archived_records: dict[str, MemoryIntelligenceRecord] = {}

    def archive(self, record: MemoryIntelligenceRecord) -> None:
        """Add copy of record to archives and set state to Archived."""
        record.lifecycle_state = "Archived"
        self.archived_records[record.memory_id] = record

    def restore(self, record: MemoryIntelligenceRecord) -> None:
        """Set state to Active and evict from archives."""
        record.lifecycle_state = "Active"
        self.archived_records.pop(record.memory_id, None)


class MemoryIntelligenceManager:
    """Coordinating manager verifying memories, routing rollbacks, and resolving conflicts."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.importance_engine = MemoryImportanceEngine()
        self.retention_engine = RetentionPolicyEngine()
        self.consolidation_engine = MemoryConsolidationEngine()
        self.conflict_resolver = MemoryConflictResolver()
        self.archive_manager = MemoryArchiveManager()

        self.active_memories: dict[str, MemoryIntelligenceRecord] = {}

    def create_memory(
        self,
        memory_id: str,
        memory_type: str,
        confidence: float,
        retention_policy: str,
        facts: list[str],
        evidence_links: list[str],
    ) -> MemoryIntelligenceRecord:
        """Compute importance, validate properties, register, and publish created events."""
        importance = self.importance_engine.score_importance(len(facts), confidence)

        record = MemoryIntelligenceRecord(
            memory_id=memory_id,
            memory_type=memory_type,
            importance_score=importance,
            confidence=confidence,
            retention_policy=retention_policy,
            facts=facts.copy(),
            evidence_links=evidence_links.copy(),
        )

        self.active_memories[memory_id] = record

        self.event_bus.publish_sync(
            Event(
                name="memory.created",
                category="MemoryIntelligence",
                source="MemoryIntelligenceManager",
                payload={"memory_id": memory_id, "type": memory_type},
            )
        )

        return record

    def consolidate_records(self, primary_id: str, secondary_id: str) -> None:
        """Merge secondary record data parameters into primary slot."""
        primary = self.active_memories.get(primary_id)
        secondary = self.active_memories.get(secondary_id)

        if not primary or not secondary:
            raise MemoryIntelligenceError("Consolidation failed: Both records must exist.")

        self.consolidation_engine.consolidate(primary, secondary)

        # Remove secondary
        self.active_memories.pop(secondary_id, None)

        self.event_bus.publish_sync(
            Event(
                name="memory.consolidated",
                category="MemoryIntelligence",
                source="MemoryIntelligenceManager",
                payload={"primary_id": primary_id, "secondary_id": secondary_id},
            )
        )

    def evaluate_new_fact(self, memory_id: str, new_fact: str) -> bool:
        """Check fact against record. If conflict exists, publish warning event and return False."""
        record = self.active_memories.get(memory_id)
        if not record:
            raise MemoryIntelligenceError(f"Operation failed: Memory '{memory_id}' not found.")

        conflict = self.conflict_resolver.detect_and_report_conflict(record, new_fact)
        if conflict:
            self.event_bus.publish_sync(
                Event(
                    name="conflict.detected",
                    category="MemoryIntelligence",
                    source="MemoryIntelligenceManager",
                    payload={"memory_id": memory_id, "explanation": conflict},
                )
            )
            return False

        # Safe to append
        record.facts.append(new_fact)
        return True

    def update_retention(self, memory_id: str, policy: str) -> None:
        """Update record policy parameter."""
        record = self.active_memories.get(memory_id)
        if not record:
            raise MemoryIntelligenceError(f"Operation failed: Memory '{memory_id}' not found.")

        record.retention_policy = policy

        self.event_bus.publish_sync(
            Event(
                name="retention.updated",
                category="MemoryIntelligence",
                source="MemoryIntelligenceManager",
                payload={"memory_id": memory_id, "new_policy": policy},
            )
        )

    def archive_memory(self, memory_id: str) -> None:
        """Archive record and set state to Inactive/Archived."""
        record = self.active_memories.get(memory_id)
        if not record:
            raise MemoryIntelligenceError(f"Operation failed: Memory '{memory_id}' not found.")

        self.archive_manager.archive(record)
        # Evict from active
        self.active_memories.pop(memory_id, None)

        self.event_bus.publish_sync(
            Event(
                name="memory.archived",
                category="MemoryIntelligence",
                source="MemoryIntelligenceManager",
                payload={"memory_id": memory_id},
            )
        )

    def restore_memory(self, memory_id: str) -> None:
        """Evict record from archive back to active slot."""
        record = self.archive_manager.archived_records.get(memory_id)
        if not record:
            raise MemoryIntelligenceError(
                f"Restore failed: Record '{memory_id}' not found in archive."
            )

        self.archive_manager.restore(record)
        self.active_memories[memory_id] = record

        self.event_bus.publish_sync(
            Event(
                name="memory.restored",
                category="MemoryIntelligence",
                source="MemoryIntelligenceManager",
                payload={"memory_id": memory_id},
            )
        )
