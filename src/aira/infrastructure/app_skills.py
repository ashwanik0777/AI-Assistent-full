"""Enterprise Application Skill Pack for AIRA.

Provides platform-agnostic application control wrappers integrating with the Permission Manager.
"""

import subprocess
import sys
from abc import ABC, abstractmethod
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.permission_manager import PermissionManager
from aira.infrastructure.service_registry import ServiceRegistry
from aira.infrastructure.skill_engine import BaseSkill, SkillEngineError, SkillMetadata

logger = structlog.get_logger("aira.app_skills")


class UnsupportedPlatformError(SkillEngineError):
    """Raised when running app management on Windows or Linux placeholders."""

    pass


class ApplicationNotFoundError(SkillEngineError):
    """Raised when target application cannot be launched or closed."""

    pass


class BaseApplicationAdapter(ABC):
    """Abstract base class that all operating system application adapters must implement."""

    @abstractmethod
    def open_application(self, app_name: str) -> None:
        """Launch the target application by name."""
        pass

    @abstractmethod
    def close_application(self, app_name: str) -> None:
        """Quit the target application gracefully."""
        pass

    @abstractmethod
    def is_running(self, app_name: str) -> bool:
        """Assert whether application process name is currently active."""
        pass

    @abstractmethod
    def bring_to_front(self, app_name: str) -> None:
        """Bring target window forward in focus hierarchy."""
        pass

    @abstractmethod
    def list_running_applications(self) -> list[str]:
        """Query list of running active applications."""
        pass


class MacApplicationAdapter(BaseApplicationAdapter):
    """macOS Application Adapter using AppleScript."""

    def open_application(self, app_name: str) -> None:
        script = f'tell application "{app_name}" to activate'
        self._run_applescript(script)

    def close_application(self, app_name: str) -> None:
        script = f'tell application "{app_name}" to quit'
        self._run_applescript(script)

    def is_running(self, app_name: str) -> bool:
        running = self.list_running_applications()
        return any(app_name.lower() in r.lower() for r in running)

    def bring_to_front(self, app_name: str) -> None:
        script = (
            f'tell application "System Events" to set frontmost of process "{app_name}" to true'
        )
        self._run_applescript(script)

    def list_running_applications(self) -> list[str]:
        script = (
            'tell application "System Events" to get name of every process '
            "whose background only is false"
        )
        try:
            output = self._run_applescript(script)
            return [app.strip() for app in output.split(",")]
        except Exception:
            return []

    def _run_applescript(self, script: str) -> str:
        try:
            res = subprocess.run(
                ["osascript", "-e", script], capture_output=True, text=True, check=True
            )
            return res.stdout.strip()
        except subprocess.CalledProcessError as err:
            logger.warning("AppleScript execution failed", script=script, error=err.stderr)
            raise ApplicationNotFoundError(f"AppleScript error: {err.stderr}") from err


class WindowsApplicationAdapter(BaseApplicationAdapter):
    """Windows Application Adapter placeholder."""

    def open_application(self, app_name: str) -> None:
        raise UnsupportedPlatformError("Windows application control is not implemented.")

    def close_application(self, app_name: str) -> None:
        raise UnsupportedPlatformError("Windows application control is not implemented.")

    def is_running(self, app_name: str) -> bool:
        raise UnsupportedPlatformError("Windows application control is not implemented.")

    def bring_to_front(self, app_name: str) -> None:
        raise UnsupportedPlatformError("Windows application control is not implemented.")

    def list_running_applications(self) -> list[str]:
        raise UnsupportedPlatformError("Windows application control is not implemented.")


class LinuxApplicationAdapter(BaseApplicationAdapter):
    """Linux Application Adapter placeholder."""

    def open_application(self, app_name: str) -> None:
        raise UnsupportedPlatformError("Linux application control is not implemented.")

    def close_application(self, app_name: str) -> None:
        raise UnsupportedPlatformError("Linux application control is not implemented.")

    def is_running(self, app_name: str) -> bool:
        raise UnsupportedPlatformError("Linux application control is not implemented.")

    def bring_to_front(self, app_name: str) -> None:
        raise UnsupportedPlatformError("Linux application control is not implemented.")

    def list_running_applications(self) -> list[str]:
        raise UnsupportedPlatformError("Linux application control is not implemented.")


class ApplicationNameResolver:
    """Resolves shortcuts and aliases into absolute official application names."""

    def __init__(self) -> None:
        self.aliases = {
            "vs code": "Visual Studio Code",
            "vscode": "Visual Studio Code",
            "chrome": "Google Chrome",
            "terminal": "Terminal",
            "safari": "Safari",
        }

    def resolve(self, name: str) -> str:
        """Find matching resolved process string."""
        normalized = name.lower().strip()
        return self.aliases.get(normalized, name)


class ApplicationManager:
    """Coordinates target adapters, resolves alias bindings, and audits permissions."""

    def __init__(
        self,
        config: AppConfig,
        registry: ServiceRegistry,
        event_bus: EventBus,
        permission_manager: PermissionManager,
    ) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus
        self.permission_manager = permission_manager

        self.resolver = ApplicationNameResolver()

        # Instantiate platform-specific adapter
        if sys.platform == "darwin":
            self.adapter: BaseApplicationAdapter = MacApplicationAdapter()
        elif sys.platform == "win32":
            self.adapter = WindowsApplicationAdapter()
        else:
            self.adapter = LinuxApplicationAdapter()

    def open_application(self, name: str) -> None:
        """Resolve app, audit capability limits, and call launch sequence."""
        self.event_bus.publish_sync(
            Event(
                name="application.requested",
                category="Applications",
                source="ApplicationManager",
                payload={"app_name": name, "action": "OPEN"},
            )
        )

        # Check permissions
        self.permission_manager.authorize_execution(
            permission="APPLICATION_LAUNCH", capability="OPEN_APPLICATION"
        )

        resolved_name = self.resolver.resolve(name)
        self.event_bus.publish_sync(
            Event(
                name="application.resolved",
                category="Applications",
                source="ApplicationManager",
                payload={"original": name, "resolved": resolved_name},
            )
        )

        try:
            self.adapter.open_application(resolved_name)
            self.event_bus.publish_sync(
                Event(
                    name="application.opened",
                    category="Applications",
                    source="ApplicationManager",
                    payload={"app_name": resolved_name},
                )
            )
        except Exception as ex:
            self.event_bus.publish_sync(
                Event(
                    name="application.failed",
                    category="Applications",
                    source="ApplicationManager",
                    payload={"app_name": resolved_name, "error": str(ex)},
                )
            )
            raise

    def close_application(self, name: str) -> None:
        """Resolve app, audit capability limits, and call quit sequence."""
        self.event_bus.publish_sync(
            Event(
                name="application.requested",
                category="Applications",
                source="ApplicationManager",
                payload={"app_name": name, "action": "CLOSE"},
            )
        )

        # Check permissions
        self.permission_manager.authorize_execution(
            permission="APPLICATION_CONTROL", capability="CLOSE_APPLICATION"
        )

        resolved_name = self.resolver.resolve(name)
        self.event_bus.publish_sync(
            Event(
                name="application.resolved",
                category="Applications",
                source="ApplicationManager",
                payload={"original": name, "resolved": resolved_name},
            )
        )

        try:
            self.adapter.close_application(resolved_name)
            self.event_bus.publish_sync(
                Event(
                    name="application.closed",
                    category="Applications",
                    source="ApplicationManager",
                    payload={"app_name": resolved_name},
                )
            )
        except Exception as ex:
            self.event_bus.publish_sync(
                Event(
                    name="application.failed",
                    category="Applications",
                    source="ApplicationManager",
                    payload={"app_name": resolved_name, "error": str(ex)},
                )
            )
            raise


class ApplicationOpenSkill(BaseSkill):
    """AIRA execution skill for launching applications."""

    def __init__(self, manager: ApplicationManager) -> None:
        metadata = SkillMetadata(
            skill_id="app_open",
            name="Open Application Skill",
            version="0.1.0",
            description="Launch application safely",
            author="AIRA",
            category="Application",
            supported_platforms=["darwin"],
            required_permissions=["APPLICATION_LAUNCH"],
            required_capabilities=["OPEN_APPLICATION"],
            input_schema={"required": ["app_name"]},
        )
        super().__init__(metadata)
        self.manager = manager

    def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        self.validate(input_data)
        app_name = input_data["app_name"]
        self.manager.open_application(app_name)
        return {"status": "SUCCESS", "message": f"Opened application: {app_name}"}


class ApplicationCloseSkill(BaseSkill):
    """AIRA execution skill for closing applications gracefully."""

    def __init__(self, manager: ApplicationManager) -> None:
        metadata = SkillMetadata(
            skill_id="app_close",
            name="Close Application Skill",
            version="0.1.0",
            description="Quit application safely",
            author="AIRA",
            category="Application",
            supported_platforms=["darwin"],
            required_permissions=["APPLICATION_CONTROL"],
            required_capabilities=["CLOSE_APPLICATION"],
            input_schema={"required": ["app_name"]},
        )
        super().__init__(metadata)
        self.manager = manager

    def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        self.validate(input_data)
        app_name = input_data["app_name"]
        self.manager.close_application(app_name)
        return {"status": "SUCCESS", "message": f"Closed application: {app_name}"}
