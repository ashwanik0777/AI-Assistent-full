"""Enterprise Command Intelligence & Terminal Adapter subsystem for AIRA.

Provides command planning engines, risk classifiers allowlists, and execution wrappers.
"""

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.command_intelligence")


class CommandIntelligenceError(Exception):
    """Raised when command validations, execution planning policies, or risk checks fail."""

    pass


@dataclass
class CommandObject:
    """Structured execution properties of a target CLI command task."""

    command_id: str
    purpose: str
    executable: str
    arguments: list[str] = field(default_factory=list)
    working_directory: str = ""
    environment: dict[str, str] = field(default_factory=dict)
    timeout: int = 30
    permissions: list[str] = field(default_factory=list)
    risk_level: str = "Safe"
    expected_output: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    version: str = "1.0.0"


class BaseTerminalAdapter(ABC):
    """Generic interface adapter contract matching local and container shell execution hosts."""

    @abstractmethod
    def execute_command(self, cmd: CommandObject) -> dict[str, Any]:
        """Execute client command session synchronously returning logs payloads."""
        pass

    @abstractmethod
    def cancel_command(self, command_id: str) -> None:
        """Terminate target active subprocess mapping."""
        pass

    @abstractmethod
    def detect_environment(self) -> dict[str, Any]:
        """Return operating system platform environment metadata (Python, Node)."""
        pass


class TerminalAdapter(BaseTerminalAdapter):
    """Concrete Terminal adapter simulating shell executions safely."""

    def __init__(self) -> None:
        self.active_processes: dict[str, bool] = {}

    def execute_command(self, cmd: CommandObject) -> dict[str, Any]:
        self.active_processes[cmd.command_id] = True
        duration = 0.05
        exit_code = 0
        stdout = f"Simulated output for executable: {cmd.executable} with args {cmd.arguments}"
        stderr = ""

        # Simulated response mappings
        if cmd.executable == "git" and "status" in cmd.arguments:
            stdout = "On branch feature/phase7\nnothing to commit, working tree clean"
        elif cmd.executable == "npm" and "install" in cmd.arguments:
            stdout = "added 120 packages, audited 121 packages in 2s"
        elif cmd.executable == "python" and "--version" in cmd.arguments:
            stdout = "Python 3.11.2"

        self.active_processes.pop(cmd.command_id, None)

        return {
            "status": "Success",
            "exit_code": exit_code,
            "duration": duration,
            "stdout": stdout,
            "stderr": stderr,
            "warnings": [],
            "errors": [],
        }

    def cancel_command(self, command_id: str) -> None:
        self.active_processes.pop(command_id, None)

    def detect_environment(self) -> dict[str, Any]:
        return {
            "python_env": "Python 3.11 VirtualEnv detected",
            "node_env": "Node.js v18.0.0 detected",
            "package_managers": ["npm", "Poetry", "uv"],
            "path_metadata": "/usr/bin:/bin:/usr/sbin:/sbin",
        }


class CommandValidator:
    """Checks executable targets, arguments structures, and paths mappings validity."""

    def validate_command(self, cmd: CommandObject) -> None:
        """Reject empty executables or non-directory working paths."""
        if not cmd.executable:
            raise CommandIntelligenceError("Command executable name cannot be empty.")
        if cmd.working_directory and not os.path.isdir(cmd.working_directory):
            raise CommandIntelligenceError(
                f"Working directory '{cmd.working_directory}' does not exist."
            )


class RiskAnalyzer:
    """Classifies command execution risk indexes based on allowlists/denylists rules."""

    def __init__(self) -> None:
        self.denied_executables = ["sudo", "rm", "format", "reboot", "poweroff", "mkfs"]

    def analyze_risk(self, cmd: CommandObject) -> str:
        """Return risk assessment category based on executable types."""
        exe = cmd.executable.lower()
        if exe in self.denied_executables:
            return "Critical"

        # Medium risk for dependency installation package commands
        if exe in ["npm", "pip", "poetry", "cargo"] and any(
            arg in cmd.arguments for arg in ["install", "add", "update"]
        ):
            return "Medium"

        if exe in ["git", "ls", "echo", "pwd", "python", "node"]:
            return "Safe"

        return "Low"


class ExecutionPlanner:
    """Plans CLI script workflows mapping dry run simulations or approval overrides."""

    def plan_execution(self, cmd: CommandObject, risk_level: str) -> str:
        """Resolve planner strategy based on risk level class."""
        if risk_level == "Critical":
            return "Rejected (Policy violation)"
        if risk_level in ["High"]:
            return "Approval Required"
        if risk_level == "Medium":
            return "Simulation Mode"
        return "Normal Execution"


class EnvironmentManager:
    """Resolves local PATH, Node/Python runtime configurations context."""

    def __init__(self, adapter: BaseTerminalAdapter) -> None:
        self.adapter = adapter

    def get_runtime_context(self) -> dict[str, Any]:
        """Load target terminal adapter environment settings."""
        return self.adapter.detect_environment()


class OutputParser:
    """Normalizes exit codes, stdout summaries, and durations properties."""

    def parse_output(self, raw_result: dict[str, Any]) -> dict[str, Any]:
        """Aggregate exit code indicators and format execution summaries."""
        exit_code = raw_result.get("exit_code", 0)
        status = "Success" if exit_code == 0 else "Failed"

        return {
            "status": status,
            "exit_code": exit_code,
            "duration": raw_result.get("duration", 0.0),
            "warnings_count": len(raw_result.get("warnings", [])),
            "summary": f"Command finished with status: {status}",
        }


class CommandIntelligenceManager:
    """Unified manager planning, validating, and executing commands safely."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.adapter = TerminalAdapter()
        self.validator = CommandValidator()
        self.risk_analyzer = RiskAnalyzer()
        self.planner = ExecutionPlanner()
        self.env_manager = EnvironmentManager(self.adapter)
        self.output_parser = OutputParser()

    def execute_command(self, cmd: CommandObject) -> dict[str, Any]:
        """Plan, validate, risk classify, and execute command safely."""
        self.event_bus.publish_sync(
            Event(
                name="command.planned",
                category="Terminal",
                source="CommandIntelligenceManager",
                payload={"command_id": cmd.command_id, "executable": cmd.executable},
            )
        )

        # 1. Validate
        self.validator.validate_command(cmd)
        self.event_bus.publish_sync(
            Event(
                name="validation.completed",
                category="Terminal",
                source="CommandIntelligenceManager",
                payload={"command_id": cmd.command_id},
            )
        )

        # 2. Risk Classification
        risk = self.risk_analyzer.analyze_risk(cmd)
        cmd.risk_level = risk

        # 3. Execution Plan
        plan = self.planner.plan_execution(cmd, risk)
        if plan == "Rejected (Policy violation)" or risk == "Critical":
            self.event_bus.publish_sync(
                Event(
                    name="execution.failed",
                    category="Terminal",
                    source="CommandIntelligenceManager",
                    payload={"command_id": cmd.command_id, "reason": "Security policy violation"},
                )
            )
            raise CommandIntelligenceError(
                f"Security Policy violation: Command '{cmd.executable}' is blocked."
            )

        # 4. Execute (simulated via adapter)
        self.event_bus.publish_sync(
            Event(
                name="execution.started",
                category="Terminal",
                source="CommandIntelligenceManager",
                payload={"command_id": cmd.command_id},
            )
        )

        raw_result = self.adapter.execute_command(cmd)

        self.event_bus.publish_sync(
            Event(
                name="execution.finished",
                category="Terminal",
                source="CommandIntelligenceManager",
                payload={"command_id": cmd.command_id},
            )
        )

        # 5. Parse Output
        parsed = self.output_parser.parse_output(raw_result)

        self.event_bus.publish_sync(
            Event(
                name="output.parsed",
                category="Terminal",
                source="CommandIntelligenceManager",
                payload={"command_id": cmd.command_id, "status": parsed["status"]},
            )
        )

        return parsed
