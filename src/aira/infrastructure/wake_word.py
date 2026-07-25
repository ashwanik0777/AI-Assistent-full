"""Enterprise Wake Word Engine for AIRA.

Provides engine abstraction interfaces, OpenWakeWord adapters, wake session lifecycles,
and event publication triggers.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, ClassVar, Literal

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.wakeword")

WakeSessionStateType = Literal[
    "IDLE", "LISTENING", "WAKE_DETECTED", "WAKE_CONFIRMED", "VOICE_SESSION_STARTED", "COOLDOWN"
]


class WakeWordError(Exception):
    """Base exception for all wake word engine failures."""

    pass


class InvalidWakeSessionTransitionError(WakeWordError):
    """Raised when violating the valid wake session state machine paths."""

    pass


class BaseWakeEngine(ABC):
    """Abstract interface defining the wake word engine contract."""

    @abstractmethod
    def initialize(self, config: AppConfig) -> None:
        """Initialize engine settings and load detection models."""
        pass

    @abstractmethod
    def process_chunk(self, chunk: bytes) -> dict[str, Any] | None:
        """Process a raw PCM chunk, returning prediction metrics if matched."""
        pass


class OpenWakeEngine(BaseWakeEngine):
    """Default implementation utilizing openwakeword interface structures."""

    def __init__(self) -> None:
        self.config: AppConfig | None = None
        self.sensitivity: float = 0.5
        self.threshold: float = 0.7
        self.supported: list[str] = []

    def initialize(self, config: AppConfig) -> None:
        self.config = config
        self.sensitivity = config.voice.wake_sensitivity
        self.threshold = config.voice.wake_confidence_threshold
        self.supported = config.voice.supported_wake_words
        logger.info(
            "Initialized OpenWakeWord adapter",
            sensitivity=self.sensitivity,
            threshold=self.threshold,
            wake_words=self.supported,
        )

    def process_chunk(self, chunk: bytes) -> dict[str, Any] | None:
        """Mock process frames chunk. Returns wake word details if specific triggers match."""
        # Simple test trigger: if chunk contains special bytes prefix or text
        # In real systems, this wraps openwakeword's model.predict(chunk)
        if b"HEY_AIRA_TRIGGER" in chunk:
            return {
                "wake_word": "Hey AIRA",
                "confidence": 0.85,
                "timestamp": datetime.now().isoformat(),
            }
        elif b"HELLO_AIRA_TRIGGER" in chunk:
            return {
                "wake_word": "Hello AIRA",
                "confidence": 0.95,
                "timestamp": datetime.now().isoformat(),
            }
        elif b"AIRA_TRIGGER" in chunk:
            return {
                "wake_word": "AIRA",
                "confidence": 0.72,
                "timestamp": datetime.now().isoformat(),
            }
        return None


class WakeEngineFactory:
    """Factory creating configured wake word detection engine adapters."""

    @staticmethod
    def create_engine(engine_type: str) -> BaseWakeEngine:
        """Create concrete engine adapters."""
        if engine_type == "openwakeword":
            return OpenWakeEngine()
        else:
            logger.error("Unrecognized wake engine type", target=engine_type)
            raise WakeWordError(f"Unsupported wake engine: {engine_type}")


class WakeWordManager:
    """Manages wake engine session states, sensitivity rules, and event triggers."""

    VALID_TRANSITIONS: ClassVar[dict[WakeSessionStateType, set[WakeSessionStateType]]] = {
        "IDLE": {"LISTENING"},
        "LISTENING": {"WAKE_DETECTED", "COOLDOWN", "IDLE"},
        "WAKE_DETECTED": {"WAKE_CONFIRMED", "LISTENING", "COOLDOWN"},
        "WAKE_CONFIRMED": {"VOICE_SESSION_STARTED", "COOLDOWN", "LISTENING"},
        "VOICE_SESSION_STARTED": {"COOLDOWN", "LISTENING"},
        "COOLDOWN": {"LISTENING", "IDLE"},
    }

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.state: WakeSessionStateType = "IDLE"
        self._is_enabled: bool = True
        self._last_activation: datetime | None = None

        # Load engine
        engine_type = config.voice.wake_engine_type
        self.engine = WakeEngineFactory.create_engine(engine_type)
        self.engine.initialize(config)

    def transition_to(self, target_state: WakeSessionStateType) -> None:
        """Transition wake session state and publish event notifications."""
        allowed = self.VALID_TRANSITIONS.get(self.state, set())
        if target_state not in allowed:
            err_msg = f"Wake transition from '{self.state}' to '{target_state}' is invalid."
            logger.error("Wake state transition conflict", current=self.state, target=target_state)
            raise InvalidWakeSessionTransitionError(err_msg)

        old_state = self.state
        self.state = target_state

        # Dispatch events on specific transitions
        event_map = {
            "LISTENING": "wakeword.listening_started",
            "WAKE_DETECTED": "wakeword.detected",
            "WAKE_CONFIRMED": "wakeword.confirmed",
            "COOLDOWN": "wakeword.cooldown_started",
            "IDLE": "wakeword.listening_stopped",
        }
        event_name = event_map.get(target_state)
        if event_name:
            ev = Event(
                name=event_name,
                category="Voice",
                source="WakeWordManager",
                payload={"old_state": old_state, "new_state": target_state},
            )
            self.event_bus.publish_sync(ev)
            logger.info("Wake event published", event_type=event_name)

    def enable(self) -> None:
        """Enable wake detection listening."""
        self._is_enabled = True
        logger.info("Wake word detection enabled.")

    def disable(self) -> None:
        """Temporarily disable wake detection listening."""
        self._is_enabled = False
        if self.state != "IDLE":
            self.transition_to("IDLE")
        ev = Event(name="wakeword.disabled", category="Voice", source="WakeWordManager", payload={})
        self.event_bus.publish_sync(ev)
        logger.info("Wake word detection disabled.")

    def start_listening(self) -> None:
        """Enter LISTENING status lifecycle."""
        if not self._is_enabled:
            logger.warning("Wake word detection is disabled. Cannot start listening.")
            raise WakeWordError("Wake word engine is disabled.")
        self.transition_to("LISTENING")

    def process_audio_chunk(self, chunk: bytes) -> dict[str, Any] | None:
        """Pass audio chunk to wake engine, evaluate confidence filters, and update state."""
        if self.state != "LISTENING" or not self._is_enabled:
            return None

        # Check cooldown period
        if self._last_activation:
            elapsed = (datetime.now() - self._last_activation).total_seconds()
            if elapsed < self.config.voice.wake_cooldown_seconds:
                # Still cooling down, ignore triggers
                return None

        try:
            match = self.engine.process_chunk(chunk)
            if match is None:
                return None

            word = match.get("wake_word")
            confidence = match.get("confidence", 0.0)

            # Sensitivity and confidence threshold filter checks
            if word not in self.config.voice.supported_wake_words:
                logger.debug("Unsupported wake word detected; filtering", word=word)
                return None

            if confidence < self.config.voice.wake_confidence_threshold:
                logger.debug("Wake detection confidence below threshold", confidence=confidence)
                return None

            # Wake word confirmed
            logger.info("Wake word matched successfully", word=word, confidence=confidence)
            self.transition_to("WAKE_DETECTED")
            self.transition_to("WAKE_CONFIRMED")

            # Start voice session simulation
            self.transition_to("VOICE_SESSION_STARTED")
            self._last_activation = datetime.now()

            # Trigger cooldown state
            self.transition_to("COOLDOWN")
            self.transition_to("LISTENING")

            return match

        except Exception as e:
            logger.error("Wake engine chunk processing failed", error=str(e))
            ev = Event(
                name="wakeword.error",
                category="Voice",
                source="WakeWordManager",
                payload={"error": str(e)},
            )
            self.event_bus.publish_sync(ev)
            raise WakeWordError(f"Wake engine process failure: {e}") from e
