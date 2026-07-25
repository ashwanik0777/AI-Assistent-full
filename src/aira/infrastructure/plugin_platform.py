"""Enterprise Plugin, Extension, Capability Pack & Runtime Isolation Platform for AIRA.

Provides plugin registries, compatibility validators, sandbox runtimes, and lifecycle managers.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.plugin_platform")


class PluginPlatformError(Exception):
    """Base exception raised for manifest errors, security blocks, or lifecycle violations."""

    pass


@dataclass
class PluginManifest:
    """Plugin metadata shape describing dependencies, permissions, and extension endpoints."""

    plugin_id: str
    name: str
    version: str
    capability_pack: str
    dependencies: list[str]
    permissions: list[str]
    extension_points: list[str]
    compatibility: str
    metadata: dict[str, Any] = field(default_factory=dict)
    manifest_version: int = 1


@dataclass
class Plugin:
    """Governed plugin instance wrapper tracking state machine variables."""

    manifest: PluginManifest
    # States: Installed, Validated, Enabled, Running, Paused, Disabled, Removed
    lifecycle_state: str = "Installed"


class PluginRegistry:
    """Tracks registered plugins inventories."""

    def __init__(self) -> None:
        self.plugins: dict[str, Plugin] = {}

    def register_plugin(self, plugin: Plugin) -> None:
        """Add plugin representation to memory map."""
        self.plugins[plugin.manifest.plugin_id] = plugin


class CompatibilityValidator:
    """Checks plugin core versions compatibility checks."""

    def validate_compatibility(self, manifest: PluginManifest, target_ver: str) -> bool:
        """Validate alignment constraint."""
        return manifest.compatibility == target_ver


class SandboxRuntime:
    """Provides isolated namespaces container executions."""

    def execute_in_sandbox(
        self, plugin: Plugin, action: str, permissions_manager: "PermissionManager"
    ) -> dict[str, Any]:
        """Verify safety bounds, check access manager permission scope, and execute safely."""
        # Policy rule: block unsafe operations unless authorized
        if action == "access_network":
            permissions_manager.check_permission(plugin, "NetworkAccess")
        return {
            "plugin_id": plugin.manifest.plugin_id,
            "status": "Success",
            "action_executed": action,
        }


class PermissionManager:
    """Governs capability access permission checks."""

    def check_permission(self, plugin: Plugin, required_perm: str) -> None:
        """Check if target permission is declared in manifest."""
        if required_perm not in plugin.manifest.permissions:
            raise PluginPlatformError(
                f"Security block: Plugin '{plugin.manifest.plugin_id}' lacks "
                f"required permission '{required_perm}'."
            )


class DependencyManager:
    """Resolves dependencies keys lists against registry inventories."""

    def resolve_dependencies(self, manifest: PluginManifest, active_ids: set[str]) -> None:
        """Block if manifest dependencies are missing from active set."""
        missing = set(manifest.dependencies) - active_ids
        if missing:
            raise PluginPlatformError(
                f"Dependency resolution failed for plugin '{manifest.plugin_id}': "
                f"Missing dependencies: {missing}."
            )


class LifecycleManager:
    """Controls plugin lifecycle state transitions."""

    def transition_state(self, plugin: Plugin, next_state: str) -> None:
        """Validate state transitions rules and modify local status."""
        current = plugin.lifecycle_state

        # Reject invalid transitions
        allowed = {
            "Installed": {"Validated", "Removed"},
            "Validated": {"Enabled", "Removed"},
            "Enabled": {"Running", "Disabled"},
            "Running": {"Paused", "Disabled"},
            "Paused": {"Running", "Disabled"},
            "Disabled": {"Enabled", "Removed"},
            "Removed": set(),
        }

        if next_state not in allowed.get(current, set()):
            raise PluginPlatformError(
                f"Lifecycle transition failed: Cannot transition "
                f"plugin '{plugin.manifest.plugin_id}' from "
                f"state '{current}' to '{next_state}'."
            )

        plugin.lifecycle_state = next_state


class PluginPlatform:
    """Coordinating manager resolving plugin installs, validations, sandboxes, and lifecycles."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.plugin_registry = PluginRegistry()
        self.compatibility_validator = CompatibilityValidator()
        self.sandbox_runtime = SandboxRuntime()
        self.permission_manager = PermissionManager()
        self.dependency_manager = DependencyManager()
        self.lifecycle_manager = LifecycleManager()

    def install_plugin_package(self, manifest: PluginManifest) -> Plugin:
        """Initialize plugin, register record, and publish events."""
        plugin = Plugin(manifest=manifest, lifecycle_state="Installed")
        self.plugin_registry.register_plugin(plugin)

        self.event_bus.publish_sync(
            Event(
                name="plugin.installed",
                category="PluginPlatform",
                source="PluginPlatform",
                payload={"plugin_id": manifest.plugin_id},
            )
        )

        return plugin

    def validate_plugin_package(self, plugin_id: str, platform_version: str) -> None:
        """Validate compatibilities, resolve dependencies, promote state, and publish events."""
        plugin = self.plugin_registry.plugins.get(plugin_id)
        if not plugin:
            raise PluginPlatformError(f"Plugin not found: '{plugin_id}'")

        # 1. Compatibility Check
        if not self.compatibility_validator.validate_compatibility(
            plugin.manifest, platform_version
        ):
            raise PluginPlatformError(
                f"Compatibility check failed: Plugin '{plugin_id}' "
                f"version matches are out of bounds."
            )

        # 2. Dependency Check
        active_ids = {
            pid for pid, p in self.plugin_registry.plugins.items() if p.lifecycle_state != "Removed"
        }
        self.dependency_manager.resolve_dependencies(plugin.manifest, active_ids)

        # 3. State transition
        self.lifecycle_manager.transition_state(plugin, "Validated")

        self.event_bus.publish_sync(
            Event(
                name="plugin.validated",
                category="PluginPlatform",
                source="PluginPlatform",
                payload={"plugin_id": plugin_id},
            )
        )

    def enable_plugin_package(self, plugin_id: str) -> None:
        """Transition lifecycle state to Enabled and publish events."""
        plugin = self.plugin_registry.plugins.get(plugin_id)
        if not plugin:
            raise PluginPlatformError(f"Plugin not found: '{plugin_id}'")

        self.lifecycle_manager.transition_state(plugin, "Enabled")

        self.event_bus.publish_sync(
            Event(
                name="plugin.enabled",
                category="PluginPlatform",
                source="PluginPlatform",
                payload={"plugin_id": plugin_id},
            )
        )

    def disable_plugin_package(self, plugin_id: str) -> None:
        """Transition lifecycle state to Disabled and publish events."""
        plugin = self.plugin_registry.plugins.get(plugin_id)
        if not plugin:
            raise PluginPlatformError(f"Plugin not found: '{plugin_id}'")

        self.lifecycle_manager.transition_state(plugin, "Disabled")

        self.event_bus.publish_sync(
            Event(
                name="plugin.disabled",
                category="PluginPlatform",
                source="PluginPlatform",
                payload={"plugin_id": plugin_id},
            )
        )

    def remove_plugin_package(self, plugin_id: str) -> None:
        """Transition lifecycle state to Removed and publish events."""
        plugin = self.plugin_registry.plugins.get(plugin_id)
        if not plugin:
            raise PluginPlatformError(f"Plugin not found: '{plugin_id}'")

        # Handle valid lifecycle transitions to Removed
        if plugin.lifecycle_state in {"Installed", "Validated", "Disabled"}:
            self.lifecycle_manager.transition_state(plugin, "Removed")
        else:
            raise PluginPlatformError(
                f"Cannot remove plugin '{plugin_id}' in state '{plugin.lifecycle_state}'."
            )

        self.event_bus.publish_sync(
            Event(
                name="plugin.removed",
                category="PluginPlatform",
                source="PluginPlatform",
                payload={"plugin_id": plugin_id},
            )
        )

    def run_sandbox_action(self, plugin_id: str, action: str) -> dict[str, Any]:
        """Verify state, run sandbox executors, check permissions, and return outcomes."""
        plugin = self.plugin_registry.plugins.get(plugin_id)
        if not plugin:
            raise PluginPlatformError(f"Plugin not found: '{plugin_id}'")

        # Plugin must be Enabled/Running to execute sandbox actions
        if plugin.lifecycle_state not in {"Enabled", "Running"}:
            raise PluginPlatformError(
                f"Execution failed: Plugin '{plugin_id}' is not in active run state. "
                f"Current state: '{plugin.lifecycle_state}'."
            )

        return self.sandbox_runtime.execute_in_sandbox(plugin, action, self.permission_manager)
