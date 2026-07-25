"""Enterprise Voice Session Manager for AIRA.

Coordinates session lifecycle transitions, timeouts, active registries,
and state metadata.
"""

import uuid
from datetime import datetime
from typing import Any, ClassVar, Literal

import structlog

from aira.infrastructure.audio import AudioManager
from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry
from aira.infrastructure.speech_recognition import SpeechRecognitionManager
from aira.infrastructure.wake_word import WakeWordManager

logger = structlog.get_logger("aira.voicesession")

VoiceSessionStateType = Literal[
    "IDLE",
    "WAITING_FOR_WAKE",
    "WAKE_DETECTED",
    "LISTENING",
    "RECOGNIZING",
    "WAITING_FOR_RESPONSE",
    "RESPONDING",
    "COMPLETED",
]


class VoiceSessionError(Exception):
    """Base exception for all voice session failures."""

    pass


class InvalidVoiceSessionTransitionError(VoiceSessionError):
    """Raised when violating the valid session state machine paths."""

    pass


class VoiceSessionMetadata:
    """Consolidated metadata tracking parameters for active voice sessions."""

    def __init__(self, session_id: str, microphone_name: str) -> None:
        self.session_id = session_id
        self.user_id: str = "default_user"
        self.start_time: datetime = datetime.now()
        self.end_time: datetime | None = None
        self.duration: float = 0.0
        self.current_state: VoiceSessionStateType = "IDLE"
        self.wake_word_used: str = ""
        self.language: str = "en"
        self.microphone: str = microphone_name
        self.recognition_count: int = 0
        self.transcript_count: int = 0
        self.error_count: int = 0

    def finalize(self) -> None:
        """Lock ending timestamps and compute elapsed duration."""
        self.end_time = datetime.now()
        self.duration = (self.end_time - self.start_time).total_seconds()

    def to_dict(self) -> dict[str, Any]:
        """Serialize session metadata properties."""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration": self.duration,
            "current_state": self.current_state,
            "wake_word_used": self.wake_word_used,
            "language": self.language,
            "microphone": self.microphone,
            "recognition_count": self.recognition_count,
            "transcript_count": self.transcript_count,
            "error_count": self.error_count,
        }


class VoiceSession:
    """A single managed voice interaction lifecycle context instance."""

    VALID_TRANSITIONS: ClassVar[dict[VoiceSessionStateType, set[VoiceSessionStateType]]] = {
        "IDLE": {"WAITING_FOR_WAKE"},
        "WAITING_FOR_WAKE": {"WAKE_DETECTED", "IDLE"},
        "WAKE_DETECTED": {"LISTENING", "IDLE"},
        "LISTENING": {"RECOGNIZING", "IDLE"},
        "RECOGNIZING": {"WAITING_FOR_RESPONSE", "IDLE"},
        "WAITING_FOR_RESPONSE": {"RESPONDING", "COMPLETED", "IDLE"},
        "RESPONDING": {"COMPLETED", "IDLE"},
        "COMPLETED": {"IDLE"},
    }

    def __init__(self, session_id: str, microphone_name: str, timeout_seconds: float) -> None:
        self.session_id = session_id
        self.timeout_seconds = timeout_seconds
        self.state: VoiceSessionStateType = "IDLE"
        self.metadata = VoiceSessionMetadata(session_id, microphone_name)
        self._last_active: datetime = datetime.now()

    def transition_to(self, target_state: VoiceSessionStateType) -> None:
        """Enforce transition mapping checks and update metadata state references."""
        allowed = self.VALID_TRANSITIONS.get(self.state, set())
        if target_state not in allowed:
            err_msg = (
                f"Voice session transition from '{self.state}' to '{target_state}' is invalid."
            )
            logger.error(
                "Session state transition conflict", current=self.state, target=target_state
            )
            raise InvalidVoiceSessionTransitionError(err_msg)

        self.state = target_state
        self.metadata.current_state = target_state
        self._last_active = datetime.now()

    def touch(self) -> None:
        """Update last active timestamp mark."""
        self._last_active = datetime.now()

    def is_expired(self) -> bool:
        """Check if elapsed inactive duration exceeds timeout bounds."""
        elapsed = (datetime.now() - self._last_active).total_seconds()
        return elapsed > self.timeout_seconds


class VoiceSessionManager:
    """Enterprise manager coordinating Voice Sessions, audio hardware, and event notifications."""

    def __init__(
        self,
        config: AppConfig,
        registry: ServiceRegistry,
        event_bus: EventBus,
        audio: AudioManager,
        wake_word: WakeWordManager,
        stt: SpeechRecognitionManager,
    ) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus
        self.audio = audio
        self.wake_word = wake_word
        self.stt = stt

        self.active_session: VoiceSession | None = None
        self._timeout_seconds = config.voice.session_timeout_seconds

    def create_session(self) -> VoiceSession:
        """Create a new voice interaction session instance."""
        if self.active_session is not None:
            # Clean up existing session
            logger.info("Cleaning up active voice session before creating new instance.")
            self.close_session()

        session_id = uuid.uuid4().hex
        mic_name = self.audio.device_manager.get_selected_device().name
        self.active_session = VoiceSession(session_id, mic_name, self._timeout_seconds)

        # Dispatch Session Created Event
        ev = Event(
            name="voicesession.created",
            category="Voice",
            source="VoiceSessionManager",
            payload={"session_id": session_id},
        )
        self.event_bus.publish_sync(ev)
        logger.info("Voice session context created", session=session_id)
        return self.active_session

    def start_session(self) -> None:
        """Activate the session, starting audio capture interfaces and wake word detection."""
        if self.active_session is None:
            self.create_session()

        assert self.active_session is not None
        self.active_session.transition_to("WAITING_FOR_WAKE")

        # Sync downstream voice engines
        self.audio.initialize()
        self.wake_word.enable()
        self.wake_word.start_listening()

        # Dispatch Session Started Event
        ev = Event(
            name="voicesession.started",
            category="Voice",
            source="VoiceSessionManager",
            payload={"session_id": self.active_session.session_id},
        )
        self.event_bus.publish_sync(ev)
        logger.info("Voice session started successfully.")

    def handle_wake_trigger(self, wake_word: str) -> None:
        """Update session state to WAKE_DETECTED upon wake word triggers."""
        if self.active_session is None or self.active_session.state != "WAITING_FOR_WAKE":
            return

        self.active_session.metadata.wake_word_used = wake_word
        self.active_session.transition_to("WAKE_DETECTED")

        # Dispatch Wake Detected Event
        ev = Event(
            name="voicesession.wake_detected",
            category="Voice",
            source="VoiceSessionManager",
            payload={"wake_word": wake_word, "session_id": self.active_session.session_id},
        )
        self.event_bus.publish_sync(ev)

        # Advance to LISTENING
        self.active_session.transition_to("LISTENING")
        self.stt.start_listening()

    def process_audio(self, audio_chunk: bytes) -> None:
        """Process real-time audio chunk through active session pipeline checkpoints."""
        if self.active_session is None:
            return

        # Expire session if inactive
        if self.active_session.is_expired():
            self.handle_timeout()
            return

        self.active_session.touch()

        # If in WAITING_FOR_WAKE, pass audio chunks to Wake Word Manager
        if self.active_session.state == "WAITING_FOR_WAKE":
            match = self.wake_word.process_audio_chunk(audio_chunk)
            if match:
                self.handle_wake_trigger(match["wake_word"])

        # If in LISTENING, pass audio chunks to STT SpeechRecognitionManager
        elif self.active_session.state == "LISTENING":
            self.active_session.transition_to("RECOGNIZING")
            try:
                self.active_session.metadata.recognition_count += 1
                result = self.stt.transcribe_audio(audio_chunk)
                self.active_session.metadata.transcript_count += 1

                # Update transcript event
                self.active_session.transition_to("WAITING_FOR_RESPONSE")

                # Check for completed transaction
                self.active_session.transition_to("COMPLETED")
                logger.info("Voice session interaction completed", text=result.text)

            except Exception as e:
                self.active_session.metadata.error_count += 1
                logger.error("Session audio process transcription failure", error=str(e))
                # Survive temporary failures, falling back to listening
                self.active_session.transition_to("IDLE")
                self.active_session.state = "LISTENING"  # State rollback recovery
                raise VoiceSessionError(f"Audio processing failure inside session: {e}") from e

    def handle_timeout(self) -> None:
        """Mark session state expired and close handles."""
        if self.active_session is None:
            return

        session_id = self.active_session.session_id
        logger.warning("Voice session timed out due to inactivity", session=session_id)

        # Dispatch Timeout Event
        ev = Event(
            name="voicesession.timeout",
            category="Voice",
            source="VoiceSessionManager",
            payload={"session_id": session_id},
        )
        self.event_bus.publish_sync(ev)

        self.close_session()

    def cancel_session(self) -> None:
        """Cancel the current session and publish cancellations."""
        if self.active_session is None:
            return

        session_id = self.active_session.session_id
        logger.info("Voice session cancelled by system request", session=session_id)

        # Dispatch Cancelled Event
        ev = Event(
            name="voicesession.cancelled",
            category="Voice",
            source="VoiceSessionManager",
            payload={"session_id": session_id},
        )
        self.event_bus.publish_sync(ev)

        self.close_session()

    def close_session(self) -> None:
        """Gracefully release audio capture and close active session details."""
        if self.active_session is None:
            return

        session_id = self.active_session.session_id
        self.active_session.metadata.finalize()

        # Stop hardware streams
        if self.audio.state in ["LISTENING", "STREAMING", "BUFFERING", "PAUSED"]:
            self.audio.stop_listening()
        self.wake_word.disable()

        # Dispatch Closed Event
        ev = Event(
            name="voicesession.closed",
            category="Voice",
            source="VoiceSessionManager",
            payload=self.active_session.metadata.to_dict(),
        )
        self.event_bus.publish_sync(ev)

        self.active_session = None
        logger.info("Voice session finalized and closed", session=session_id)
