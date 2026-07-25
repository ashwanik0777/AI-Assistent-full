"""Enterprise Feedback Intelligence, Signal Processing & Evidence Quality Platform for AIRA.

Provides feedback signals collectors, classifiers, quality scorers, and priority engines.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.feedback_intelligence")


class FeedbackIntelligenceError(Exception):
    """Base exception raised for classification or priority failures."""

    pass


@dataclass
class FeedbackSignal:
    """Feedback telemetry properties detailed schema mapping quality metrics."""

    feedback_id: str
    interaction_reference: str
    source: str
    signal_type: str  # Positive, Negative, Neutral, Suggestion, Correction, Preference, Bug Report
    confidence: float
    evidence_links: list[str]
    quality_score: float = 0.0
    priority: str = "Medium"  # Critical, High, Medium, Low, Informational
    privacy_classification: str = "Public"
    metadata: dict[str, Any] = field(default_factory=dict)
    version: str = "1.0.0"


class FeedbackClassifier:
    """Classifies feedback signals category based on textual analysis keywords stubs."""

    def classify_text(self, text: str) -> str:
        """Deduce signal type based on simple word filters."""
        text_lower = text.lower()
        if "bug" in text_lower or "error" in text_lower or "failed" in text_lower:
            return "Bug Report"
        if "correct" in text_lower or "should be" in text_lower:
            return "Correction"
        if "prefer" in text_lower or "instead of" in text_lower:
            return "Preference"
        if "suggest" in text_lower or "maybe" in text_lower:
            return "Suggestion"
        return "Neutral"


class EvidenceCorrelator:
    """Correlates feedback items with platform execution indicators references."""

    def correlate(self, signal: FeedbackSignal) -> None:
        """Validate referenced evidence links identifiers presence."""
        if not signal.interaction_reference:
            raise FeedbackIntelligenceError(
                "Correlation failed: Signals must declare interaction references."
            )


class QualityScorer:
    """Assigns quality scores based on initial parameters confidence, frequency, and weights."""

    def compute_score(self, initial_confidence: float, frequency: int = 1) -> float:
        """Compute score multiplier based on recurrences frequency logs."""
        score = initial_confidence * 10.0
        # Boost score slightly on multiple occurrences (frequency)
        if frequency > 1:
            score += min(2.0, (frequency - 1) * 0.5)
        return min(10.0, score)


class PriorityEngine:
    """Assigns priority classes to learning elements."""

    def resolve_priority(self, signal_type: str, quality_score: float) -> str:
        """Assign Critical/High tags to bugs; Informational/Low to neutral elements."""
        if signal_type in ("Bug Report", "Correction"):
            return "Critical" if quality_score >= 8.0 else "High"
        if signal_type in ("Preference", "Suggestion"):
            return "Medium" if quality_score >= 6.0 else "Low"
        return "Informational"


class FeedbackIntelligenceManager:
    """Coordinating manager capturing feedback signals and ranking priorities."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.classifier = FeedbackClassifier()
        self.correlator = EvidenceCorrelator()
        self.scorer = QualityScorer()
        self.priority_engine = PriorityEngine()

        self.collected_signals: dict[str, FeedbackSignal] = {}

    def collect_feedback(
        self,
        feedback_id: str,
        text: str,
        interaction_ref: str,
        source: str,
        initial_confidence: float,
        evidence_links: list[str],
    ) -> FeedbackSignal:
        """Process feedback validation, assign priorities, and publish events."""
        # 1. Classification
        sig_type = self.classifier.classify_text(text)
        self.event_bus.publish_sync(
            Event(
                name="signal.classified",
                category="Feedback",
                source="FeedbackIntelligenceManager",
                payload={"feedback_id": feedback_id, "type": sig_type},
            )
        )

        # Check duplicate
        freq = 1
        if feedback_id in self.collected_signals:
            # Merging duplicate signals
            freq += 1
            existing = self.collected_signals[feedback_id]
            initial_confidence = max(existing.confidence, initial_confidence)
            evidence_links = list(set(existing.evidence_links + evidence_links))

        # 2. Correlate
        signal = FeedbackSignal(
            feedback_id=feedback_id,
            interaction_reference=interaction_ref,
            source=source,
            signal_type=sig_type,
            confidence=initial_confidence,
            evidence_links=evidence_links,
        )
        self.correlator.correlate(signal)
        self.event_bus.publish_sync(
            Event(
                name="evidence.correlated",
                category="Feedback",
                source="FeedbackIntelligenceManager",
                payload={"feedback_id": feedback_id, "links": evidence_links},
            )
        )

        # 3. Quality Scoring
        q_score = self.scorer.compute_score(initial_confidence, freq)
        signal.quality_score = q_score
        self.event_bus.publish_sync(
            Event(
                name="quality.updated",
                category="Feedback",
                source="FeedbackIntelligenceManager",
                payload={"feedback_id": feedback_id, "quality_score": q_score},
            )
        )

        # 4. Priority resolution
        pri = self.priority_engine.resolve_priority(sig_type, q_score)
        signal.priority = pri
        self.event_bus.publish_sync(
            Event(
                name="priority.assigned",
                category="Feedback",
                source="FeedbackIntelligenceManager",
                payload={"feedback_id": feedback_id, "priority": pri},
            )
        )

        self.collected_signals[feedback_id] = signal

        self.event_bus.publish_sync(
            Event(
                name="feedback.recorded",
                category="Feedback",
                source="FeedbackIntelligenceManager",
                payload={"feedback_id": feedback_id, "priority": pri},
            )
        )

        self.event_bus.publish_sync(
            Event(
                name="learning_queue.updated",
                category="Feedback",
                source="FeedbackIntelligenceManager",
                payload={"observation_id": feedback_id, "status": "Pending Review"},
            )
        )

        return signal
