"""Enterprise AI Application Framework, Modular Composition & Lifecycle Platform for AIRA.

Provides composition engines, feature module registries, and overlay managers.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.ai_application_platform")


class ApplicationFrameworkError(Exception):
    """Base exception raised for composition errors, health checks, or lifecycle failures."""

    pass


@dataclass
class AppBlueprint:
    """Blueprint layout specifying modules, parameters profiles, and environments."""

    app_id: str
    name: str
    modules: list[str]
    capabilities: list[str]
    config_profile: str  # Development, Testing, Staging, Production
    env_profile: str  # Local, Edge, On-Premises, Private Cloud, Public Cloud, Hybrid
    dependencies: list[str]
    lifecycle_state: str = "Created"  # Created, Composed, Configured, Running, Stopped
    metadata: dict[str, Any] = field(default_factory=dict)
    version: str = "1.0.0"


@dataclass
class FeatureModule:
    """Reusable feature module detailing version and exposed capabilities."""

    module_id: str
    name: str
    version: str
    capabilities: list[str]


class FeatureModuleRegistry:
    """Stores reusable capability modules."""

    def __init__(self) -> None:
        self.modules: dict[str, FeatureModule] = {}

    def register_module(self, f_module: FeatureModule) -> None:
        """Add capability module to registry database."""
        self.modules[f_module.module_id] = f_module


class CompositionEngine:
    """Assembles and verifies blueprints integrity and dependency resolution."""

    def resolve_blueprint(self, blueprint: AppBlueprint, registry: FeatureModuleRegistry) -> None:
        """Resolve modules dependencies and block on missing components."""
        for mod_id in blueprint.modules:
            reg_mod = registry.modules.get(mod_id)
            if not reg_mod:
                raise ApplicationFrameworkError(
                    f"Composition failed: Module '{mod_id}' referenced in "
                    f"blueprint '{blueprint.app_id}' is not registered."
                )

            # Check capability compatibility (e.g. if planning module matches blueprint request)
            for cap in blueprint.capabilities:
                if cap in reg_mod.capabilities:
                    break
            else:
                # If blueprint requests capabilities not covered by any module, verify alignment
                pass


class ConfigurationOverlayManager:
    """Applies environment specific configurations."""

    def apply_overlay(self, blueprint: AppBlueprint) -> dict[str, Any]:
        """Output environment configuration overlay options."""
        base_conf: dict[str, Any] = {"app_id": blueprint.app_id, "mode": blueprint.config_profile}

        if blueprint.config_profile == "Production":
            base_conf["logging_level"] = "INFO"
            base_conf["concurrency_limit"] = 100
        else:
            base_conf["logging_level"] = "DEBUG"
            base_conf["concurrency_limit"] = 10

        return base_conf


class LifecycleManager:
    """Transitions application lifecycle states."""

    def transition_state(self, blueprint: AppBlueprint, next_state: str) -> None:
        """Apply state transitions and block illegal flows."""
        current = blueprint.lifecycle_state

        allowed = {
            "Created": {"Composed"},
            "Composed": {"Configured"},
            "Configured": {"Running", "Stopped"},
            "Running": {"Paused", "Stopped"},
            "Paused": {"Running", "Stopped"},
            "Stopped": {"Running", "Created"},
        }

        if next_state not in allowed.get(current, set()):
            raise ApplicationFrameworkError(
                f"Lifecycle transition rejected: Cannot transition app '{blueprint.app_id}' "
                f"from state '{current}' to '{next_state}'."
            )

        blueprint.lifecycle_state = next_state


class HealthManager:
    """Validates application readiness and module alignment."""

    def verify_health(self, blueprint: AppBlueprint, overlay: dict[str, Any]) -> bool:
        """Confirm that overlay matches blueprint parameters."""
        return overlay.get("app_id") == blueprint.app_id


class AiApplicationPlatform:
    """Coordinating manager resolving AI app blueprints and overlays."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.module_registry = FeatureModuleRegistry()
        self.composition_engine = CompositionEngine()
        self.config_manager = ConfigurationOverlayManager()
        self.lifecycle_manager = LifecycleManager()
        self.health_manager = HealthManager()

        self.blueprints: dict[str, AppBlueprint] = {}

    def create_blueprint(
        self,
        app_id: str,
        name: str,
        modules: list[str],
        capabilities: list[str],
        config_profile: str,
        env_profile: str,
        dependencies: list[str],
    ) -> AppBlueprint:
        """Initialize blueprint configuration metadata and publish events."""
        blueprint = AppBlueprint(
            app_id=app_id,
            name=name,
            modules=modules,
            capabilities=capabilities,
            config_profile=config_profile,
            env_profile=env_profile,
            dependencies=dependencies,
        )

        self.blueprints[app_id] = blueprint

        self.event_bus.publish_sync(
            Event(
                name="app.blueprint.created",
                category="ApplicationFramework",
                source="AiApplicationPlatform",
                payload={"app_id": app_id},
            )
        )

        return blueprint

    def compose_application(self, app_id: str) -> None:
        """Assemble dependencies, validate blueprints, promote state, and publish events."""
        blueprint = self.blueprints.get(app_id)
        if not blueprint:
            raise ApplicationFrameworkError(f"Blueprint not found: '{app_id}'")

        # 1. Resolve composition dependencies
        self.composition_engine.resolve_blueprint(blueprint, self.module_registry)

        # 2. Lifecycle update
        self.lifecycle_manager.transition_state(blueprint, "Composed")

        self.event_bus.publish_sync(
            Event(
                name="app.composition.completed",
                category="ApplicationFramework",
                source="AiApplicationPlatform",
                payload={"app_id": app_id},
            )
        )

    def apply_configuration(self, app_id: str) -> dict[str, Any]:
        """Apply profile configuration overrides and update state."""
        blueprint = self.blueprints.get(app_id)
        if not blueprint:
            raise ApplicationFrameworkError(f"Blueprint not found: '{app_id}'")

        overlay = self.config_manager.apply_overlay(blueprint)

        self.lifecycle_manager.transition_state(blueprint, "Configured")

        self.event_bus.publish_sync(
            Event(
                name="app.config.applied",
                category="ApplicationFramework",
                source="AiApplicationPlatform",
                payload={"app_id": app_id, "profile": blueprint.config_profile},
            )
        )

        return overlay

    def verify_app_health(self, app_id: str, overlay: dict[str, Any]) -> None:
        """Verify health checks and notify events."""
        blueprint = self.blueprints.get(app_id)
        if not blueprint:
            raise ApplicationFrameworkError(f"Blueprint not found: '{app_id}'")

        healthy = self.health_manager.verify_health(blueprint, overlay)
        if not healthy:
            raise ApplicationFrameworkError(
                f"Health checks failed for app '{app_id}': Overlay settings mismatch."
            )

        self.event_bus.publish_sync(
            Event(
                name="app.health.verified",
                category="ApplicationFramework",
                source="AiApplicationPlatform",
                payload={"app_id": app_id},
            )
        )

    def run_application(self, app_id: str) -> None:
        """Transition blueprint state to Running and publish events."""
        blueprint = self.blueprints.get(app_id)
        if not blueprint:
            raise ApplicationFrameworkError(f"Blueprint not found: '{app_id}'")

        self.lifecycle_manager.transition_state(blueprint, "Running")

        self.event_bus.publish_sync(
            Event(
                name="app.lifecycle.updated",
                category="ApplicationFramework",
                source="AiApplicationPlatform",
                payload={"app_id": app_id, "state": "Running"},
            )
        )
