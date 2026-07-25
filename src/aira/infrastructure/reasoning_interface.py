"""Enterprise Reasoning Interface for AIRA.

Translates and normalizes raw AI model outputs into standardized internal
reasoning objects consumed by future planners.
"""

import json
import uuid
from datetime import datetime
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.reasoning")


class ReasoningError(Exception):
    """Base exception for all reasoning layer failures."""

    pass


class InvalidReasoningObjectError(ReasoningError):
    """Raised when validating malformed or invalid internal reasoning structures."""

    pass


class InternalReasoningObject:
    """Standardized internal representation of model decisions and assumptions."""

    def __init__(
        self,
        request_id: str,
        brain_session_id: str,
        provider_id: str,
        confidence: float,
        language: str,
        summary: str,
        detected_intent: str,
        extracted_goals: list[str],
        constraints: list[str],
        assumptions: list[str],
        risks: list[str],
        suggested_actions: list[str],
        priority: int = 1,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.reasoning_id: str = uuid.uuid4().hex
        self.request_id = request_id
        self.brain_session_id = brain_session_id
        self.provider_id = provider_id
        self.timestamp: datetime = datetime.now()
        self.confidence = confidence
        self.language = language
        self.summary = summary
        self.detected_intent = detected_intent
        self.extracted_goals = extracted_goals
        self.constraints = constraints
        self.assumptions = assumptions
        self.risks = risks
        self.suggested_actions = suggested_actions
        self.priority = priority
        self.metadata: dict[str, Any] = metadata or {}

    def to_dict(self) -> dict[str, Any]:
        """Serialize internal reasoning attributes."""
        return {
            "reasoning_id": self.reasoning_id,
            "request_id": self.request_id,
            "brain_session_id": self.brain_session_id,
            "provider_id": self.provider_id,
            "timestamp": self.timestamp.isoformat(),
            "confidence": self.confidence,
            "language": self.language,
            "summary": self.summary,
            "detected_intent": self.detected_intent,
            "extracted_goals": self.extracted_goals,
            "constraints": self.constraints,
            "assumptions": self.assumptions,
            "risks": self.risks,
            "suggested_actions": self.suggested_actions,
            "priority": self.priority,
            "metadata": self.metadata,
        }


class ReasoningNormalizer:
    """Parses raw provider payloads (JSON, plain text, markdown) into schema properties."""

    @staticmethod
    def normalize(
        raw_response: str, request_id: str, brain_session_id: str, provider_id: str
    ) -> InternalReasoningObject:
        """Parse raw string values into InternalReasoningObject components."""
        # Check if raw response is structured JSON
        try:
            parsed = json.loads(raw_response)
            if isinstance(parsed, dict):
                return InternalReasoningObject(
                    request_id=request_id,
                    brain_session_id=brain_session_id,
                    provider_id=provider_id,
                    confidence=float(parsed.get("confidence", 0.9)),
                    language=str(parsed.get("language", "en")),
                    summary=str(parsed.get("summary", "Structured response")),
                    detected_intent=str(parsed.get("detected_intent", "Unknown")),
                    extracted_goals=list(parsed.get("extracted_goals", [])),
                    constraints=list(parsed.get("constraints", [])),
                    assumptions=list(parsed.get("assumptions", [])),
                    risks=list(parsed.get("risks", [])),
                    suggested_actions=list(parsed.get("suggested_actions", [])),
                    priority=int(parsed.get("priority", 1)),
                    metadata=parsed.get("metadata", {}),
                )
        except json.JSONDecodeError:
            pass

        # Parse unstructured plain text/markdown string
        normalized_str = raw_response.strip().lower()
        detected_intent = "Unknown"
        suggested_actions = []
        extracted_goals = []

        if "open" in normalized_str or "visit" in normalized_str:
            detected_intent = "Open Application"
            suggested_actions = ["Open application browser target"]
            extracted_goals = ["Start application lifecycle"]
        elif "delete" in normalized_str:
            detected_intent = "Delete File"
            suggested_actions = ["Remove file target"]
            extracted_goals = ["Perform file delete operations"]

        return InternalReasoningObject(
            request_id=request_id,
            brain_session_id=brain_session_id,
            provider_id=provider_id,
            confidence=0.8,
            language="en",
            summary=raw_response,
            detected_intent=detected_intent,
            extracted_goals=extracted_goals,
            constraints=[],
            assumptions=["Model matches raw keywords"],
            risks=[],
            suggested_actions=suggested_actions,
            priority=1,
            metadata={},
        )


class ReasoningValidator:
    """Verifies schema conformance and rejects malformed structures."""

    @staticmethod
    def validate(obj: InternalReasoningObject) -> None:
        """Confirm properties comply with internal standards. Raises InvalidReasoningObjectError."""
        if not obj.request_id.strip():
            raise InvalidReasoningObjectError("Request ID must be defined.")
        if not obj.brain_session_id.strip():
            raise InvalidReasoningObjectError("Brain Session ID must be defined.")
        if not obj.provider_id.strip():
            raise InvalidReasoningObjectError("Provider ID must be defined.")
        if obj.confidence < 0.0 or obj.confidence > 1.0:
            raise InvalidReasoningObjectError(
                "Confidence score must fall within [0.0, 1.0] limits."
            )
        if not obj.summary.strip():
            raise InvalidReasoningObjectError("Summary description cannot be blank.")


class ReasoningManager:
    """Coordinates normalization steps, validates parameters, and dispatches events."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.normalizer = ReasoningNormalizer()
        self.validator = ReasoningValidator()

    def process_response(
        self, raw_response: str, request_id: str, brain_session_id: str, provider_id: str
    ) -> InternalReasoningObject:
        """Translate raw provider payloads into normalized and validated reasoning schemas."""
        self.event_bus.publish_sync(
            Event(
                name="reasoning.started",
                category="Brain",
                source="ReasoningManager",
                payload={"request_id": request_id},
            )
        )

        try:
            # 1. Normalize
            obj = self.normalizer.normalize(raw_response, request_id, brain_session_id, provider_id)
            self.event_bus.publish_sync(
                Event(
                    name="reasoning.normalized",
                    category="Brain",
                    source="ReasoningManager",
                    payload={"reasoning_id": obj.reasoning_id},
                )
            )

            # 2. Validate
            self.validator.validate(obj)
            self.event_bus.publish_sync(
                Event(
                    name="reasoning.validated",
                    category="Brain",
                    source="ReasoningManager",
                    payload={"reasoning_id": obj.reasoning_id},
                )
            )

            # 3. Complete
            self.event_bus.publish_sync(
                Event(
                    name="reasoning.completed",
                    category="Brain",
                    source="ReasoningManager",
                    payload=obj.to_dict(),
                )
            )

            logger.info(
                "Internal Reasoning Object generated successfully", reasoning_id=obj.reasoning_id
            )
            return obj

        except Exception as e:
            logger.error("Reasoning translation pipeline failed", error=str(e))
            self.event_bus.publish_sync(
                Event(
                    name="reasoning.failed",
                    category="Brain",
                    source="ReasoningManager",
                    payload={"error": str(e)},
                )
            )
            raise ReasoningError(f"Reasoning validation failed: {e}") from e
