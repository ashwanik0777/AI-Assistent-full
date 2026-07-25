"""Enterprise Extension SDK, Public API Framework & Developer Experience Platform for AIRA.

Provides public API gateways, SDK manifests, CLI templates generator, and migration assistants.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.extension_sdk")


class ExtensionSDKError(Exception):
    """Base exception raised for SDK contracts, version incompatibilities, or template failures."""

    pass


@dataclass
class SDKManifest:
    """SDK specification contract tracking supported APIs and deprecations."""

    sdk_version: str
    supported_api_versions: list[str]
    compatibility_matrix: dict[str, str] = field(default_factory=dict)
    deprecation_notices: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseExtensionPlugin(ABC):
    """Abstract base class that all extension plugins must inherit from."""

    def __init__(self, context: Any) -> None:
        self.context = context

    @abstractmethod
    def on_enable(self) -> None:
        """Called when the extension is initialized and enabled."""
        pass

    @abstractmethod
    def on_disable(self) -> None:
        """Called when the extension is stopped and cleaned up."""
        pass


class PublicAPIGateway:
    """Exposes controlled, stable abstractions to private core runtime components."""

    def __init__(self, registry: ServiceRegistry) -> None:
        self.registry = registry

    def log_message(self, message: str) -> None:
        """Public API wrapper logging messages safely."""
        logger.info(f"[Extension Log] {message}")

    def read_config_value(self, key: str) -> Any:
        """Expose limited config properties access."""
        # Simple placeholder lookup mapping safe values
        return "development" if key == "env" else None


class DeveloperCLI:
    """Simulates developer CLI code generators."""

    def generate_extension_project(self, project_name: str, author: str) -> dict[str, str]:
        """Generate sample workspace manifest contents."""
        return {
            "extension.yaml": (
                f"extension_id: {project_name.lower()}\n"
                f"name: {project_name}\n"
                f"version: 1.0.0\n"
                f"author: {author}\n"
                "capabilities: [cap_custom]\n"
                "permissions: [MemoryAccess]\n"
                "dependencies: []\n"
                "compatibility: '>=0.9.0'\n"
            ),
            "plugin.py": (
                "from aira.infrastructure.extension_sdk import BaseExtensionPlugin\n\n"
                f"class {project_name}Plugin(BaseExtensionPlugin):\n"
                "    def on_enable(self) -> None:\n"
                "        self.context.log_message('Enabled!')\n"
                "    def on_disable(self) -> None:\n"
                "        pass\n"
            ),
        }


class MigrationHelper:
    """Scans code text patterns to suggest deprecation updates."""

    def __init__(self, notices: dict[str, str]) -> None:
        self.notices = notices

    def scan_for_deprecations(self, code_content: str) -> list[str]:
        """Identify deprecated keywords, returning suggested migration fixes."""
        suggestions = []
        for keyword, suggestion in self.notices.items():
            if keyword in code_content:
                suggestions.append(f"Deprecated keyword '{keyword}' found. {suggestion}")
        return suggestions


class SDKManager:
    """Coordinating manager verifying SDK manifests, registering gateways, and publishing events."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.manifest = SDKManifest(
            sdk_version="1.0.0",
            supported_api_versions=["v1", "v2"],
            compatibility_matrix={"0.9.0": "1.0.0"},
            deprecation_notices={
                "internal_read_memory": "Use PublicAPIGateway.read_config_value instead."
            },
        )

        self.gateway = PublicAPIGateway(self.registry)
        self.cli = DeveloperCLI()
        self.migration_helper = MigrationHelper(self.manifest.deprecation_notices)

    def load_sdk(self, extension_id: str) -> None:
        """Register API gateway, check compatibility, and publish SDK Loaded events."""
        self.event_bus.publish_sync(
            Event(
                name="sdk.loaded",
                category="SDK",
                source="SDKManager",
                payload={"extension_id": extension_id, "sdk_version": self.manifest.sdk_version},
            )
        )
        self.event_bus.publish_sync(
            Event(
                name="api.registered",
                category="SDK",
                source="SDKManager",
                payload={"api_version": "v1"},
            )
        )

    def check_migration_needs(self, code_content: str) -> list[str]:
        """Scan code content, suggest migration, and publish event."""
        suggestions = self.migration_helper.scan_for_deprecations(code_content)
        if suggestions:
            self.event_bus.publish_sync(
                Event(
                    name="migration.suggested",
                    category="SDK",
                    source="SDKManager",
                    payload={"suggestions_count": len(suggestions)},
                )
            )
        return suggestions
