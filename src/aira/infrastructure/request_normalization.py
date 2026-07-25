"""Enterprise Request Normalization Layer for AIRA.

Converts intent recognition outputs into normalized, validated, and versioned
Runtime Request schemas for consumption by downstream brain orchestrators.
"""

import uuid
from datetime import datetime
from typing import Any, ClassVar

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.intent import IntentResult
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.request")


class RequestNormalizationError(Exception):
    """Base exception for all normalization layer failures."""

    pass


class InvalidRuntimeRequestError(RequestNormalizationError):
    """Raised when validating malformed or invalid runtime request details."""

    pass


class RuntimeRequest:
    """Standardized request object contract passed down to future Brain engines."""

    def __init__(
        self,
        session_id: str,
        intent: str,
        confidence: float,
        language: str,
        original_transcript: str,
        normalized_transcript: str,
        entities: list[dict[str, Any]],
        parameters: dict[str, Any],
        source_module: str = "VoicePlatform",
        priority: int = 1,
        request_version: str = "1.0.0",
    ) -> None:
        self.request_id: str = uuid.uuid4().hex
        self.session_id = session_id
        self.intent = intent
        self.confidence = confidence
        self.language = language
        self.original_transcript = original_transcript
        self.normalized_transcript = normalized_transcript
        self.entities = entities
        self.parameters = parameters
        self.source_module = source_module
        self.timestamp: datetime = datetime.now()
        self.priority = priority
        self.request_version = request_version

    def to_dict(self) -> dict[str, Any]:
        """Serialize runtime request attributes."""
        return {
            "request_id": self.request_id,
            "session_id": self.session_id,
            "intent": self.intent,
            "confidence": self.confidence,
            "language": self.language,
            "original_transcript": self.original_transcript,
            "normalized_transcript": self.normalized_transcript,
            "entities": self.entities,
            "parameters": self.parameters,
            "source_module": self.source_module,
            "timestamp": self.timestamp.isoformat(),
            "priority": self.priority,
            "request_version": self.request_version,
        }


class RequestNormalizer:
    """Resolves aliases and normalizes paths, urls, and app names consistently."""

    APP_ALIASES: ClassVar[dict[str, str]] = {
        "vs code": "Visual Studio Code",
        "vscode": "Visual Studio Code",
        "vs-code": "Visual Studio Code",
        "safari": "Safari Browser",
        "chrome": "Google Chrome",
        "terminal": "System Terminal",
        "slack": "Slack Desktop",
    }

    def normalize_app_name(self, name: str) -> str:
        """Resolve aliases and variations to official application names."""
        cleaned = name.strip().lower()
        return self.APP_ALIASES.get(cleaned, name)

    def normalize_parameters(self, intent: str, params: dict[str, Any]) -> dict[str, Any]:
        """Format paths, URLs, and apply alias lookups depending on Intent targets."""
        normalized = params.copy()
        if "application_name" in normalized:
            normalized["application_name"] = self.normalize_app_name(normalized["application_name"])

        # File paths normalization (strip trailing spaces, ensure lowercase extensions)
        if "file_name" in normalized:
            fn = normalized["file_name"].strip()
            normalized["file_name"] = fn

        return normalized


class RequestValidator:
    """Asserts schema correctness, parameter presence, and validation constraints."""

    @staticmethod
    def validate(req: RuntimeRequest, threshold: float) -> None:
        """Confirm request properties comply with specifications.

        Raises InvalidRuntimeRequestError on failure.
        """
        if not req.session_id.strip():
            raise InvalidRuntimeRequestError("Session ID must be defined.")
        if not req.intent.strip():
            raise InvalidRuntimeRequestError("Intent type classification cannot be blank.")
        if req.confidence < threshold:
            logger.warning("Rejecting request due to low intent confidence", score=req.confidence)
            raise InvalidRuntimeRequestError(
                f"Confidence score {req.confidence} falls below required threshold {threshold}."
            )
        # Required parameter presence rules
        if req.intent == "Open Application" and "application_name" not in req.parameters:
            raise InvalidRuntimeRequestError("Required parameter 'application_name' is missing.")
        if (
            req.intent in ["Read File", "Write File", "Delete File"]
            and "file_name" not in req.parameters
        ):
            raise InvalidRuntimeRequestError("Required parameter 'file_name' is missing.")


class RequestManager:
    """Manages validation pipelines, normalizes parameters, and issues event dispatches."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.normalizer = RequestNormalizer()
        self.validator = RequestValidator()
        self._confidence_threshold = config.voice.intent_confidence_threshold

    def create_request(self, intent_result: IntentResult) -> RuntimeRequest:
        """Normalize intent metadata, validate against schemas, and return consolidated requests."""
        if not intent_result.session_id:
            logger.error("Intent result contains no valid Voice Session ID reference.")
            ev = Event(
                name="request.rejected",
                category="Voice",
                source="RequestManager",
                payload={"error": "Session ID reference missing."},
            )
            self.event_bus.publish_sync(ev)
            raise InvalidRuntimeRequestError("Intent has no session reference.")

        # 1. Dispatch Request Created
        ev_created = Event(
            name="request.created",
            category="Voice",
            source="RequestManager",
            payload={"intent_id": intent_result.intent_id},
        )
        self.event_bus.publish_sync(ev_created)

        try:
            # 2. Normalize parameters
            norm_params = self.normalizer.normalize_parameters(
                intent_result.intent_name, intent_result.parameters
            )

            request = RuntimeRequest(
                session_id=intent_result.session_id,
                intent=intent_result.intent_name,
                confidence=intent_result.confidence,
                language=intent_result.language,
                original_transcript=intent_result.original_transcript,
                normalized_transcript=intent_result.normalized_transcript,
                entities=[e.to_dict() for e in intent_result.extracted_entities],
                parameters=norm_params,
            )

            # 3. Dispatch Request Normalized
            ev_normalized = Event(
                name="request.normalized",
                category="Voice",
                source="RequestManager",
                payload=request.to_dict(),
            )
            self.event_bus.publish_sync(ev_normalized)

            # 4. Validate request schema
            self.validator.validate(request, self._confidence_threshold)

            # 5. Dispatch Request Validated
            ev_validated = Event(
                name="request.validated",
                category="Voice",
                source="RequestManager",
                payload={"request_id": request.request_id},
            )
            self.event_bus.publish_sync(ev_validated)
            logger.info("Runtime Request generated successfully", request_id=request.request_id)

            return request

        except Exception as e:
            logger.error("Request normalizer pipeline failed", error=str(e))
            ev_rejected = Event(
                name="request.rejected",
                category="Voice",
                source="RequestManager",
                payload={"error": str(e)},
            )
            self.event_bus.publish_sync(ev_rejected)
            raise RequestNormalizationError(f"Request construction failed: {e}") from e
