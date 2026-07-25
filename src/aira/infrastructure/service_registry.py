"""Enterprise Service Registry for AIRA.

Provides runtime discovery, category cataloging, capability indices, and health metadata
independent of dependency injection object instantiation.
"""

import json
import uuid
from datetime import datetime
from typing import Any, ClassVar, Literal

import structlog

from aira.infrastructure.di_container import DependencyContainer

logger = structlog.get_logger("aira.registry")

ServiceStatusType = Literal[
    "REGISTERED", "INITIALIZING", "READY", "BUSY", "DISABLED", "FAILED", "STOPPED", "UNKNOWN"
]


class RegistryError(Exception):
    """Base exception for all service registry errors."""

    pass


class DuplicateServiceError(RegistryError):
    """Raised when registering a service that already exists in the catalog."""

    pass


class InvalidMetadataError(RegistryError):
    """Raised when validation check fails on service descriptors."""

    pass


class ServiceNotFoundError(RegistryError):
    """Raised when attempting action on unregistered services."""

    pass


class ServiceDescriptor:
    """Complete runtime descriptor, routing metadata, capabilities, and health statistics."""

    def __init__(
        self,
        name: str,
        category: str,
        description: str,
        version: str,
        owner: str = "core",
        tags: set[str] | None = None,
        dependencies: list[str] | None = None,
        is_experimental: bool = False,
        is_internal: bool = True,
        visibility: Literal["public", "private"] = "private",
    ) -> None:
        self.name = name
        self.category = category
        self.description = description
        self.version = version
        self.owner = owner
        self.tags = tags or set()
        self.dependencies = dependencies or []
        self.is_experimental = is_experimental
        self.is_internal = is_internal
        self.visibility = visibility

        # Runtime Status
        self.status: ServiceStatusType = "REGISTERED"

        # Unique Runtime Identifier
        self.uid: str = f"srv-{name}-{uuid.uuid4().hex[:8]}"
        self.registered_at: datetime = datetime.now()

        # Health Monitoring Placeholders (Sprint 1.5 Integration Points)
        self.health_score: float = 100.0
        self.last_check: datetime | None = None
        self.last_failure: datetime | None = None
        self.failure_count: int = 0
        self.recovery_count: int = 0
        self.uptime_start: datetime | None = None

        # Capability Integration Placeholders (Sprint 1.5 Integration Points)
        self.capabilities: list[str] = []
        self.permission_requirements: list[str] = []
        self.supported_operations: list[str] = []

    def transition_to(self, new_status: ServiceStatusType) -> None:
        """Execute state transition logs and update descriptor state."""
        old_status = self.status
        self.status = new_status
        if new_status == "READY" and old_status != "READY":
            self.uptime_start = datetime.now()
        logger.debug(
            "Service status transitioned",
            service=self.name,
            old_status=old_status,
            new_status=new_status,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize descriptor to dict format."""
        return {
            "name": self.name,
            "uid": self.uid,
            "category": self.category,
            "description": self.description,
            "version": self.version,
            "owner": self.owner,
            "tags": list(self.tags),
            "dependencies": self.dependencies,
            "is_experimental": self.is_experimental,
            "is_internal": self.is_internal,
            "visibility": self.visibility,
            "status": self.status,
            "registered_at": self.registered_at.isoformat(),
            "health": {
                "score": self.health_score,
                "last_check": self.last_check.isoformat() if self.last_check else None,
                "last_failure": self.last_failure.isoformat() if self.last_failure else None,
                "failure_count": self.failure_count,
                "recovery_count": self.recovery_count,
            },
            "capabilities": {
                "list": self.capabilities,
                "permissions": self.permission_requirements,
                "operations": self.supported_operations,
            },
        }


class ServiceRegistry:
    """Centralized Service Registry tracking runtime categories, metadata, and status checks."""

    # Pre-defined core categories
    VALID_CATEGORIES: ClassVar[set[str]] = {
        "Core",
        "Configuration",
        "Logging",
        "Memory",
        "Database",
        "Plugin",
        "Skill",
        "Voice",
        "Vision",
        "Automation",
        "AI",
        "Security",
        "Utilities",
        "Testing",
    }

    def __init__(self, di_container: DependencyContainer) -> None:
        self._container = di_container
        self._registry: dict[str, ServiceDescriptor] = {}

    def register_service(self, descriptor: ServiceDescriptor) -> None:
        """Register a service descriptor in the catalog."""
        if descriptor.name in self._registry:
            err_msg = f"Service '{descriptor.name}' is already registered."
            logger.error("Registration failed", service=descriptor.name)
            raise DuplicateServiceError(err_msg)

        if descriptor.category not in self.VALID_CATEGORIES:
            err_msg = (
                f"Category '{descriptor.category}' is invalid. Allowed: {self.VALID_CATEGORIES}"
            )
            logger.error(
                "Registration failed - invalid category",
                service=descriptor.name,
                category=descriptor.category,
            )
            raise InvalidMetadataError(err_msg)

        self._registry[descriptor.name] = descriptor
        logger.info(
            "Registered service in registry catalog",
            service=descriptor.name,
            category=descriptor.category,
        )

    def unregister_service(self, name: str) -> None:
        """Remove a service descriptor from the catalog."""
        if name not in self._registry:
            raise ServiceNotFoundError(f"Service '{name}' is not in registry.")
        self._registry.pop(name)
        logger.info("Unregistered service from catalog", service=name)

    def update_service(
        self, name: str, status: ServiceStatusType, health_score: float | None = None
    ) -> None:
        """Update runtime status metrics of a registered service descriptor."""
        if name not in self._registry:
            raise ServiceNotFoundError(f"Service '{name}' is not in registry.")
        descriptor = self._registry[name]
        descriptor.transition_to(status)
        if health_score is not None:
            descriptor.health_score = health_score
            descriptor.last_check = datetime.now()
            if health_score < 100.0:
                descriptor.last_failure = datetime.now()
                descriptor.failure_count += 1

    def get_service(self, name: str) -> ServiceDescriptor:
        """Retrieve the service descriptor matching name."""
        if name not in self._registry:
            raise ServiceNotFoundError(f"Service '{name}' not found in registry.")
        return self._registry[name]

    def resolve_instance(self, name: str) -> Any:
        """Retrieve the active runtime object instance using the wired DI Container.

        Enforces strict Separation of Concerns: Registry does NOT instantiate.
        """
        # Ensure it exists in registry catalog
        if name not in self._registry:
            raise ServiceNotFoundError(f"Service '{name}' not tracked in Registry catalog.")

        # Resolve instance from DI container
        return self._container.resolve(name)

    def list_services(self) -> list[ServiceDescriptor]:
        """Return list of all registered descriptors."""
        return list(self._registry.values())

    def list_by_category(self, category: str) -> list[ServiceDescriptor]:
        """Filter registered service descriptors matching category."""
        return [s for s in self._registry.values() if s.category == category]

    def list_by_tag(self, tag: str) -> list[ServiceDescriptor]:
        """Filter registered service descriptors containing tag."""
        return [s for s in self._registry.values() if tag in s.tags]

    def service_exists(self, name: str) -> bool:
        """Check if a service descriptor name exists in catalog."""
        return name in self._registry

    def clear_registry(self) -> None:
        """Reset catalog entries."""
        self._registry.clear()
        logger.info("Cleared Service Registry catalog")

    def validate_registry(self) -> None:
        """Validate registration configurations, dependencies, and type properties."""
        logger.info("Validating Service Registry integrity...")
        for name, descriptor in self._registry.items():
            # Validate dependencies are present in catalog
            for dep in descriptor.dependencies:
                if dep not in self._registry:
                    err_msg = (
                        f"Dependency constraint failed: '{name}' requires unregistered '{dep}'"
                    )
                    logger.error("Registry validation error", service=name, dependency=dep)
                    raise InvalidMetadataError(err_msg)
        logger.info("Service Registry validation: SUCCESS")

    def registry_statistics(self) -> dict[str, Any]:
        """Calculate counts, status profiles, and stats across catalog."""
        stats: dict[str, Any] = {
            "total_services": len(self._registry),
            "categories": {},
            "status": {},
        }
        for s in self._registry.values():
            stats["categories"][s.category] = stats["categories"].get(s.category, 0) + 1
            stats["status"][s.status] = stats["status"].get(s.status, 0) + 1
        return stats

    def export_registry(self) -> str:
        """Export serialized registry descriptors as JSON formats."""
        try:
            export_data = {name: s.to_dict() for name, s in self._registry.items()}
            return json.dumps(export_data, indent=2)
        except Exception as e:
            err_msg = f"Failed to export service registry: {e}"
            logger.error("Registry export error", error=str(e))
            raise RegistryError(err_msg) from e
