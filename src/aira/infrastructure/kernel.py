"""AIRA Runtime Kernel.

Coordinates configuration, logging, dependency injection, service registry,
event bus, lifecycle orchestration, and runtime context.
"""

import platform
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar, Literal

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.di_container import DependencyContainer
from aira.infrastructure.event_bus import EventBus
from aira.infrastructure.lifecycle import LifecycleOrchestrator
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.kernel")

KernelStateType = Literal[
    "CREATED",
    "BOOTSTRAPPING",
    "INITIALIZING",
    "READY",
    "RUNNING",
    "BUSY",
    "IDLE",
    "STOPPING",
    "STOPPED",
    "FAILED",
    "RECOVERING",
]


class KernelError(Exception):
    """Base exception for all runtime kernel failures."""

    pass


class InvalidKernelStateTransitionError(KernelError):
    """Raised when violating the valid kernel state machine paths."""

    pass


class RuntimeContext:
    """Centralized runtime context metadata describing application versions and environments."""

    def __init__(self, config: AppConfig) -> None:
        self.app_name: str = "AIRA"
        self.app_version: str = config.version
        self.profile: str = config.env.profile
        self.platform: str = config.env.platform
        self.architecture: str = platform.machine()
        self.working_dir: str = str(Path.cwd())
        self.data_dir: str = str(config.paths.data_dir)
        self.log_dir: str = str(config.paths.log_dir)
        self.cache_dir: str = str(config.paths.data_dir / "cache")
        self.session_id: str = uuid.uuid4().hex
        self.runtime_id: str = f"rt-{uuid.uuid4().hex[:8]}"
        self.startup_timestamp: datetime = datetime.now()
        self.state: KernelStateType = "CREATED"

    def to_dict(self) -> dict[str, Any]:
        """Serialize context to dict format."""
        return {
            "app_name": self.app_name,
            "app_version": self.app_version,
            "profile": self.profile,
            "platform": self.platform,
            "architecture": self.architecture,
            "working_dir": self.working_dir,
            "data_dir": self.data_dir,
            "log_dir": self.log_dir,
            "cache_dir": self.cache_dir,
            "session_id": self.session_id,
            "runtime_id": self.runtime_id,
            "startup_timestamp": self.startup_timestamp.isoformat(),
            "state": self.state,
        }


class AIRAKernel:
    """Enterprise Runtime Kernel coordinating all active subsystems of AIRA."""

    VALID_TRANSITIONS: ClassVar[dict[KernelStateType, set[KernelStateType]]] = {
        "CREATED": {"BOOTSTRAPPING", "FAILED"},
        "BOOTSTRAPPING": {"INITIALIZING", "FAILED"},
        "INITIALIZING": {"READY", "FAILED"},
        "READY": {"RUNNING", "STOPPING", "FAILED"},
        "RUNNING": {"BUSY", "IDLE", "STOPPING", "FAILED"},
        "BUSY": {"RUNNING", "IDLE", "FAILED"},
        "IDLE": {"RUNNING", "BUSY", "STOPPING", "FAILED"},
        "STOPPING": {"STOPPED", "FAILED"},
        "STOPPED": {"BOOTSTRAPPING", "CREATED"},
        "FAILED": {"RECOVERING", "STOPPING", "STOPPED"},
        "RECOVERING": {"INITIALIZING", "READY", "FAILED"},
    }

    def __init__(
        self,
        config: AppConfig,
        container: DependencyContainer,
        registry: ServiceRegistry,
        event_bus: EventBus,
        lifecycle: LifecycleOrchestrator,
    ) -> None:
        self.config = config
        self.container = container
        self.registry = registry
        self.event_bus = event_bus
        self.lifecycle = lifecycle

        self.state: KernelStateType = "CREATED"
        self.context = RuntimeContext(config)

        # Extension contracts/placeholders registry mappings
        self._extensions: dict[str, Any] = {}

    def transition_to(self, target_state: KernelStateType) -> None:
        """Enforce transition rules and update kernel state."""
        allowed = self.VALID_TRANSITIONS.get(self.state, set())
        if target_state not in allowed:
            err_msg = f"Kernel transition from '{self.state}' to '{target_state}' is invalid."
            logger.error(
                "Kernel state transition conflict", current=self.state, target=target_state
            )
            raise InvalidKernelStateTransitionError(err_msg)

        old_state = self.state
        self.state = target_state
        self.context.state = target_state
        logger.info("Kernel state transitioned", old_state=old_state, new_state=target_state)

    def bootstrap(self) -> None:
        """Coordinate container validation and state progression checks."""
        self.transition_to("BOOTSTRAPPING")
        try:
            # Validate registrations
            self.container.validate_container()
            self.registry.validate_registry()
            self.transition_to("INITIALIZING")
        except Exception as e:
            self.transition_to("FAILED")
            logger.error("Kernel bootstrap failed", error=str(e))
            raise KernelError(f"Subsystem bootstrap integrity failed: {e}") from e

    def start(self) -> None:
        """Startup Lifecycle Orchestrator and transition kernel to RUNNING."""
        if self.state != "INITIALIZING":
            self.bootstrap()

        try:
            self.lifecycle.startup()
            self.transition_to("READY")
            self.transition_to("RUNNING")
            logger.info("AIRA Runtime Kernel is operational.")
        except Exception as e:
            self.transition_to("FAILED")
            logger.error("Kernel failed to start core subsystems", error=str(e))
            raise KernelError(f"Subsystem startup coordination failed: {e}") from e

    def shutdown(self) -> None:
        """Trigger Lifecycle Orchestrator shutdown and transition kernel state."""
        self.transition_to("STOPPING")
        try:
            self.lifecycle.shutdown()
            self.transition_to("STOPPED")
            logger.info("AIRA Runtime Kernel shutdown complete.")
        except Exception as e:
            self.transition_to("FAILED")
            logger.error("Kernel shutdown coordination failed", error=str(e))
            raise KernelError(f"Subsystem shutdown coordination failed: {e}") from e

    def register_extension(self, name: str, extension: Any) -> None:
        """Register a runtime extension contract placeholder."""
        if name in self._extensions:
            raise KernelError(f"Extension '{name}' is already registered.")
        self._extensions[name] = extension
        logger.debug("Registered kernel extension contract placeholder", extension=name)

    def get_extension(self, name: str) -> Any:
        """Retrieve the registered extension matching name."""
        if name not in self._extensions:
            raise KernelError(f"Extension '{name}' not found.")
        return self._extensions[name]

    def get_runtime_info(self) -> dict[str, Any]:
        """Gather platform metrics, metadata catalog details, and version details."""
        startup_duration = (datetime.now() - self.context.startup_timestamp).total_seconds()
        return {
            "status": self.state,
            "context": self.context.to_dict(),
            "startup_duration_seconds": startup_duration,
            "registered_services_count": len(self.registry.list_services()),
            "extensions_count": len(self._extensions),
            "placeholders": {"cpu_usage": 0.0, "memory_usage_bytes": 0, "gpu_available": False},
        }
