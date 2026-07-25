"""Centralized Dependency Injection (DI) Container for AIRA.

Manages lifecycles (Singleton, Transient, Scoped) of core services and plugins
with circular dependency checks and startup validation.
"""

import inspect
from collections.abc import Callable
from datetime import datetime
from typing import Any, Literal

import structlog

logger = structlog.get_logger("aira.di")

LifetimeType = Literal["singleton", "transient", "scoped"]


class DIError(Exception):
    """Base exception for all Dependency Injection failures."""

    pass


class ServiceRegistrationConflictError(DIError):
    """Raised when registering a service key that already exists."""

    pass


class ServiceResolutionError(DIError):
    """Raised when requesting a service that is not registered."""

    pass


class CircularDependencyError(DIError):
    """Raised when a circular reference dependency is detected during resolution."""

    pass


class ServiceMetadata:
    """Stores registration data, lifetimes, and operational descriptions of services."""

    def __init__(
        self,
        name: str,
        lifetime: LifetimeType,
        module_path: str,
        description: str,
        version: str = "0.1.0",
    ) -> None:
        self.name = name
        self.lifetime = lifetime
        self.module_path = module_path
        self.description = description
        self.version = version
        self.registered_at: datetime = datetime.now()
        self.health_status: str = "healthy"


class DependencyContainer:
    """Lightweight, pure-Python Dependency Injection container."""

    def __init__(self) -> None:
        self._services: dict[str, Callable[[], Any]] = {}
        self._singletons: dict[str, Any] = {}
        self._metadata: dict[str, ServiceMetadata] = {}
        # Tracks resolving stack to detect circular loops
        self._resolution_stack: list[str] = []

    def register_singleton(
        self,
        name: str,
        instance_or_factory: Any,
        description: str = "",
        version: str = "0.1.0",
        allow_overwrite: bool = False,
    ) -> None:
        """Register a service with a single, persistent lifetime."""
        if name in self._services and not allow_overwrite:
            err_msg = f"Service '{name}' is already registered."
            logger.error("Registration conflict", service=name)
            raise ServiceRegistrationConflictError(err_msg)

        # Retrieve module info from callers
        frame = inspect.stack()[1]
        module_path = frame.filename

        self._metadata[name] = ServiceMetadata(
            name=name,
            lifetime="singleton",
            module_path=module_path,
            description=description,
            version=version,
        )

        if name in self._singletons:
            self._singletons.pop(name, None)

        if callable(instance_or_factory):
            self._services[name] = instance_or_factory
        else:
            # Wrap pre-existing instance in a simple factory
            self._services[name] = lambda: instance_or_factory
            self._singletons[name] = instance_or_factory

        logger.debug("Registered singleton service", service=name)

    def register_transient(
        self, name: str, factory: Callable[..., Any], description: str = "", version: str = "0.1.0"
    ) -> None:
        """Register a transient service generated fresh on each resolution request."""
        if name in self._services:
            err_msg = f"Service '{name}' is already registered."
            logger.error("Registration conflict", service=name)
            raise ServiceRegistrationConflictError(err_msg)

        if not callable(factory):
            raise DIError(f"Transient registrations require a callable factory for '{name}'.")

        frame = inspect.stack()[1]
        module_path = frame.filename

        self._metadata[name] = ServiceMetadata(
            name=name,
            lifetime="transient",
            module_path=module_path,
            description=description,
            version=version,
        )
        self._services[name] = factory
        logger.debug("Registered transient service", service=name)

    def register_factory(
        self, name: str, factory: Callable[..., Any], description: str = "", version: str = "0.1.0"
    ) -> None:
        """Register a factory delegate (alias for register_transient)."""
        self.register_transient(name, factory, description, version)

    def resolve(self, name: str) -> Any:
        """Locate and return the requested service instance, checking for circular loops."""
        if name not in self._services:
            err_msg = f"Requested service '{name}' is not registered."
            logger.error("Resolution failure", service=name)
            raise ServiceResolutionError(err_msg)

        # 1. Circular dependency detection check
        if name in self._resolution_stack:
            cycle = " -> ".join([*self._resolution_stack, name])
            err_msg = f"Circular dependency loop detected: {cycle}"
            logger.error("Circular dependency", cycle=cycle)
            raise CircularDependencyError(err_msg)

        # 2. Check if singleton is already resolved
        if name in self._singletons:
            return self._singletons[name]

        # 3. Add to resolution stack
        self._resolution_stack.append(name)

        try:
            factory = self._services[name]
            instance = factory()

            # Cache singleton instances
            meta = self._metadata[name]
            if meta.lifetime == "singleton":
                self._singletons[name] = instance

            return instance
        except DIError:
            raise
        except Exception as e:
            err_msg = f"Failed to instantiate service '{name}': {e}"
            logger.exception("Instantiation failure", service=name)
            raise DIError(err_msg) from e
        finally:
            self._resolution_stack.pop()

    def is_registered(self, name: str) -> bool:
        """Check if a service matches registered keys."""
        return name in self._services

    def remove(self, name: str) -> None:
        """Remove a service registration from the container mappings."""
        self._services.pop(name, None)
        self._singletons.pop(name, None)
        self._metadata.pop(name, None)
        logger.debug("Removed service registration", service=name)

    def clear(self) -> None:
        """Reset all registrations and cached singletons."""
        self._services.clear()
        self._singletons.clear()
        self._metadata.clear()
        logger.debug("Cleared container registrations")

    def list_services(self) -> list[dict[str, Any]]:
        """Return descriptions of all active container service registrations."""
        services_list = []
        for _, meta in self._metadata.items():
            services_list.append(
                {
                    "name": meta.name,
                    "lifetime": meta.lifetime,
                    "description": meta.description,
                    "version": meta.version,
                    "registered_at": meta.registered_at.isoformat(),
                    "health": meta.health_status,
                }
            )
        return services_list

    def validate_container(self) -> None:
        """Perform a dry-run resolution of all registered services to verify dependencies."""
        logger.info("Starting Dependency Container validations...")
        for name in list(self._services.keys()):
            self.resolve(name)
        logger.info("Container validation status: SUCCESS")
