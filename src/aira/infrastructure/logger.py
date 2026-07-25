"""Centralized Enterprise Logging System for AIRA.

Manages daily log rotation, structured logging, custom levels (SUCCESS),
secret scrubbing, and category-based file routing.
"""

import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any, ClassVar

import structlog

from aira.infrastructure.config import AppConfig

# Define Custom SUCCESS Log Level (value 25, between INFO 20 and WARNING 30)
SUCCESS_LEVEL_NUM = 25
logging.addLevelName(SUCCESS_LEVEL_NUM, "SUCCESS")


def success(self: logging.Logger, message: str, *args: Any, **kws: Any) -> None:
    """Custom logging success method attached to logging.Logger instances."""
    if self.isEnabledFor(SUCCESS_LEVEL_NUM):
        self._log(SUCCESS_LEVEL_NUM, message, args, **kws)


# Bind custom success helper to stdlib Logger class dynamically
logging.Logger.success = success  # type: ignore


# Secret keywords to scrub from log values
SECRET_KEYS = {
    "password",
    "secret",
    "token",
    "api_key",
    "private_key",
    "credentials",
    "key",
    "auth",
    "passwd",
}


def scrub_secrets_processor(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Structlog processor to recursively scrub sensitive values from log contents."""

    def _scrub(item: Any) -> Any:
        if isinstance(item, dict):
            return {
                k: ("[SCRUBBED]" if k.lower() in SECRET_KEYS else _scrub(v))
                for k, v in item.items()
            }
        elif isinstance(item, list):
            return [_scrub(x) for x in item]
        return item

    res = _scrub(event_dict)
    assert isinstance(res, dict)
    return res


class AIRALoggerManager:
    """Manages creation, directory mapping, and configurations of system loggers."""

    _initialized = False
    _config: AppConfig | None = None
    _handlers: ClassVar[dict[str, logging.Handler]] = {}

    @classmethod
    def initialize(cls, config: AppConfig) -> None:
        """Create subdirectories and set up structured logging configurations."""
        if cls._initialized:
            return

        cls._config = config

        # 1. Automatically create and manage logs/ directories
        base_log_dir = config.paths.log_dir
        sub_dirs = ["application", "security", "performance", "crash", "audit", "debug", "startup"]
        for sub in sub_dirs:
            (base_log_dir / sub).mkdir(parents=True, exist_ok=True)

        # 2. Configure processors for structlog
        shared_processors: list[Any] = [
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            scrub_secrets_processor,
        ]

        # 3. Setup File Rotators (Daily rotation)
        log_level_num = getattr(logging, config.logging.level)

        # Set up stdlib root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(log_level_num)

        # Clear existing handlers
        root_logger.handlers.clear()

        # Console Handler
        if config.logging.console_logging:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(log_level_num)
            root_logger.addHandler(console_handler)
            cls._handlers["console"] = console_handler

        # Category mapping for file handlers
        cls._setup_file_handler(
            "application", base_log_dir / "application" / "application.log", log_level_num
        )
        cls._setup_file_handler(
            "security", base_log_dir / "security" / "security.log", log_level_num
        )
        cls._setup_file_handler(
            "performance", base_log_dir / "performance" / "performance.log", log_level_num
        )
        cls._setup_file_handler("crash", base_log_dir / "crash" / "crash.log", logging.ERROR)
        cls._setup_file_handler("audit", base_log_dir / "audit" / "audit.log", log_level_num)
        cls._setup_file_handler("debug", base_log_dir / "debug" / "debug.log", logging.DEBUG)
        cls._setup_file_handler("startup", base_log_dir / "startup" / "startup.log", log_level_num)

        # Register category file handlers to root logger so everything flows into them
        for handler in cls._handlers.values():
            if handler != cls._handlers.get("console"):
                root_logger.addHandler(handler)

        # Configure Structlog
        structlog.configure(
            processors=[
                *shared_processors,
                structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )

        # Connect formatter mappings
        formatter = structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processor=structlog.dev.ConsoleRenderer(colors=config.env.profile == "development"),
        )

        # Future JSON formatting fallback config
        # formatter = structlog.stdlib.ProcessorFormatter(
        #     foreign_pre_chain=shared_processors,
        #     processor=structlog.processors.JSONRenderer(),
        # )

        for handler in root_logger.handlers:
            handler.setFormatter(formatter)

        cls._initialized = True

    @classmethod
    def _setup_file_handler(cls, name: str, path: Path, level: int) -> None:
        """Create a daily TimedRotatingFileHandler for a specific category."""
        # 30 days log retention policy
        handler = TimedRotatingFileHandler(
            str(path), when="D", interval=1, backupCount=30, encoding="utf-8"
        )
        handler.setLevel(level)
        cls._handlers[name] = handler

    @classmethod
    def get_logger(cls, category: str) -> Any:
        """Return a structured context-specific logger instance."""
        # Standardize logger category tagging
        return structlog.get_logger(f"aira.{category}")


def setup_logger(config: AppConfig) -> Any:
    """Wired hook compatible with bootstrap configurations, initializing managers."""
    AIRALoggerManager.initialize(config)
    return AIRALoggerManager.get_logger("system")
