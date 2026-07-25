"""Enterprise Intent Recognition Layer for AIRA.

Converts raw spoken natural language transcripts into structured intent models
with parameters, confidence thresholds, and entity boundaries.
"""

import re
import uuid
from datetime import datetime
from typing import Any, Literal

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.intent")

IntentConfidenceLevel = Literal["HIGH", "MEDIUM", "LOW", "UNKNOWN"]

IntentTypeName = Literal[
    "Open Application",
    "Close Application",
    "Read File",
    "Write File",
    "Search",
    "Open Website",
    "Create Folder",
    "Delete File",
    "Ask Question",
    "Greeting",
    "Unknown Intent",
]


class IntentError(Exception):
    """Base exception for all intent recognition system failures."""

    pass


class InvalidIntentError(IntentError):
    """Raised when intent fields or validation constraints fail."""

    pass


class ExtractedEntity:
    """Dataclass holding extracted NER bounds and values."""

    def __init__(self, entity_type: str, value: str, start: int, end: int) -> None:
        self.entity_type = entity_type
        self.value = value
        self.start = start
        self.end = end

    def to_dict(self) -> dict[str, Any]:
        """Serialize entity properties."""
        return {
            "entity_type": self.entity_type,
            "value": self.value,
            "start": self.start,
            "end": self.end,
        }


class IntentResult:
    """Structured intent representation outcome produced by the parser."""

    def __init__(
        self,
        intent_name: IntentTypeName,
        confidence: float,
        confidence_level: IntentConfidenceLevel,
        original_transcript: str,
        normalized_transcript: str,
        extracted_entities: list[ExtractedEntity],
        parameters: dict[str, Any],
        language: str,
        session_id: str | None = None,
    ) -> None:
        self.intent_id: str = uuid.uuid4().hex
        self.intent_name = intent_name
        self.confidence = confidence
        self.confidence_level = confidence_level
        self.original_transcript = original_transcript
        self.normalized_transcript = normalized_transcript
        self.extracted_entities = extracted_entities
        self.parameters = parameters
        self.language = language
        self.timestamp: datetime = datetime.now()
        self.session_id = session_id

    def to_dict(self) -> dict[str, Any]:
        """Serialize intent properties."""
        return {
            "intent_id": self.intent_id,
            "intent_name": self.intent_name,
            "confidence": self.confidence,
            "confidence_level": self.confidence_level,
            "original_transcript": self.original_transcript,
            "normalized_transcript": self.normalized_transcript,
            "extracted_entities": [e.to_dict() for e in self.extracted_entities],
            "parameters": self.parameters,
            "language": self.language,
            "timestamp": self.timestamp.isoformat(),
            "session_id": self.session_id,
        }


class IntentParser:
    """Parses transcripts using pattern-matching rules and extracts entities."""

    # Simple Regex Rules for extracting entities
    URL_PATTERN: re.Pattern[str] = re.compile(
        r"(https?://[^\s]+|www\.[^\s]+\.[^\s]+|[a-zA-Z0-9.-]+\.(com|org|net|io|in|edu))"
    )
    FILE_PATTERN: re.Pattern[str] = re.compile(
        r"([a-zA-Z0-9_-]+\.(txt|md|py|json|yaml|yml|csv|pdf))"
    )
    APP_PATTERN: re.Pattern[str] = re.compile(
        r"\b(safari|chrome|slack|terminal|finder|spotify|sublime|vscode)\b", re.IGNORECASE
    )

    @staticmethod
    def normalize(text: str) -> str:
        """Sanitize whitespace, cases, and characters."""
        return " ".join(text.strip().lower().split())

    def extract_entities(self, text: str) -> list[ExtractedEntity]:
        """Extract application names, files, URLs, and numeric references from text."""
        entities: list[ExtractedEntity] = []

        # 1. Extract URLs
        for match in self.URL_PATTERN.finditer(text):
            entities.append(ExtractedEntity("URL", match.group(0), match.start(), match.end()))

        # 2. Extract Files
        for match in self.FILE_PATTERN.finditer(text):
            entities.append(ExtractedEntity("File", match.group(0), match.start(), match.end()))

        # 3. Extract Apps
        for match in self.APP_PATTERN.finditer(text):
            entities.append(
                ExtractedEntity("Application", match.group(0), match.start(), match.end())
            )

        return entities

    def parse_transcript(
        self, transcript: str, threshold: float, session_id: str | None = None
    ) -> IntentResult:
        """Run tokenization matching rules and determine Intent classification properties."""
        normalized = self.normalize(transcript)
        entities = self.extract_entities(normalized)

        intent_name: IntentTypeName = "Unknown Intent"
        confidence = 0.5
        params: dict[str, Any] = {}

        # Rule evaluation pipeline
        if not normalized:
            intent_name = "Unknown Intent"
            confidence = 0.0
        elif "hello" in normalized or "greet" in normalized or "hi" in normalized:
            intent_name = "Greeting"
            confidence = 0.9
        elif "open" in normalized and any(e.entity_type == "Application" for e in entities):
            intent_name = "Open Application"
            confidence = 0.85
            app_entity = next(e for e in entities if e.entity_type == "Application")
            params["application_name"] = app_entity.value
        elif "close" in normalized and any(e.entity_type == "Application" for e in entities):
            intent_name = "Close Application"
            confidence = 0.85
            app_entity = next(e for e in entities if e.entity_type == "Application")
            params["application_name"] = app_entity.value
        elif "read" in normalized and any(e.entity_type == "File" for e in entities):
            intent_name = "Read File"
            confidence = 0.8
            file_entity = next(e for e in entities if e.entity_type == "File")
            params["file_name"] = file_entity.value
        elif "write" in normalized and any(e.entity_type == "File" for e in entities):
            intent_name = "Write File"
            confidence = 0.8
            file_entity = next(e for e in entities if e.entity_type == "File")
            params["file_name"] = file_entity.value
        elif "delete" in normalized and any(e.entity_type == "File" for e in entities):
            intent_name = "Delete File"
            confidence = 0.8
            file_entity = next(e for e in entities if e.entity_type == "File")
            params["file_name"] = file_entity.value
        elif "search" in normalized or "find" in normalized:
            intent_name = "Search"
            confidence = 0.75
            params["query"] = normalized.replace("search", "").replace("find", "").strip()
        elif (
            "visit" in normalized
            or "go to" in normalized
            or any(e.entity_type == "URL" for e in entities)
        ):
            intent_name = "Open Website"
            confidence = 0.8
            url_entity = next((e for e in entities if e.entity_type == "URL"), None)
            params["url"] = url_entity.value if url_entity else normalized
        elif "folder" in normalized or "directory" in normalized:
            intent_name = "Create Folder"
            confidence = 0.7
            params["folder_name"] = "new_folder"
        elif (
            "?" in transcript or "what" in normalized or "how" in normalized or "why" in normalized
        ):
            intent_name = "Ask Question"
            confidence = 0.75

        # Classify confidence level enum
        if confidence >= 0.8:
            level: IntentConfidenceLevel = "HIGH"
        elif confidence >= 0.5:
            level = "MEDIUM"
        elif confidence >= 0.2:
            level = "LOW"
        else:
            level = "UNKNOWN"

        return IntentResult(
            intent_name=intent_name,
            confidence=confidence,
            confidence_level=level,
            original_transcript=transcript,
            normalized_transcript=normalized,
            extracted_entities=entities,
            parameters=params,
            language="en",
            session_id=session_id,
        )


class IntentValidator:
    """Validates structural properties of parsed intents."""

    @staticmethod
    def validate(result: IntentResult) -> None:
        """Enforce validation rules. Raises InvalidIntentError on failure."""
        if not result.original_transcript.strip():
            logger.error("Empty transcript provided during intent parsing checks.")
            raise InvalidIntentError("Original transcript cannot be empty.")
        if result.confidence < 0.0 or result.confidence > 1.0:
            logger.error("Confidence bounds breached", value=result.confidence)
            raise InvalidIntentError("Confidence score must fall between 0.0 and 1.0.")


class IntentManager:
    """Enterprise coordinator managing registries, pipelines, and event dispatches."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.parser = IntentParser()
        self.validator = IntentValidator()
        self._threshold = config.voice.intent_confidence_threshold

    def recognize_intent(self, transcript: str, session_id: str | None = None) -> IntentResult:
        """Run transcript normalizations, extract entities, and validate structures."""
        if not transcript.strip():
            logger.error("Blank transcript; aborting recognition.")
            ev = Event(
                name="intent.failed",
                category="Voice",
                source="IntentManager",
                payload={"error": "Blank transcript input."},
            )
            self.event_bus.publish_sync(ev)
            raise InvalidIntentError("Blank transcript string.")

        try:
            result = self.parser.parse_transcript(transcript, self._threshold, session_id)
            self.validator.validate(result)

            # Dispatch entity extraction notifications
            if result.extracted_entities:
                ev_entities = Event(
                    name="intent.entities_extracted",
                    category="Voice",
                    source="IntentManager",
                    payload={"entities": [e.to_dict() for e in result.extracted_entities]},
                )
                self.event_bus.publish_sync(ev_entities)
                logger.info("Entities extracted successfully", count=len(result.extracted_entities))

            # Dispatch success events
            ev_detected = Event(
                name="intent.detected",
                category="Voice",
                source="IntentManager",
                payload=result.to_dict(),
            )
            self.event_bus.publish_sync(ev_detected)
            logger.info(
                "Intent detected successfully",
                intent=result.intent_name,
                confidence=result.confidence_level,
            )

            return result

        except Exception as e:
            logger.error("Intent parsing operation failure", error=str(e))
            ev = Event(
                name="intent.failed",
                category="Voice",
                source="IntentManager",
                payload={"error": str(e)},
            )
            self.event_bus.publish_sync(ev)
            raise IntentError(f"Intent recognition failed: {e}") from e
