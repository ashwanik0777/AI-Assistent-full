"""Adaptive Intelligence & Governed Learning Foundation for AIRA.

Provides structured observation records, validators, queues, and evidence databases.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.adaptive_learning")


class LearningFoundationError(Exception):
    """Base exception raised for evidence validation, duplicate records, or queue updates issues."""

    pass


@dataclass
class ObservationRecord:
    """Captured platform interaction detailed parameters and metrics."""

    observation_id: str
    timestamp: float
    interaction_type: str  # feedback, workflow_outcome, execution_result
    context_reference: str
    outcome_summary: str
    evidence_score: float
    confidence: float
    source: str
    privacy_classification: str = "Public"  # Public, Protected, PII
    metadata: dict[str, Any] = field(default_factory=dict)
    version: str = "1.0.0"


class EvidenceValidator:
    """Enforces confidence thresholds and identifies duplicate logs entries."""

    def __init__(self, min_confidence: float = 0.5) -> None:
        self.min_confidence = min_confidence
        self.processed_ids: set[str] = set()

    def validate_record(self, record: ObservationRecord) -> None:
        """Reject low confidence parameters or duplicate interaction IDs."""
        # 1. Duplicate check
        if record.observation_id in self.processed_ids:
            raise LearningFoundationError(
                f"Validation failed: Duplicate observation ID '{record.observation_id}'."
            )

        # 2. Confidence check
        if record.confidence < self.min_confidence:
            raise LearningFoundationError(
                f"Validation failed: Confidence '{record.confidence}' "
                f"is below threshold '{self.min_confidence}'."
            )

    def mark_processed(self, observation_id: str) -> None:
        """Mark record ID processed."""
        self.processed_ids.add(observation_id)


class EvidenceStore:
    """Storage directory indexing validated evidence records."""

    def __init__(self) -> None:
        self.store: dict[str, ObservationRecord] = {}

    def save(self, record: ObservationRecord) -> None:
        """Persist record."""
        self.store[record.observation_id] = record

    def get(self, observation_id: str) -> ObservationRecord | None:
        """Fetch record."""
        return self.store.get(observation_id)


class LearningQueue:
    """Review queue grouping pending updates states mappings."""

    def __init__(self) -> None:
        # Maps observation_id -> status state
        self.queue: dict[str, str] = {}

    def enqueue(self, observation_id: str) -> None:
        """Add item in review state."""
        self.queue[observation_id] = "Pending Review"

    def update_status(self, observation_id: str, status: str) -> None:
        """Update review queue state status."""
        allowed = {"Pending Review", "Approved", "Rejected", "Deferred", "Archived"}
        if status not in allowed:
            raise LearningFoundationError(
                f"Queue update failed: Status '{status}' is not supported."
            )
        self.queue[observation_id] = status


class LearningManager:
    """Coordinating manager verifying records, managing databases, and publishing events."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.validator = EvidenceValidator()
        self.store = EvidenceStore()
        self.queue = LearningQueue()

    def record_observation(self, record: ObservationRecord) -> None:
        """Validate, store, enqueue, and publish events sync logs."""
        try:
            self.validator.validate_record(record)
        except LearningFoundationError as e:
            self.event_bus.publish_sync(
                Event(
                    name="evidence.validation_failed",
                    category="AdaptiveLearning",
                    source="LearningManager",
                    payload={"observation_id": record.observation_id, "reason": str(e)},
                )
            )
            raise

        # Save and process status shifts
        self.validator.mark_processed(record.observation_id)
        self.store.save(record)
        self.queue.enqueue(record.observation_id)

        self.event_bus.publish_sync(
            Event(
                name="observation.recorded",
                category="AdaptiveLearning",
                source="LearningManager",
                payload={"observation_id": record.observation_id, "type": record.interaction_type},
            )
        )

        self.event_bus.publish_sync(
            Event(
                name="evidence.validated",
                category="AdaptiveLearning",
                source="LearningManager",
                payload={"observation_id": record.observation_id},
            )
        )

        self.event_bus.publish_sync(
            Event(
                name="learning_queue.updated",
                category="AdaptiveLearning",
                source="LearningManager",
                payload={"observation_id": record.observation_id, "status": "Pending Review"},
            )
        )

    def approve_observation(self, observation_id: str) -> None:
        """Transition queue status to Approved and notify."""
        if not self.store.get(observation_id):
            raise LearningFoundationError(f"Operation failed: Record '{observation_id}' not found.")

        self.queue.update_status(observation_id, "Approved")
        self.event_bus.publish_sync(
            Event(
                name="review.requested",
                category="AdaptiveLearning",
                source="LearningManager",
                payload={"observation_id": observation_id, "outcome": "Approved"},
            )
        )

    def archive_observation(self, observation_id: str) -> None:
        """Transition queue status to Archived and notify."""
        if not self.store.get(observation_id):
            raise LearningFoundationError(f"Operation failed: Record '{observation_id}' not found.")

        self.queue.update_status(observation_id, "Archived")
        self.event_bus.publish_sync(
            Event(
                name="evidence.archived",
                category="AdaptiveLearning",
                source="LearningManager",
                payload={"observation_id": observation_id},
            )
        )
