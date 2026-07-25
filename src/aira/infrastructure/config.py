"""Enterprise Configuration System for AIRA.

Manages strongly-typed configuration settings, profile validation, and macOS-first,
offline-first defaults.
"""

import sys
from pathlib import Path
from typing import Literal

from platformdirs import PlatformDirs
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Default application namespaces
_dirs = PlatformDirs("aira", "ashwanik0777")


class EnvironmentSettings(BaseModel):
    """Detects and validates runtime environments and platform compatibility."""

    profile: Literal["development", "testing", "production"] = Field(default="development")
    platform: str = Field(default=sys.platform)

    @field_validator("platform")
    @classmethod
    def validate_macos_first(cls, val: str) -> str:
        """Enforce warnings or validations prioritizing macOS environments."""
        if val != "darwin":
            # We don't hard crash to allow developer testing, but warn
            print(f"[Warning] Platform detected as '{val}'. AIRA is optimized for macOS (darwin).")
        return val


class PathSettings(BaseModel):
    """Manages application directory systems on disk."""

    data_dir: Path = Field(default=Path(_dirs.user_data_dir))
    config_dir: Path = Field(default=Path(_dirs.user_config_dir))
    log_dir: Path = Field(default=Path(_dirs.user_log_dir))
    cache_dir: Path = Field(default=Path(_dirs.user_cache_dir))

    @property
    def backup_dir(self) -> Path:
        """Directory for system database backups."""
        return self.data_dir / "backups"

    @property
    def skills_dir(self) -> Path:
        """Directory for loading user custom skills."""
        return self.config_dir / "skills"

    @property
    def plugins_dir(self) -> Path:
        """Directory for third-party executable plugins."""
        return self.config_dir / "plugins"


class LoggingSettings(BaseModel):
    """Configures system event auditing parameters."""

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(default="INFO")
    console_logging: bool = Field(default=True)
    file_logging: bool = Field(default=True)


class FeatureFlags(BaseModel):
    """Runtime toggles for system sub-modules."""

    enable_voice: bool = Field(default=False)
    enable_vision: bool = Field(default=False)
    enable_browser: bool = Field(default=False)
    enable_plugins: bool = Field(default=False)
    offline_only: bool = Field(default=True)  # Offline-first default


class AISettings(BaseModel):
    """Model router parameters (placeholders)."""

    default_model: str = Field(default="phi-3-mini")
    local_model_name: str = Field(default="phi-3-mini")
    cloud_model_name: str = Field(default="claude-3-5-sonnet")
    temperature: float = Field(default=0.0)
    max_tokens: int = Field(default=2048)
    local_endpoint: str = Field(default="http://localhost:11434")


class PluginSettings(BaseModel):
    """Auditing and loader limits for plugin integrations (placeholders)."""

    autostart_plugins: bool = Field(default=False)
    allowed_plugins: set[str] = Field(default_factory=set)


class SecuritySettings(BaseModel):
    """Permission framework and isolation rules (placeholders)."""

    enable_sandboxing: bool = Field(default=True)
    require_confirmation_for_destructive: bool = Field(default=True)
    allowed_shell_commands: set[str] = Field(default_factory=lambda: {"ls", "git status", "pwd"})


class VoiceSettings(BaseModel):
    """Configuration settings for speech recognition and wake words."""

    wake_word: str = Field(default="Hey AIRA")
    supported_wake_words: list[str] = Field(
        default_factory=lambda: ["Hey AIRA", "AIRA", "Hello AIRA"]
    )
    wake_sensitivity: float = Field(default=0.5)
    wake_confidence_threshold: float = Field(default=0.7)
    wake_cooldown_seconds: float = Field(default=2.0)
    wake_engine_type: Literal["openwakeword", "porcupine"] = Field(default="openwakeword")
    stt_engine_type: Literal["faster_whisper", "whisper_cpp"] = Field(default="faster_whisper")
    stt_language: str = Field(default="en")
    stt_model_size: str = Field(default="base")
    session_timeout_seconds: float = Field(default=30.0)
    intent_confidence_threshold: float = Field(default=0.6)


class AppConfig(BaseSettings):
    """Immutable root config loader integrating all subsystem settings."""

    version: str = Field(default="0.1.0")
    env: EnvironmentSettings = Field(default_factory=EnvironmentSettings)
    paths: PathSettings = Field(default_factory=PathSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    features: FeatureFlags = Field(default_factory=FeatureFlags)
    ai: AISettings = Field(default_factory=AISettings)
    voice: VoiceSettings = Field(default_factory=VoiceSettings)
    plugins: PluginSettings = Field(default_factory=PluginSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)

    # Nest environment config parsing using AIRA_ prefix and __ delimiters
    model_config = SettingsConfigDict(
        env_prefix="AIRA_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
        frozen=True,  # Immutable after initialization
    )

    @field_validator("version")
    @classmethod
    def validate_version_format(cls, val: str) -> str:
        """Enforce strict semantic version format rules."""
        parts = val.split(".")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            raise ValueError(f"Invalid semantic version format: {val}")
        return val


def load_config() -> AppConfig:
    """Instantiate and validate system configuration once."""
    return AppConfig()
