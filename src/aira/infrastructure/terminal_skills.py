"""Enterprise Terminal Skill Pack for AIRA.

Provides safe command execution validation, directory checks, templates checks,
and platform terminal adapters.
"""

import subprocess
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.fs_skills import FilesystemManager, UnsafePathError
from aira.infrastructure.permission_manager import PermissionManager
from aira.infrastructure.service_registry import ServiceRegistry
from aira.infrastructure.skill_engine import BaseSkill, SkillEngineError, SkillMetadata

logger = structlog.get_logger("aira.terminal_skills")


class TerminalError(SkillEngineError):
    """Base exception for all terminal execution failures."""

    pass


class UnsafeCommandError(TerminalError):
    """Raised when running forbidden executables or parameters."""

    pass


@dataclass
class CommandSpec:
    """Detailed structural parameter properties of a command execution."""

    command_id: str
    executable: str
    arguments: list[str] = field(default_factory=list)
    cwd: Path = field(default_factory=Path)
    env: dict[str, str] = field(default_factory=dict)
    timeout: float = 30.0
    expected_exit_codes: list[int] = field(default_factory=lambda: [0])
    safety_level: str = "SAFE"
    retry_policy: int = 1


class CommandValidator:
    """Validates executables, parameters, and working directory containment."""

    def __init__(self, allowed_roots: list[Path]) -> None:
        self.allowed_roots = allowed_roots
        self.allowed_executables = {"pwd", "ls", "git", "npm", "uv", "python", "node"}
        self.blocked_executables = {
            "sudo",
            "rm",
            "kill",
            "chmod",
            "chown",
            "diskutil",
            "shutdown",
            "reboot",
            "launchctl",
        }

    def validate_spec(self, spec: CommandSpec) -> None:
        """Assert parameters, executables, and workspace path compliance."""
        # 1. Blocked executables validation
        if spec.executable in self.blocked_executables:
            raise UnsafeCommandError(f"Executable is restricted: {spec.executable}")

        # 2. Allowed templates validation
        if spec.executable not in self.allowed_executables:
            raise UnsafeCommandError(
                f"Executable not in allowed Safe Mode templates: {spec.executable}"
            )

        # 3. Argument checks to block inline shell injections
        # (e.g. semicolon, pipe, background runs)
        for arg in spec.arguments:
            for char in [";", "|", "&", "`", "$"]:
                if char in arg:
                    raise UnsafeCommandError(
                        f"Prohibited shell metacharacter found in argument: {arg}"
                    )

        # 4. Working directory validation
        try:
            resolved_cwd = spec.cwd.resolve()
        except Exception as ex:
            raise UnsafePathError(f"Failed to resolve working directory: {spec.cwd}") from ex

        is_allowed = False
        for root in self.allowed_roots:
            try:
                resolved_root = root.resolve()
                if resolved_cwd.parts[: len(resolved_root.parts)] == resolved_root.parts:
                    is_allowed = True
                    break
            except Exception:
                continue

        if not is_allowed:
            raise UnsafePathError(
                f"Working directory resolves outside allowed roots boundary: {spec.cwd}"
            )


class BaseTerminalAdapter(ABC):
    """Abstract base class that all operating system terminal adapters must implement."""

    @abstractmethod
    def execute_command(self, spec: CommandSpec) -> tuple[int, str, str]:
        """Run specification inside subprocess shell environment."""
        pass


class MacTerminalAdapter(BaseTerminalAdapter):
    """macOS Terminal Adapter using subprocess."""

    def execute_command(self, spec: CommandSpec) -> tuple[int, str, str]:
        cmd = [spec.executable, *spec.arguments]
        try:
            res = subprocess.run(
                cmd,
                cwd=str(spec.cwd),
                env=spec.env if spec.env else None,
                capture_output=True,
                text=True,
                timeout=spec.timeout,
                check=False,
            )
            return res.returncode, res.stdout, res.stderr
        except subprocess.TimeoutExpired as err:
            logger.warning("Subprocess execution timed out", cmd=cmd)
            raise TerminalError(f"Command execution timed out after {spec.timeout}s.") from err
        except Exception as ex:
            logger.error("Subprocess execution failed", cmd=cmd, error=str(ex))
            raise TerminalError(f"Subprocess run failure: {ex!s}") from ex


class WindowsTerminalAdapter(BaseTerminalAdapter):
    """Windows Terminal Adapter placeholder."""

    def execute_command(self, spec: CommandSpec) -> tuple[int, str, str]:
        raise TerminalError("Windows Terminal adapter is not implemented.")


class LinuxTerminalAdapter(BaseTerminalAdapter):
    """Linux Terminal Adapter placeholder."""

    def execute_command(self, spec: CommandSpec) -> tuple[int, str, str]:
        raise TerminalError("Linux Terminal adapter is not implemented.")


class TerminalManager:
    """Coordinates command validation, evaluations, and adapter executes."""

    def __init__(
        self,
        config: AppConfig,
        registry: ServiceRegistry,
        event_bus: EventBus,
        permission_manager: PermissionManager,
        filesystem_manager: FilesystemManager,
    ) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus
        self.permission_manager = permission_manager
        self.fs_manager = filesystem_manager

        # Allow execution only within virtual filesystem sub-roots
        allowed_roots = list(self.fs_manager.vfs.roots.values())
        self.validator = CommandValidator(allowed_roots)

        # Instantiate platform adapter
        if sys.platform == "darwin":
            self.adapter: BaseTerminalAdapter = MacTerminalAdapter()
        elif sys.platform == "win32":
            self.adapter = WindowsTerminalAdapter()
        else:
            self.adapter = LinuxTerminalAdapter()

    def run_command(
        self, executable: str, arguments: list[str], cwd_logical: str
    ) -> tuple[int, str, str]:
        """Build, validate, check permissions, and execute the command."""
        resolved_cwd = self.fs_manager.vfs.resolve_logical_path(cwd_logical)

        spec = CommandSpec(
            command_id="cmd_run", executable=executable, arguments=arguments, cwd=resolved_cwd
        )

        self.event_bus.publish_sync(
            Event(
                name="terminal.command_built",
                category="Terminal",
                source="TerminalManager",
                payload={"executable": executable, "arguments": arguments},
            )
        )

        # Check permissions gate
        self.permission_manager.authorize_execution(
            permission="TERMINAL_ACCESS", capability="RUN_COMMAND"
        )

        # Validate specifications and workspace bounds
        self.validator.validate_spec(spec)
        self.event_bus.publish_sync(
            Event(
                name="terminal.command_validated",
                category="Terminal",
                source="TerminalManager",
                payload={"executable": executable},
            )
        )

        self.event_bus.publish_sync(
            Event(
                name="terminal.sandbox_ready",
                category="Terminal",
                source="TerminalManager",
                payload={},
            )
        )

        self.event_bus.publish_sync(
            Event(
                name="terminal.execution_started",
                category="Terminal",
                source="TerminalManager",
                payload={"executable": executable},
            )
        )

        try:
            exit_code, stdout, stderr = self.adapter.execute_command(spec)

            self.event_bus.publish_sync(
                Event(
                    name="terminal.execution_finished",
                    category="Terminal",
                    source="TerminalManager",
                    payload={"exit_code": exit_code},
                )
            )

            return exit_code, stdout, stderr
        except Exception as ex:
            self.event_bus.publish_sync(
                Event(
                    name="terminal.execution_failed",
                    category="Terminal",
                    source="TerminalManager",
                    payload={"error": str(ex)},
                )
            )
            raise


class TerminalExecuteSkill(BaseSkill):
    """AIRA execution skill for command-line runs."""

    def __init__(self, manager: TerminalManager) -> None:
        metadata = SkillMetadata(
            skill_id="terminal_execute",
            name="Terminal Execute Skill",
            version="0.1.0",
            description="Run command line programs safely",
            author="AIRA",
            category="Terminal",
            supported_platforms=["darwin"],
            required_permissions=["TERMINAL_ACCESS"],
            required_capabilities=["RUN_COMMAND"],
            input_schema={"required": ["executable", "arguments", "cwd"]},
        )
        super().__init__(metadata)
        self.manager = manager

    def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        self.validate(input_data)
        exit_code, stdout, stderr = self.manager.run_command(
            executable=input_data["executable"],
            arguments=input_data["arguments"],
            cwd_logical=input_data["cwd"],
        )
        status = (
            "SUCCESS"
            if exit_code in self.metadata.output_schema.get("success_codes", [0])
            else "FAILED"
        )
        return {"status": status, "exit_code": exit_code, "stdout": stdout, "stderr": stderr}
