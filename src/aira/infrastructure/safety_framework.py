"""Enterprise Execution Safety Framework for AIRA.

Provides independent risk scoring, policy validation checks, and safety approval engines
before executing any capability skill.
"""

from enum import Enum
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.permission_manager import PermissionManager
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.safety_framework")


class SafetyRiskLevel(Enum):
    """Supported risk levels classification ranks."""

    SAFE = "SAFE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    BLOCKED = "BLOCKED"


class SafetyDecision(Enum):
    """Supported authorization outcomes returned by the approval engine."""

    APPROVED = "APPROVED"
    DENIED = "DENIED"
    REQUIRE_CONFIRMATION = "REQUIRE_CONFIRMATION"
    SANDBOX_ONLY = "SANDBOX_ONLY"
    READ_ONLY = "READ_ONLY"


class SafetyError(Exception):
    """Raised when an operation fails safety constraints validation."""

    pass


class RiskAnalyzer:
    """Assigns security risk categories based on requested commands and parameters."""

    def __init__(self) -> None:
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
        self.allowed_executables = {"pwd", "ls", "git", "npm", "uv", "python", "node"}

    def evaluate_risk(self, skill_id: str, input_data: dict[str, Any]) -> SafetyRiskLevel:
        """Analyze skill parameters to classify overall risk category."""
        # 1. Terminal skill specific validation
        if skill_id == "terminal_execute":
            executable = input_data.get("executable", "").strip()
            args = input_data.get("arguments", [])

            # Blocked commands checks
            if executable in self.blocked_executables:
                return SafetyRiskLevel.BLOCKED

            # Check args for hazardous sequences (e.g. -rf, rm)
            for arg in args:
                arg_lc = arg.lower()
                if "rm " in arg_lc or "-rf" in arg_lc or "kill" in arg_lc:
                    return SafetyRiskLevel.BLOCKED

            # Unknown commands validation checks
            if executable not in self.allowed_executables:
                return SafetyRiskLevel.HIGH  # Unknown command requires review

            return SafetyRiskLevel.SAFE

        # 2. Filesystem skill specific validation
        if skill_id in ["file_write", "create_folder"]:
            path_str = input_data.get("path", "").strip()
            # Prohibit system paths modification
            for system_root in ["/System", "/private", "/etc", "/var", "/bin", "/sbin"]:
                if path_str.startswith(system_root) or f"/{system_root}" in path_str:
                    return SafetyRiskLevel.BLOCKED
            return SafetyRiskLevel.SAFE

        # 3. Application launches specific checks
        if skill_id == "app_open":
            return SafetyRiskLevel.SAFE

        return SafetyRiskLevel.LOW


class PolicyEngine:
    """Audits execution requests against configured security policies."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.read_only = False
        self.dry_run = False

    def validate_policy(self, skill_id: str, input_data: dict[str, Any]) -> bool:
        """Verify whether request conforms to active policy parameters."""
        if self.read_only and skill_id in ["file_write", "create_folder", "terminal_execute"]:
            # If terminal execute changes file, block in read-only mode
            if skill_id == "terminal_execute":
                exec_name = input_data.get("executable", "")
                if exec_name in ["npm", "uv"]:  # Mapped changes
                    return False
            if skill_id in ["file_write", "create_folder"]:
                return False
        return True


class ApprovalManager:
    """Resolves ultimate safety decision outputs."""

    def __init__(self, policy_engine: PolicyEngine) -> None:
        self.policy = policy_engine

    def resolve_decision(self, risk: SafetyRiskLevel) -> SafetyDecision:
        """Translate risk categories into safety authorization decisions."""
        if risk == SafetyRiskLevel.BLOCKED:
            return SafetyDecision.DENIED
        if risk in [SafetyRiskLevel.HIGH, SafetyRiskLevel.CRITICAL]:
            return SafetyDecision.REQUIRE_CONFIRMATION
        if self.policy.dry_run:
            return SafetyDecision.SANDBOX_ONLY
        if self.policy.read_only:
            return SafetyDecision.READ_ONLY
        return SafetyDecision.APPROVED


class SafetyEngine:
    """Coordinating gateway analyzing risk and authorizing executions."""

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

        self.analyzer = RiskAnalyzer()
        self.policy = PolicyEngine(config)
        self.approval = ApprovalManager(self.policy)

    def authorize_execution(self, skill_id: str, input_data: dict[str, Any]) -> SafetyDecision:
        """Validate safety pipeline and authorize execution."""
        # 1. Risk Analysis
        risk = self.analyzer.evaluate_risk(skill_id, input_data)
        self.event_bus.publish_sync(
            Event(
                name="safety.risk_evaluated",
                category="Safety",
                source="SafetyEngine",
                payload={"skill_id": skill_id, "risk": risk.value},
            )
        )

        # 2. Policy Engine Checks
        policy_ok = self.policy.validate_policy(skill_id, input_data)
        if not policy_ok:
            self.event_bus.publish_sync(
                Event(
                    name="safety.execution_blocked",
                    category="Safety",
                    source="SafetyEngine",
                    payload={"reason": "Policy violation"},
                )
            )
            return SafetyDecision.DENIED

        self.event_bus.publish_sync(
            Event(name="safety.policy_passed", category="Safety", source="SafetyEngine", payload={})
        )

        # 3. Resolve Decision
        decision = self.approval.resolve_decision(risk)
        self.event_bus.publish_sync(
            Event(
                name="safety.approval_requested",
                category="Safety",
                source="SafetyEngine",
                payload={"decision": decision.value},
            )
        )

        if decision == SafetyDecision.DENIED:
            self.event_bus.publish_sync(
                Event(
                    name="safety.execution_blocked",
                    category="Safety",
                    source="SafetyEngine",
                    payload={"reason": "Risk blocked"},
                )
            )
            return SafetyDecision.DENIED

        self.event_bus.publish_sync(
            Event(
                name="safety.approval_granted", category="Safety", source="SafetyEngine", payload={}
            )
        )

        self.event_bus.publish_sync(
            Event(
                name="safety.execution_authorized",
                category="Safety",
                source="SafetyEngine",
                payload={},
            )
        )

        return decision
