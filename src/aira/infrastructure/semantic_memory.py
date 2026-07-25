"""Enterprise Semantic Memory & Knowledge Store for AIRA.

Captures, validates, normalizes, resolves overlaps, and catalogs semantic fact triples.
"""

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.episodic_memory import EpisodeObject
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.semantic_memory")


class SemanticMemoryError(Exception):
    """Raised when fact validation checks, normalizations, or overlap resolutions fail."""

    pass


class FactState(Enum):
    """Lifecycle states of captured semantic facts."""

    CREATED = "CREATED"
    VALIDATED = "VALIDATED"
    CONFIRMED = "CONFIRMED"
    UPDATED = "UPDATED"
    DEPRECATED = "DEPRECATED"
    ARCHIVED = "ARCHIVED"
    DELETED = "DELETED"


@dataclass
class FactObject:
    """Enterprise semantic triple fact representation."""

    fact_id: str
    subject: str
    predicate: str
    object_val: str
    source_episode: str
    confidence_score: float = 1.0
    timestamp: float = field(default_factory=time.time)
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    version: str = "1.0.0"
    state: FactState = FactState.CREATED


class FactNormalizer:
    """Standardizes terminology spelling differences."""

    _DICTIONARY: ClassVar[dict[str, str]] = {
        "python3": "Python",
        "python3.11": "Python",
        "python3.12": "Python",
        "python3.14": "Python",
        "git status": "Git",
        "git commit": "Git",
        "git-cli": "Git",
        "vscode": "VS Code",
        "visual studio code": "VS Code",
        "reactjs": "React",
        "nextjs": "Next.js",
    }

    def normalize(self, term: str) -> str:
        """Translate synonym string to standardized name from dictionary."""
        val = term.strip()
        return self._DICTIONARY.get(val.lower(), val)


class FactValidator:
    """Verifies triple format structure compliance and value bounds."""

    def validate(self, fact: FactObject) -> None:
        """Enforce validation rules checking properties."""
        if not fact.fact_id:
            raise SemanticMemoryError("Fact validation failed: Missing Fact ID.")

        if not fact.subject or not fact.predicate or not fact.object_val:
            raise SemanticMemoryError(
                "Fact validation failed: Triple terms (Subject, Predicate, Object) must be present."
            )

        if not (0.0 <= fact.confidence_score <= 1.0):
            raise SemanticMemoryError(
                f"Confidence score '{fact.confidence_score}' falls outside valid [0.0, 1.0] range."
            )

        if fact.version != "1.0.0":
            raise SemanticMemoryError(f"Unsupported fact version compatibility: '{fact.version}'.")


class ConflictResolver:
    """Resolves overlapping triples collisions using configurable policies."""

    def resolve(
        self, existing: FactObject, proposed: FactObject, policy: str = "NEWEST_WINS"
    ) -> FactObject:
        """Apply target policy to return selected winner fact."""
        if policy == "HIGHEST_CONFIDENCE_WINS":
            if proposed.confidence_score > existing.confidence_score:
                return proposed
            return existing

        # Default policy: NEWEST_WINS
        if proposed.timestamp > existing.timestamp:
            return proposed
        return existing


class KnowledgeExtractor:
    """Extracts semantic triples from episodic execution contexts."""

    def __init__(self) -> None:
        self.normalizer = FactNormalizer()

    def extract_from_episode(self, episode: EpisodeObject) -> list[FactObject]:
        """Convert episodic tags and skills metadata to Fact objects list."""
        facts = []
        now = time.time()

        # 1. Extract technology facts from skills_used
        for idx, skill in enumerate(episode.skills_used):
            normalized_subj = self.normalizer.normalize(episode.title)
            normalized_obj = self.normalizer.normalize(skill)

            fact = FactObject(
                fact_id=f"fact_{episode.episode_id}_skill_{idx}",
                subject=normalized_subj,
                predicate="uses_skill",
                object_val=normalized_obj,
                source_episode=episode.episode_id,
                confidence_score=1.0,
                timestamp=now,
            )
            facts.append(fact)

        # 2. Extract outcome facts
        outcome_fact = FactObject(
            fact_id=f"fact_{episode.episode_id}_outcome",
            subject=self.normalizer.normalize(episode.title),
            predicate="has_outcome",
            object_val=episode.outcome,
            source_episode=episode.episode_id,
            confidence_score=0.9,
            timestamp=now,
        )
        facts.append(outcome_fact)

        return facts


class SemanticStore:
    """Thread-safe catalog database storing validated semantic facts."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.validator = FactValidator()
        self.resolver = ConflictResolver()
        self.extractor = KnowledgeExtractor()
        self.facts: dict[str, FactObject] = {}
        # Triple mappings: key is (subject, predicate) tuple
        self.triple_map: dict[tuple[str, str], FactObject] = {}
        self.lock = threading.Lock()

    def store_fact(self, fact: FactObject, policy: str = "NEWEST_WINS") -> None:
        """Validate proposed fact, check for overlapping collisions, and store reference."""
        with self.lock:
            # 1. Validate
            self.validator.validate(fact)
            fact.state = FactState.VALIDATED

            self.event_bus.publish_sync(
                Event(
                    name="fact.validated",
                    category="Memory",
                    source="SemanticStore",
                    payload={"fact_id": fact.fact_id},
                )
            )

            # 2. Resolve Collisions
            key = (fact.subject, fact.predicate)
            existing = self.triple_map.get(key)
            winner = fact

            if existing:
                self.event_bus.publish_sync(
                    Event(
                        name="conflict.detected",
                        category="Memory",
                        source="SemanticStore",
                        payload={"subject": fact.subject, "predicate": fact.predicate},
                    )
                )

                winner = self.resolver.resolve(existing, fact, policy)
                winner.state = FactState.UPDATED

                # If proposed fact lost, do not overwrite the existing record
                if winner == existing:
                    self.event_bus.publish_sync(
                        Event(
                            name="conflict.resolved",
                            category="Memory",
                            source="SemanticStore",
                            payload={
                                "fact_id": existing.fact_id,
                                "resolution": "Retained existing",
                            },
                        )
                    )
                    return

                # If proposed won, clean up references
                self.facts.pop(existing.fact_id, None)
                self.event_bus.publish_sync(
                    Event(
                        name="conflict.resolved",
                        category="Memory",
                        source="SemanticStore",
                        payload={
                            "fact_id": fact.fact_id,
                            "resolution": f"Overwrote with policy {policy}",
                        },
                    )
                )

            # 3. Store Winner
            self.facts[winner.fact_id] = winner
            self.triple_map[key] = winner
            winner.state = FactState.CONFIRMED

            self.event_bus.publish_sync(
                Event(
                    name="fact.stored",
                    category="Memory",
                    source="SemanticStore",
                    payload={"fact_id": winner.fact_id},
                )
            )

    def get_fact(self, fact_id: str) -> FactObject | None:
        """Fetch matching fact record from catalog."""
        with self.lock:
            return self.facts.get(fact_id)

    def get_fact_by_triple(self, subject: str, predicate: str) -> FactObject | None:
        """Fetch matching fact mapping (subject, predicate) collision key."""
        with self.lock:
            return self.triple_map.get((subject, predicate))

    def list_all(self) -> list[FactObject]:
        """Return list representing all stored facts."""
        with self.lock:
            return list(self.facts.values())
