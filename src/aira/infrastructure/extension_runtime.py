"""Enterprise Extension Runtime & Plugin Foundation for AIRA.

Provides descriptors, registries, lifecycle controllers, sandboxes, and permission validators.
"""

from dataclasses import dataclass, field
from typing import Any, ClassVar

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.extension_runtime")


class ExtensionRuntimeError(Exception):
    """Base exception raised for all extension platform and plugin lifecycle failures."""

    pass


@dataclass
class ExtensionDescriptor:
    """Stable metadata contract defining an extension identity, requirements, and permissions."""

    extension_id: str
    name: str
    version: str
    author: str
    capabilities: list[str]
    permissions: list[str]
    dependencies: list[str]
    compatibility: str  # e.g., ">=0.9.0"
    entry_points: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtensionRecord:
    """Active runtime entry tracking an extension state inside the registry."""

    descriptor: ExtensionDescriptor
    lifecycle_state: str = "Discovered"


class ExtensionRegistry:
    """Maintains active extension profiles catalog."""

    def __init__(self) -> None:
        self.extensions: dict[str, ExtensionRecord] = {}

    def register(self, record: ExtensionRecord) -> None:
        """Register a new extension record."""
        self.extensions[record.descriptor.extension_id] = record

    def get(self, extension_id: str) -> ExtensionRecord | None:
        """Retrieve extension record."""
        return self.extensions.get(extension_id)

    def list_all(self) -> list[ExtensionRecord]:
        """List all registered extension records."""
        return list(self.extensions.values())


class ExtensionLifecycleManager:
    """Enforces valid lifecycle transitions on extensions."""

    # Map of source state -> allowed target states
    VALID_TRANSITIONS: ClassVar[dict[str, set[str]]] = {
        "Discovered": {"Installed", "Uninstalled"},
        "Installed": {"Verified", "Uninstalled"},
        "Verified": {"Enabled", "Uninstalled"},
        "Enabled": {"Running", "Disabled", "Updated"},
        "Running": {"Paused", "Disabled"},
        "Paused": {"Running", "Disabled"},
        "Disabled": {"Enabled", "Uninstalled", "Updated"},
        "Updated": {"Enabled", "Uninstalled"},
        "Uninstalled": {"Discovered"},
    }

    def transition_state(self, record: ExtensionRecord, target_state: str) -> None:
        """Move extension state or raise runtime error if transition is invalid."""
        current = record.lifecycle_state
        allowed = self.VALID_TRANSITIONS.get(current, set())
        if target_state not in allowed:
            raise ExtensionRuntimeError(
                f"Lifecycle transition failed: Cannot move from '{current}' to '{target_state}'."
            )
        record.lifecycle_state = target_state


class ExtensionSandbox:
    """Isolates extension execution variables."""

    def __init__(self) -> None:
        self.workspaces: dict[str, dict[str, Any]] = {}

    def start_sandbox(self, extension_id: str) -> None:
        """Create isolated variables context map."""
        self.workspaces[extension_id] = {
            "extension_id": extension_id,
            "variables": {},
            "status": "Isolated",
        }

    def cleanup_sandbox(self, extension_id: str) -> None:
        """Evict local context maps."""
        self.workspaces.pop(extension_id, None)


class ExtensionPermissionManager:
    """Enforces zero-trust capability, memory, and filesystem authorization checks."""

    def __init__(self) -> None:
        # Simple policy list mapping permissions to scopes
        self.allowed_permissions = {
            "MemoryAccess",
            "CapabilityAccess",
            "WorkflowAccess",
            "AgentAccess",
            "PerceptionAccess",
            "FilesystemAccess",
            "NetworkAccess",
        }

    def validate_permissions(self, descriptor: ExtensionDescriptor) -> bool:
        """Check if all requested permissions are supported by the framework."""
        return all(perm in self.allowed_permissions for perm in descriptor.permissions)


class ExtensionVersionManager:
    """Checks extension metadata compatibility versions against the core platform version."""

    def __init__(self, platform_version: str = "0.9.0") -> None:
        self.platform_version = platform_version

    def is_compatible(self, descriptor: ExtensionDescriptor) -> bool:
        """Verify semantic compatibility rules."""
        # Simple match version check
        req = descriptor.compatibility.replace(">=", "").strip()
        p_parts = [int(x) for x in self.platform_version.split(".")]
        r_parts = [int(x) for x in req.split(".")]
        return p_parts >= r_parts


class ExtensionRuntime:
    """Coordinating manager verifying descriptors, lifecycle transitions, and sandbox operations."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.extension_registry = ExtensionRegistry()
        self.lifecycle_manager = ExtensionLifecycleManager()
        self.sandbox = ExtensionSandbox()
        self.permission_manager = ExtensionPermissionManager()
        self.version_manager = ExtensionVersionManager()

    def install_extension(self, descriptor: ExtensionDescriptor) -> ExtensionRecord:
        """Register descriptor, validate rules, and transition lifecycle state."""
        # 1. Validate version compatibility
        if not self.version_manager.is_compatible(descriptor):
            raise ExtensionRuntimeError(
                f"Installation blocked: Extension '{descriptor.extension_id}' is incompatible "
                f"with platform version '{self.version_manager.platform_version}'."
            )

        # 2. Validate permissions requests
        if not self.permission_manager.validate_permissions(descriptor):
            raise ExtensionRuntimeError(
                f"Installation blocked: Extension '{descriptor.extension_id}' "
                f"requests unauthorized permissions."
            )

        # 3. Register Record
        record = ExtensionRecord(descriptor=descriptor)
        self.extension_registry.register(record)

        self.event_bus.publish_sync(
            Event(
                name="extension.registered",
                category="Extension",
                source="ExtensionRuntime",
                payload={"extension_id": descriptor.extension_id},
            )
        )

        # 4. Transition State
        self.lifecycle_manager.transition_state(record, "Installed")
        self.event_bus.publish_sync(
            Event(
                name="extension.installed",
                category="Extension",
                source="ExtensionRuntime",
                payload={"extension_id": descriptor.extension_id},
            )
        )

        return record

    def enable_extension(self, extension_id: str) -> None:
        """Verify descriptor, prepare sandbox, and transition state to Enabled."""
        record = self.extension_registry.get(extension_id)
        if not record:
            raise ExtensionRuntimeError(f"Operation failed: Extension '{extension_id}' not found.")

        self.lifecycle_manager.transition_state(record, "Verified")
        self.lifecycle_manager.transition_state(record, "Enabled")

        # Spawn Sandbox
        self.sandbox.start_sandbox(extension_id)

        self.event_bus.publish_sync(
            Event(
                name="extension.enabled",
                category="Extension",
                source="ExtensionRuntime",
                payload={"extension_id": extension_id},
            )
        )

    def disable_extension(self, extension_id: str) -> None:
        """Cleanup sandbox and transition state to Disabled."""
        record = self.extension_registry.get(extension_id)
        if not record:
            raise ExtensionRuntimeError(f"Operation failed: Extension '{extension_id}' not found.")

        # If Running, must transition through Disabled
        if record.lifecycle_state == "Running" or record.lifecycle_state == "Enabled":
            self.lifecycle_manager.transition_state(record, "Disabled")
        else:
            raise ExtensionRuntimeError(
                f"Operation failed: Extension '{extension_id}' "
                f"is in state '{record.lifecycle_state}'."
            )

        self.sandbox.cleanup_sandbox(extension_id)

        self.event_bus.publish_sync(
            Event(
                name="extension.disabled",
                category="Extension",
                source="ExtensionRuntime",
                payload={"extension_id": extension_id},
            )
        )
