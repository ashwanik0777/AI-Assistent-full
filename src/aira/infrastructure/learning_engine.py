"""Enterprise Memory Consolidation & Learning Engine for AIRA.

Processes memory candidates, enforces learning policies, promotes items, and decays expired data.
"""

import threading
import time
from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.knowledge_graph import (
    EntityObject,
    KnowledgeGraphStore,
    RelationshipObject,
)
from aira.infrastructure.procedural_memory import ProcedureLibrary, ProcedureObject
from aira.infrastructure.semantic_memory import FactObject, SemanticStore
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.learning_engine")


class LearningEngineError(Exception):
    """Raised when validation failures, policy violations, or promotion conflicts occur."""

    pass


@dataclass
class FactCandidate:
    """Wrapper holding proposed semantic fact candidate."""

    candidate_id: str
    fact: FactObject
    created_at: float = field(default_factory=time.time)
    usage_count: int = 1


@dataclass
class ProcedureCandidate:
    """Wrapper holding proposed procedural method candidate."""

    candidate_id: str
    procedure: ProcedureObject
    created_at: float = field(default_factory=time.time)
    usage_count: int = 1


@dataclass
class RelationshipCandidate:
    """Wrapper holding proposed Knowledge Graph edge candidate."""

    candidate_id: str
    relationship: RelationshipObject
    created_at: float = field(default_factory=time.time)
    usage_count: int = 1


class LearningPolicyEngine:
    """Enforces repeated successes, usage counts, and confidence thresholds."""

    def __init__(self, min_confidence: float = 0.8, min_usage: int = 2) -> None:
        self.min_confidence = min_confidence
        self.min_usage = min_usage

    def evaluate_fact(self, candidate: FactCandidate) -> bool:
        """Approve facts meeting confidence thresholds."""
        return candidate.fact.confidence_score >= self.min_confidence

    def evaluate_procedure(self, candidate: ProcedureCandidate) -> bool:
        """Approve procedures exceeding success scores and usage count criteria."""
        proc = candidate.procedure
        return proc.success_score >= 0.8 and candidate.usage_count >= self.min_usage

    def evaluate_relationship(self, candidate: RelationshipCandidate) -> bool:
        """Approve graph relationships satisfying confidence thresholds."""
        return candidate.relationship.confidence >= self.min_confidence


class KnowledgePromotionEngine:
    """Registers approved candidates directly into production stores."""

    def promote_fact(self, candidate: FactCandidate, store: SemanticStore) -> None:
        """Publish fact to semantic memory store."""
        store.store_fact(candidate.fact)

    def promote_procedure(self, candidate: ProcedureCandidate, lib: ProcedureLibrary) -> None:
        """Publish generalized procedure template to library catalog."""
        lib.publish_procedure(candidate.procedure)

    def promote_relationship(
        self, candidate: RelationshipCandidate, graph: KnowledgeGraphStore
    ) -> None:
        """Publish entity nodes and relationship edges to graph store."""
        # 1. Ensure linked nodes are registered in the graph store first
        src_entity = EntityObject(
            entity_id=candidate.relationship.source_entity,
            entity_type="Projects",
            canonical_name=candidate.relationship.source_entity,
        )
        target_entity = EntityObject(
            entity_id=candidate.relationship.target_entity,
            entity_type="Databases",
            canonical_name=candidate.relationship.target_entity,
        )
        graph.add_entity(src_entity)
        graph.add_entity(target_entity)

        # 2. Add relationship edge
        graph.add_relationship(candidate.relationship)


class MemoryDecayManager:
    """Prunes or archives candidate records exceeding time-to-live expirations."""

    def __init__(self, ttl_seconds: float = 3600.0) -> None:
        self.ttl_seconds = ttl_seconds

    def prune_candidates(self, candidates: dict[str, Any], event_bus: EventBus) -> list[str]:
        """Iterate candidates removing expired instances."""
        now = time.time()
        expired_keys = []

        for key, candidate in list(candidates.items()):
            age = now - candidate.created_at
            if age > self.ttl_seconds:
                expired_keys.append(key)
                candidates.pop(key)
                event_bus.publish_sync(
                    Event(
                        name="memory.pruned",
                        category="Memory",
                        source="DecayManager",
                        payload={"candidate_id": candidate.candidate_id},
                    )
                )

        return expired_keys


class MemoryConsolidationEngine:
    """Orchestrates candidate registrations, policy runs, and decays sweeps."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.policy_engine = LearningPolicyEngine()
        self.promotion_engine = KnowledgePromotionEngine()
        self.decay_manager = MemoryDecayManager()

        self.fact_candidates: dict[str, FactCandidate] = {}
        self.procedure_candidates: dict[str, ProcedureCandidate] = {}
        self.relationship_candidates: dict[str, RelationshipCandidate] = {}
        self.lock = threading.Lock()

    def propose_fact(self, fact: FactObject) -> None:
        """Register fact candidate and check immediate promotion eligibility."""
        with self.lock:
            candidate = FactCandidate(candidate_id=fact.fact_id, fact=fact)
            self.fact_candidates[fact.fact_id] = candidate
            self.event_bus.publish_sync(
                Event(
                    name="candidate.created",
                    category="Memory",
                    source="ConsolidationEngine",
                    payload={"candidate_id": fact.fact_id},
                )
            )

    def propose_procedure(self, proc: ProcedureObject) -> None:
        """Register procedure candidate checking usage threshold requirements."""
        with self.lock:
            # Check for existing duplicate candidate to increment usage count
            if proc.procedure_id in self.procedure_candidates:
                candidate = self.procedure_candidates[proc.procedure_id]
                candidate.usage_count += 1
                candidate.procedure.usage_count = candidate.usage_count
            else:
                candidate = ProcedureCandidate(candidate_id=proc.procedure_id, procedure=proc)
                self.procedure_candidates[proc.procedure_id] = candidate

            self.event_bus.publish_sync(
                Event(
                    name="candidate.created",
                    category="Memory",
                    source="ConsolidationEngine",
                    payload={"candidate_id": proc.procedure_id, "usage": candidate.usage_count},
                )
            )

    def propose_relationship(self, rel: RelationshipObject) -> None:
        """Register relationship edge candidate."""
        with self.lock:
            candidate = RelationshipCandidate(candidate_id=rel.relationship_id, relationship=rel)
            self.relationship_candidates[rel.relationship_id] = candidate
            self.event_bus.publish_sync(
                Event(
                    name="candidate.created",
                    category="Memory",
                    source="ConsolidationEngine",
                    payload={"candidate_id": rel.relationship_id},
                )
            )

    def run_consolidation(
        self,
        semantic_store: SemanticStore,
        procedure_lib: ProcedureLibrary,
        graph_store: KnowledgeGraphStore,
    ) -> None:
        """Trigger consolidation sweep evaluating candidates against policy rules."""
        with self.lock:
            self.event_bus.publish_sync(
                Event(
                    name="consolidation.started",
                    category="Memory",
                    source="ConsolidationEngine",
                    payload={},
                )
            )

            # 1. Consolidate Facts
            for key, cand_f in list(self.fact_candidates.items()):
                if self.policy_engine.evaluate_fact(cand_f):
                    self.promotion_engine.promote_fact(cand_f, semantic_store)
                    self.fact_candidates.pop(key)
                    self.event_bus.publish_sync(
                        Event(
                            name="candidate.promoted",
                            category="Memory",
                            source="ConsolidationEngine",
                            payload={"candidate_id": cand_f.candidate_id, "type": "Fact"},
                        )
                    )

            # 2. Consolidate Procedures
            for key, cand_p in list(self.procedure_candidates.items()):
                if self.policy_engine.evaluate_procedure(cand_p):
                    self.promotion_engine.promote_procedure(cand_p, procedure_lib)
                    self.procedure_candidates.pop(key)
                    self.event_bus.publish_sync(
                        Event(
                            name="candidate.promoted",
                            category="Memory",
                            source="ConsolidationEngine",
                            payload={"candidate_id": cand_p.candidate_id, "type": "Procedure"},
                        )
                    )

            # 3. Consolidate Relationships
            for key, cand_r in list(self.relationship_candidates.items()):
                if self.policy_engine.evaluate_relationship(cand_r):
                    self.promotion_engine.promote_relationship(cand_r, graph_store)
                    self.relationship_candidates.pop(key)
                    self.event_bus.publish_sync(
                        Event(
                            name="candidate.promoted",
                            category="Memory",
                            source="ConsolidationEngine",
                            payload={
                                "candidate_id": cand_r.relationship.relationship_id,
                                "type": "Relationship",
                            },
                        )
                    )

            # 4. Pruning Expirations Sweep
            self.decay_manager.prune_candidates(self.fact_candidates, self.event_bus)
            self.decay_manager.prune_candidates(self.procedure_candidates, self.event_bus)
            self.decay_manager.prune_candidates(self.relationship_candidates, self.event_bus)

            self.event_bus.publish_sync(
                Event(
                    name="learning.completed",
                    category="Memory",
                    source="ConsolidationEngine",
                    payload={},
                )
            )
