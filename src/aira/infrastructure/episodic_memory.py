"""Enterprise Episodic Memory Engine for AIRA.

Captures, validates, analyzes, and catalogs execution experience episodes.
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

logger = structlog.get_logger("aira.episodic_memory")


class EpisodicMemoryError(Exception):
    """Raised when validation constraints fail or importance analyzers crash."""

    pass


class EpisodeState(Enum):
    """Lifecycle states of captured episodes."""

    CREATED = "CREATED"
    BUILDING = "BUILDING"
    VALIDATED = "VALIDATED"
    STORED = "STORED"
    ARCHIVED = "ARCHIVED"
    DELETED = "DELETED"


@dataclass
class EpisodeObject:
    """Enterprise experience record dataclass representation."""

    episode_id: str
    title: str
    description: str
    intent: str
    goal: str
    workflow_id: str
    execution_token: str
    start_time: float
    end_time: float
    duration: float
    outcome: str  # SUCCESS or FAILURE
    skills_used: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    recovery_info: dict[str, Any] = field(default_factory=dict)
    summary: dict[str, str] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    importance_score: float = 0.5
    state: EpisodeState = EpisodeState.CREATED
    version: str = "1.0.0"


class EpisodeValidator:
    """Verifies execution context tokens and time constraints integrity."""

    def validate(self, episode: EpisodeObject) -> None:
        """Enforce validation rules checking details metadata."""
        if not episode.episode_id:
            raise EpisodicMemoryError("Episode validation failed: Missing Episode ID.")

        if not episode.execution_token:
            raise EpisodicMemoryError("Episode validation failed: Missing Execution Token.")

        if episode.start_time > episode.end_time:
            raise EpisodicMemoryError(
                "Episode validation failed: Start time occurs after end time parameters."
            )

        if not episode.summary or "short" not in episode.summary:
            raise EpisodicMemoryError("Episode validation failed: Short summary is missing.")


class ImportanceAnalyzer:
    """Calculates weight significance scores representing captured episodes."""

    def analyze(self, episode: EpisodeObject) -> float:
        """Calculate weighted score between 0.0 and 1.0."""
        failure_weight = 0.4 if episode.outcome == "FAILURE" or episode.errors else 0.0
        recovery_weight = 0.3 if episode.recovery_info else 0.0
        skills_weight = min(0.3, len(episode.skills_used) * 0.1)

        # Baseline index starts at 0.3
        score = min(1.0, 0.3 + failure_weight + recovery_weight + skills_weight)
        return round(score, 2)


class EpisodeSummarizer:
    """Compiles deterministic summary reports without calling external AI providers."""

    def summarize(self, episode: EpisodeObject) -> dict[str, str]:
        """Compile Short, Detailed, and Technical summaries."""
        short_desc = f"{episode.title} - Result: {episode.outcome}"

        skills_joined = ", ".join(episode.skills_used) if episode.skills_used else "None"
        detailed_desc = (
            f"Intent: {episode.intent} | Goal: {episode.goal} | "
            f"Skills used: {skills_joined} | Outcome: {episode.outcome}."
        )

        tech_desc = (
            f"Workflow ID: {episode.workflow_id} | Token: {episode.execution_token} | "
            f"Duration: {episode.duration:.2f}s | Errors logged: {len(episode.errors)}."
        )

        return {"short": short_desc, "detailed": detailed_desc, "technical": tech_desc}


class EpisodeBuilder:
    """Accumulates execution context items step-by-step."""

    def __init__(self, episode_id: str, title: str, workflow_id: str, execution_token: str) -> None:
        self.episode_id = episode_id
        self.title = title
        self.workflow_id = workflow_id
        self.execution_token = execution_token
        self.intent = ""
        self.goal = ""
        self.start_time = time.time()
        self.skills_used: list[str] = []
        self.errors: list[str] = []
        self.recovery_info: dict[str, Any] = {}
        self.artifacts: list[str] = []
        self.metadata: dict[str, Any] = {}

    def add_skill(self, skill_name: str) -> None:
        """Record a skill invocation in the builder context."""
        if skill_name not in self.skills_used:
            self.skills_used.append(skill_name)

    def record_error(self, error_msg: str) -> None:
        """Record an error occurred during execution run."""
        self.errors.append(error_msg)

    def build(self, outcome: str) -> EpisodeObject:
        """Compile the final EpisodeObject capturing end time metrics."""
        end_time = time.time()
        duration = max(0.0, end_time - self.start_time)

        episode = EpisodeObject(
            episode_id=self.episode_id,
            title=self.title,
            description=f"Automated capture for workflow {self.workflow_id}",
            intent=self.intent,
            goal=self.goal,
            workflow_id=self.workflow_id,
            execution_token=self.execution_token,
            start_time=self.start_time,
            end_time=end_time,
            duration=duration,
            outcome=outcome,
            skills_used=list(self.skills_used),
            errors=list(self.errors),
            recovery_info=dict(self.recovery_info),
            artifacts=list(self.artifacts),
            metadata=dict(self.metadata),
            state=EpisodeState.BUILDING,
        )
        return episode


class EpisodeStore:
    """Thread-safe catalog repository storing finalized EpisodeObject entities."""

    _VALID_TRANSITIONS: ClassVar[dict[EpisodeState, set[EpisodeState]]] = {
        EpisodeState.CREATED: {EpisodeState.BUILDING},
        EpisodeState.BUILDING: {EpisodeState.VALIDATED},
        EpisodeState.VALIDATED: {EpisodeState.STORED},
        EpisodeState.STORED: {EpisodeState.ARCHIVED, EpisodeState.DELETED},
        EpisodeState.ARCHIVED: {EpisodeState.DELETED},
        EpisodeState.DELETED: set(),
    }

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.validator = EpisodeValidator()
        self.analyzer = ImportanceAnalyzer()
        self.summarizer = EpisodeSummarizer()
        self.episodes: dict[str, EpisodeObject] = {}
        self.lock = threading.Lock()

    def store_episode(self, episode: EpisodeObject) -> None:
        """Finalize, validate, calculate scores, and store the episode instance."""
        with self.lock:
            if episode.episode_id in self.episodes:
                raise EpisodicMemoryError(
                    f"Episode with ID '{episode.episode_id}' is already registered."
                )

            # Generate deterministic summaries
            episode.summary = self.summarizer.summarize(episode)

            # Perform validation checks
            self.validator.validate(episode)
            episode.state = EpisodeState.VALIDATED

            # Evaluate importance score significance
            episode.importance_score = self.analyzer.analyze(episode)

            # Store reference catalog thread-safely
            episode.state = EpisodeState.STORED
            self.episodes[episode.episode_id] = episode

            self.event_bus.publish_sync(
                Event(
                    name="episode.stored",
                    category="Memory",
                    source="EpisodeStore",
                    payload={"episode_id": episode.episode_id, "score": episode.importance_score},
                )
            )

    def get_episode(self, episode_id: str) -> EpisodeObject | None:
        """Fetch matching episode instance from catalog."""
        with self.lock:
            return self.episodes.get(episode_id)

    def list_all(self) -> list[EpisodeObject]:
        """Return list representing all stored episodes."""
        with self.lock:
            return list(self.episodes.values())
