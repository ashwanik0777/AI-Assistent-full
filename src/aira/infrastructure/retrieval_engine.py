"""Enterprise Hybrid Retrieval & Context Assembly Engine for AIRA.

Retrieves, filters, ranks, and bounds memory fragments into clean deterministic context.
"""

import threading
import time
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.episodic_memory import EpisodeObject, EpisodeStore
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.knowledge_graph import KnowledgeGraphStore, RelationshipObject
from aira.infrastructure.procedural_memory import ProcedureLibrary, ProcedureObject
from aira.infrastructure.semantic_memory import FactObject, SemanticStore
from aira.infrastructure.service_registry import ServiceRegistry
from aira.infrastructure.working_memory import WorkingMemorySession

logger = structlog.get_logger("aira.retrieval_engine")


class RetrievalEngineError(Exception):
    """Raised when memory selection, ranking computations, or context building fail."""

    pass


class RetrievalPlanner:
    """Selects which memory sub-stores to target based on query intent analysis."""

    def plan_retrieval(self, query: str) -> list[str]:
        """Inspect query terms electing relevant memory systems list."""
        stores = ["working_memory"]  # Working memory is always queried
        normalized = query.lower()

        if "database" in normalized or "fact" in normalized or "project" in normalized:
            stores.append("semantic_memory")
            stores.append("knowledge_graph")

        if "procedure" in normalized or "run" in normalized or "how to" in normalized:
            stores.append("procedural_memory")

        if "episode" in normalized or "history" in normalized or "previous" in normalized:
            stores.append("episodic_memory")

        # Fallback if no specific trigger terms matched
        if len(stores) == 1:
            stores.extend(
                ["semantic_memory", "procedural_memory", "episodic_memory", "knowledge_graph"]
            )

        return list(set(stores))


class HybridRanker:
    """Sorts items prioritizing recency, usage counts, and confidence ratings."""

    def rank_facts(self, facts: list[FactObject]) -> list[FactObject]:
        """Sort facts by confidence score descending, then timestamp descending."""
        return sorted(facts, key=lambda f: (f.confidence_score, f.timestamp), reverse=True)

    def rank_procedures(self, procedures: list[ProcedureObject]) -> list[ProcedureObject]:
        """Sort procedures by success score descending, then usage count descending."""
        return sorted(procedures, key=lambda p: (p.success_score, p.usage_count), reverse=True)

    def rank_episodes(self, episodes: list[EpisodeObject]) -> list[EpisodeObject]:
        """Sort episodes by importance score descending, then end timestamp descending."""
        return sorted(episodes, key=lambda e: (e.importance_score, e.end_time), reverse=True)


class ContextBudgetManager:
    """Clamps retrieved lists sizes to fit configurable token/object budgets."""

    def __init__(
        self,
        max_facts: int = 5,
        max_procedures: int = 3,
        max_episodes: int = 3,
        max_relationships: int = 5,
    ) -> None:
        self.max_facts = max_facts
        self.max_procedures = max_procedures
        self.max_episodes = max_episodes
        self.max_relationships = max_relationships

    def enforce_budget(
        self,
        facts: list[FactObject],
        procedures: list[ProcedureObject],
        episodes: list[EpisodeObject],
        relationships: list[RelationshipObject],
    ) -> tuple[
        list[FactObject], list[ProcedureObject], list[EpisodeObject], list[RelationshipObject]
    ]:
        """Clamp lists sizes according to max object limitations."""
        return (
            facts[: self.max_facts],
            procedures[: self.max_procedures],
            episodes[: self.max_episodes],
            relationships[: self.max_relationships],
        )


class ContextDeduplicator:
    """Removes duplicate objects having equivalent identifiers or parameters."""

    def deduplicate_facts(self, facts: list[FactObject]) -> list[FactObject]:
        """Retain only unique facts based on Subject and Predicate keys."""
        seen = set()
        deduped = []
        for f in facts:
            key = (f.subject.lower(), f.predicate.lower())
            if key not in seen:
                seen.add(key)
                deduped.append(f)
        return deduped

    def deduplicate_procedures(self, procedures: list[ProcedureObject]) -> list[ProcedureObject]:
        """Retain only unique procedures by procedure ID."""
        seen = set()
        deduped = []
        for p in procedures:
            if p.procedure_id not in seen:
                seen.add(p.procedure_id)
                deduped.append(p)
        return deduped


class ContextBuilder:
    """Aggregates and formats context fragments into clean payload strings."""

    def build_payload(
        self,
        working_vars: dict[str, Any],
        facts: list[FactObject],
        procedures: list[ProcedureObject],
        episodes: list[EpisodeObject],
        relationships: list[RelationshipObject],
    ) -> dict[str, Any]:
        """Format arrays into semantic segments mapping references."""
        facts_payload = [
            {"subject": f.subject, "predicate": f.predicate, "object": f.object_val} for f in facts
        ]

        procedures_payload = [
            {"name": p.name, "goal": p.goal, "skills": p.supported_skills} for p in procedures
        ]

        episodes_payload = [
            {"title": e.title, "outcome": e.outcome, "score": e.importance_score} for e in episodes
        ]

        relationships_payload = [
            {"source": r.source_entity, "relation": r.relationship_type, "target": r.target_entity}
            for r in relationships
        ]

        return {
            "working_variables": working_vars,
            "facts": facts_payload,
            "procedures": procedures_payload,
            "episodes": episodes_payload,
            "relationships": relationships_payload,
            "timestamp": time.time(),
        }


class HybridRetrievalEngine:
    """Orchestrates plan selections, rank evaluations, and context builds."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.planner = RetrievalPlanner()
        self.ranker = HybridRanker()
        self.budget_manager = ContextBudgetManager()
        self.deduplicator = ContextDeduplicator()
        self.builder = ContextBuilder()
        self.lock = threading.Lock()

    def assemble_context(
        self,
        query: str,
        working_session: WorkingMemorySession | None = None,
        episodic_store: EpisodeStore | None = None,
        semantic_store: SemanticStore | None = None,
        procedure_lib: ProcedureLibrary | None = None,
        graph_store: KnowledgeGraphStore | None = None,
    ) -> dict[str, Any]:
        """Execute memory selections, ranking calculations, and budget truncations."""
        with self.lock:
            self.event_bus.publish_sync(
                Event(
                    name="retrieval.started",
                    category="Memory",
                    source="RetrievalEngine",
                    payload={"query": query},
                )
            )

            # 1. Selection Plan
            selected_stores = self.planner.plan_retrieval(query)
            self.event_bus.publish_sync(
                Event(
                    name="memory.selected",
                    category="Memory",
                    source="RetrievalEngine",
                    payload={"stores": selected_stores},
                )
            )

            # 2. Querying Stores
            working_vars = {}
            raw_facts = []
            raw_procedures = []
            raw_episodes = []
            raw_relationships = []

            if "working_memory" in selected_stores and working_session:
                working_vars = working_session.active_variables

            if "semantic_memory" in selected_stores and semantic_store:
                raw_facts = semantic_store.list_all()

            if "procedural_memory" in selected_stores and procedure_lib:
                raw_procedures = procedure_lib.list_all()

            if "episodic_memory" in selected_stores and episodic_store:
                raw_episodes = episodic_store.list_all()

            if "knowledge_graph" in selected_stores and graph_store:
                raw_relationships = graph_store.list_relationships()

            # 3. Deduplication
            facts = self.deduplicator.deduplicate_facts(raw_facts)
            procedures = self.deduplicator.deduplicate_procedures(raw_procedures)
            episodes = raw_episodes
            relationships = raw_relationships

            # 4. Ranking
            facts = self.ranker.rank_facts(facts)
            procedures = self.ranker.rank_procedures(procedures)
            episodes = self.ranker.rank_episodes(episodes)
            self.event_bus.publish_sync(
                Event(
                    name="ranking.completed",
                    category="Memory",
                    source="RetrievalEngine",
                    payload={"facts_count": len(facts)},
                )
            )

            # 5. Budget limits enforcement
            facts, procedures, episodes, relationships = self.budget_manager.enforce_budget(
                facts, procedures, episodes, relationships
            )

            # 6. Context Payload Assembly
            payload = self.builder.build_payload(
                working_vars, facts, procedures, episodes, relationships
            )

            self.event_bus.publish_sync(
                Event(
                    name="context.built",
                    category="Memory",
                    source="RetrievalEngine",
                    payload={"facts": len(facts)},
                )
            )

            self.event_bus.publish_sync(
                Event(
                    name="context.delivered",
                    category="Memory",
                    source="RetrievalEngine",
                    payload={"context_keys": list(payload.keys())},
                )
            )

            return payload
