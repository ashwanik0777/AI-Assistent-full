"""Enterprise Audio Engine for AIRA.

Manages audio device discovery, format validation, session state lifecycles,
circular buffer streaming, and device managers.
"""

from typing import Any, ClassVar, Literal

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.audio")

AudioSessionStateType = Literal[
    "IDLE", "DEVICE_READY", "LISTENING", "STREAMING", "BUFFERING", "PAUSED", "STOPPED", "RELEASED"
]
AudioFormatType = Literal["PCM", "WAV", "FLAC", "OPUS", "MP3"]


class AudioEngineError(Exception):
    """Base exception for all audio engine failures."""

    pass


class InvalidAudioSessionTransitionError(AudioEngineError):
    """Raised when violating the valid audio session state machine paths."""

    pass


class AudioBufferError(AudioEngineError):
    """Raised on buffer overflows or underflows."""

    pass


class AudioDeviceError(AudioEngineError):
    """Raised on device disconnects or missing permissions."""

    pass


class AudioFormatConfig:
    """Format and layout definitions for captured audio frames."""

    def __init__(
        self,
        sample_rate: int = 16000,
        bit_depth: int = 16,
        channels: int = 1,
        buffer_size: int = 1024,
        format_type: AudioFormatType = "PCM",
    ) -> None:
        self.sample_rate = sample_rate
        self.bit_depth = bit_depth
        self.channels = channels
        self.buffer_size = buffer_size
        self.format_type = format_type

    def validate(self) -> None:
        """Validate sample rates and configuration limits."""
        if self.sample_rate not in [8000, 16000, 32000, 44100, 48000]:
            raise AudioEngineError(f"Unsupported sample rate: {self.sample_rate}")
        if self.bit_depth not in [8, 16, 24, 32]:
            raise AudioEngineError(f"Unsupported bit depth: {self.bit_depth}")
        if self.channels not in [1, 2]:
            raise AudioEngineError(f"Unsupported channels configuration: {self.channels}")
        if self.buffer_size <= 0:
            raise AudioEngineError(f"Invalid buffer size: {self.buffer_size}")


class AudioDevice:
    """Descriptor model for physical or virtual audio capture devices."""

    def __init__(
        self, device_id: int, name: str, max_input_channels: int, default_sample_rate: float
    ) -> None:
        self.device_id = device_id
        self.name = name
        self.max_input_channels = max_input_channels
        self.default_sample_rate = default_sample_rate

    def to_dict(self) -> dict[str, Any]:
        """Serialize device descriptor."""
        return {
            "device_id": self.device_id,
            "name": self.name,
            "max_input_channels": self.max_input_channels,
            "default_sample_rate": self.default_sample_rate,
        }


class CircularAudioBuffer:
    """Fixed-size bytearray circular ring buffer for real-time audio streams."""

    def __init__(self, capacity_bytes: int = 65536) -> None:
        self._capacity = capacity_bytes
        self._buffer = bytearray(capacity_bytes)
        self._read_idx = 0
        self._write_idx = 0
        self._size = 0

        self.overflow_count = 0
        self.underflow_count = 0

    def write(self, data: bytes) -> None:
        """Write incoming PCM data into the ring buffer, raising overflow if full."""
        length = len(data)
        if length > self._capacity - self._size:
            self.overflow_count += 1
            logger.warning(
                "Audio buffer overflow detected",
                available=self._capacity - self._size,
                length=length,
            )
            raise AudioBufferError("Circular buffer overflow.")

        # Write chunks
        for byte in data:
            self._buffer[self._write_idx] = byte
            self._write_idx = (self._write_idx + 1) % self._capacity
        self._size += length

    def read(self, size_bytes: int) -> bytes:
        """Read data from the circular buffer, raising underflow if empty."""
        if size_bytes > self._size:
            self.underflow_count += 1
            logger.warning("Audio buffer underflow detected", size=self._size, requested=size_bytes)
            raise AudioBufferError("Circular buffer underflow.")

        out = bytearray(size_bytes)
        for i in range(size_bytes):
            out[i] = self._buffer[self._read_idx]
            self._read_idx = (self._read_idx + 1) % self._capacity
        self._size -= size_bytes
        return bytes(out)

    def size(self) -> int:
        """Return the current amount of bytes in the buffer."""
        return self._size

    def capacity(self) -> int:
        """Return maximum buffer capacity in bytes."""
        return self._capacity

    def clear(self) -> None:
        """Reset read/write pointers and drop statistics."""
        self._read_idx = 0
        self._write_idx = 0
        self._size = 0


class AudioDeviceManager:
    """Discovers, validates, and manages audio device states."""

    def __init__(self) -> None:
        # Generate mock input devices as fallback
        self._devices: list[AudioDevice] = [
            AudioDevice(0, "MacBook Built-in Microphone", 1, 16000.0),
            AudioDevice(1, "External USB Audio Adapter", 2, 44100.0),
            AudioDevice(2, "Bluetooth Headphones Microphone", 1, 8000.0),
        ]
        self._selected_device_id: int = 0

    def list_input_devices(self) -> list[AudioDevice]:
        """Enumerate active microphones."""
        return self._devices

    def select_device(self, device_id: int) -> None:
        """Select target input microphone by ID."""
        valid_ids = [d.device_id for d in self._devices]
        if device_id not in valid_ids:
            logger.error("Failed to select audio device", target=device_id)
            raise AudioDeviceError(f"Audio device ID {device_id} not found.")
        self._selected_device_id = device_id
        logger.info("Selected active input audio device", device=device_id)

    def get_selected_device(self) -> AudioDevice:
        """Return active device descriptor."""
        return self._devices[self._selected_device_id]


class AudioManager:
    """Central manager for audio captures, session transitions, and buffers."""

    VALID_TRANSITIONS: ClassVar[dict[AudioSessionStateType, set[AudioSessionStateType]]] = {
        "IDLE": {"DEVICE_READY", "RELEASED"},
        "DEVICE_READY": {"LISTENING", "RELEASED", "IDLE"},
        "LISTENING": {"STREAMING", "BUFFERING", "PAUSED", "STOPPED", "RELEASED"},
        "STREAMING": {"BUFFERING", "PAUSED", "STOPPED", "RELEASED"},
        "BUFFERING": {"STREAMING", "PAUSED", "STOPPED", "RELEASED"},
        "PAUSED": {"STREAMING", "LISTENING", "STOPPED", "RELEASED"},
        "STOPPED": {"IDLE", "DEVICE_READY", "RELEASED"},
        "RELEASED": {"IDLE"},
    }

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.format_config = AudioFormatConfig()
        self.device_manager = AudioDeviceManager()
        self.buffer = CircularAudioBuffer()

        self.state: AudioSessionStateType = "IDLE"

        # Pipeline hooks/placeholders
        self._noise_reduction_hooks: list[Any] = []
        self._vad_hooks: list[Any] = []
        self._enhancement_hooks: list[Any] = []

    def transition_to(self, target_state: AudioSessionStateType) -> None:
        """Transition audio session state and publish lifecycle notifications."""
        allowed = self.VALID_TRANSITIONS.get(self.state, set())
        if target_state not in allowed:
            err_msg = f"Audio transition from '{self.state}' to '{target_state}' is invalid."
            logger.error("Audio state transition conflict", current=self.state, target=target_state)
            raise InvalidAudioSessionTransitionError(err_msg)

        old_state = self.state
        self.state = target_state

        # Dispatch event notifications
        ev = Event(
            name="audio.session.state",
            category="Audio",
            source="AudioManager",
            payload={"old_state": old_state, "new_state": target_state},
        )
        self.event_bus.publish_sync(ev)
        logger.info("Audio session state transitioned", old_state=old_state, new_state=target_state)

    def initialize(self) -> None:
        """Validate layout configs and set device ready."""
        self.format_config.validate()
        self.transition_to("DEVICE_READY")

    def start_listening(self) -> None:
        """Transition state and prepare buffer streams."""
        if self.state != "DEVICE_READY":
            raise AudioEngineError("Cannot start listening; device not ready.")
        self.buffer.clear()
        self.transition_to("LISTENING")

    def stop_listening(self) -> None:
        """Stop captured streams."""
        if self.state not in ["LISTENING", "STREAMING", "BUFFERING", "PAUSED"]:
            raise AudioEngineError("Cannot stop listening; not active.")
        self.transition_to("STOPPED")

    def record_chunk(self, data: bytes) -> None:
        """Write raw frame bytes directly to internal circular buffer."""
        if self.state not in ["LISTENING", "STREAMING", "BUFFERING"]:
            raise AudioEngineError("Cannot record chunk; stream not active.")

        # Apply preprocessing hooks placeholders
        for hook in self._noise_reduction_hooks:
            data = hook(data)
        for hook in self._enhancement_hooks:
            data = hook(data)

        self.buffer.write(data)

    def get_audio_diagnostics(self) -> dict[str, Any]:
        """Return diagnostic metrics including buffer offsets and overflows."""
        return {
            "state": self.state,
            "selected_device": self.device_manager.get_selected_device().to_dict(),
            "buffer": {
                "size_bytes": self.buffer.size(),
                "capacity_bytes": self.buffer.capacity(),
                "overflows": self.buffer.overflow_count,
                "underflows": self.buffer.underflow_count,
            },
            "format": {
                "sample_rate": self.format_config.sample_rate,
                "channels": self.format_config.channels,
                "bit_depth": self.format_config.bit_depth,
            },
        }
