"""Enterprise Permission & Capability Manager for AIRA.

Provides runtime security authorization gates verifying permissions and
capabilities before any task execution.
"""

from typing import Literal

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.permission_manager")

PermissionDecision = Literal["ALLOW", "DENY", "CONFIRM", "SANDBOX", "READ_ONLY"]

PermissionCategory = Literal[
    "FILESYSTEM_ACCESS",
    "APPLICATION_LAUNCH",
    "APPLICATION_CONTROL",
    "TERMINAL_ACCESS",
    "BROWSER_ACCESS",
    "CLIPBOARD_ACCESS",
    "NETWORK_ACCESS",
    "SYSTEM_SETTINGS",
    "PROCESS_MANAGEMENT",
]

CapabilityCategory = Literal[
    "OPEN_APPLICATION",
    "CLOSE_APPLICATION",
    "READ_FILE",
    "WRITE_FILE",
    "CREATE_FOLDER",
    "DELETE_FILE",
    "RUN_COMMAND",
    "OPEN_URL",
    "OPEN_BROWSER",
    "NAVIGATE_BROWSER",
    "BROWSER_ACTION",
    "CLIPBOARD_READ",
    "CLIPBOARD_WRITE",
]


class PermissionError(Exception):
    """Base exception for all security/permission validation failures."""

    pass


class UnknownPermissionError(PermissionError):
    """Raised when validating unregistered permissions or capabilities."""

    pass


class PermissionManager:
    """Security authorization orchestrator auditing skill execution access rules."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        # Default authorization rules configuration overrides
        self.rules: dict[str, PermissionDecision] = {
            "FILESYSTEM_ACCESS": "ALLOW",
            "APPLICATION_LAUNCH": "ALLOW",
            "APPLICATION_CONTROL": "ALLOW",
            "TERMINAL_ACCESS": "CONFIRM",
            "BROWSER_ACCESS": "ALLOW",
            "CLIPBOARD_ACCESS": "ALLOW",
            "NETWORK_ACCESS": "ALLOW",
            "SYSTEM_SETTINGS": "CONFIRM",
            "PROCESS_MANAGEMENT": "DENY",
        }

        self.capabilities: dict[str, str] = {
            "OPEN_APPLICATION": "APPLICATION_LAUNCH",
            "CLOSE_APPLICATION": "APPLICATION_CONTROL",
            "READ_FILE": "FILESYSTEM_ACCESS",
            "WRITE_FILE": "FILESYSTEM_ACCESS",
            "CREATE_FOLDER": "FILESYSTEM_ACCESS",
            "DELETE_FILE": "FILESYSTEM_ACCESS",
            "RUN_COMMAND": "TERMINAL_ACCESS",
            "OPEN_URL": "BROWSER_ACCESS",
            "OPEN_BROWSER": "BROWSER_ACCESS",
            "NAVIGATE_BROWSER": "BROWSER_ACCESS",
            "BROWSER_ACTION": "BROWSER_ACCESS",
            "CLIPBOARD_READ": "CLIPBOARD_ACCESS",
            "CLIPBOARD_WRITE": "CLIPBOARD_ACCESS",
        }

    def authorize_execution(self, permission: str, capability: str) -> PermissionDecision:
        """Evaluate rules and grant, deny, or trigger confirm dialogs."""
        self.event_bus.publish_sync(
            Event(
                name="permission.requested",
                category="Security",
                source="PermissionManager",
                payload={"permission": permission, "capability": capability},
            )
        )

        # 1. Capability Verification
        if capability not in self.capabilities:
            self.event_bus.publish_sync(
                Event(
                    name="permission.failed",
                    category="Security",
                    source="PermissionManager",
                    payload={"error": f"Unknown capability: {capability}"},
                )
            )
            raise UnknownPermissionError(f"Capability category is not registered: {capability}")

        # 2. Permission Verification
        mapped_permission = self.capabilities[capability]
        if mapped_permission != permission:
            err_msg = f"Permission mismatch: {permission} does not match {mapped_permission}"
            self.event_bus.publish_sync(
                Event(
                    name="permission.failed",
                    category="Security",
                    source="PermissionManager",
                    payload={"error": err_msg},
                )
            )
            raise PermissionError(
                f"Specified permission {permission} does not match capability mapping."
            )

        self.event_bus.publish_sync(
            Event(
                name="capability.validated",
                category="Security",
                source="PermissionManager",
                payload={"capability": capability},
            )
        )

        # 3. Policy Verification
        decision = self.rules.get(permission, "DENY")

        if decision == "ALLOW":
            self.event_bus.publish_sync(
                Event(
                    name="permission.granted",
                    category="Security",
                    source="PermissionManager",
                    payload={"permission": permission},
                )
            )
        elif decision == "CONFIRM":
            self.event_bus.publish_sync(
                Event(
                    name="permission.approval_required",
                    category="Security",
                    source="PermissionManager",
                    payload={"permission": permission},
                )
            )
        else:
            self.event_bus.publish_sync(
                Event(
                    name="permission.denied",
                    category="Security",
                    source="PermissionManager",
                    payload={"permission": permission},
                )
            )
            raise PermissionError(f"Action blocked by policy decision: {decision}")

        logger.info(
            "Permission evaluation completed",
            permission=permission,
            capability=capability,
            decision=decision,
        )
        return decision
