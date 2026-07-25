"""Enterprise Lifecycle Orchestrator for AIRA.

Orchestrates runtime states, calculates topological initialization orders,
runs lifecycle hooks, and executes graceful shutdowns.
"""

from collections.abc import Callable
from typing import Any, ClassVar, Literal

import structlog

from aira.infrastructure.di_container import DependencyContainer
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.lifecycle")

RuntimeStateType = Literal[
    "CREATED",
    "INITIALIZING",
    "STARTING",
    "READY",
    "BUSY",
    "IDLE",
    "PAUSED",
    "RESTARTING",
    "STOPPING",
    "STOPPED",
    "FAILED",
    "RECOVERING",
]


class LifecycleError(Exception):
    """Base exception for all lifecycle orchestrator failures."""

    pass


class InvalidStateTransitionError(LifecycleError):
    """Raised when violating the valid runtime state machine paths."""

    pass


class LifecycleDependencyError(LifecycleError):
    """Raised when topological sort fails due to cycles or missing keys."""

    pass


class LifecycleOrchestrator:
    """Orchestrator coordinating start sequences, dependency sorting, and shutdowns."""

    # Valid transitions dictionary
    VALID_TRANSITIONS: ClassVar[dict[RuntimeStateType, set[RuntimeStateType]]] = {
        "CREATED": {"INITIALIZING", "FAILED"},
        "INITIALIZING": {"STARTING", "FAILED"},
        "STARTING": {"READY", "FAILED"},
        "READY": {"BUSY", "IDLE", "PAUSED", "RESTARTING", "STOPPING", "FAILED"},
        "BUSY": {"READY", "IDLE", "STOPPING", "FAILED"},
        "IDLE": {"BUSY", "READY", "STOPPING", "FAILED"},
        "PAUSED": {"READY", "STOPPING", "FAILED"},
        "RESTARTING": {"STOPPING", "INITIALIZING", "FAILED"},
        "STOPPING": {"STOPPED", "FAILED"},
        "STOPPED": {"INITIALIZING", "CREATED"},
        "FAILED": {"RECOVERING", "STOPPING", "STOPPED"},
        "RECOVERING": {"INITIALIZING", "READY", "FAILED"},
    }

    def __init__(
        self, di_container: DependencyContainer, registry: ServiceRegistry, event_bus: EventBus
    ) -> None:
        self._container = di_container
        self._registry = registry
        self._event_bus = event_bus

        self.state: RuntimeStateType = "CREATED"

        # Hooks dictionary: hook_name -> list of callable execution actions
        self._hooks: dict[str, list[Callable[[], Any]]] = {
            "before_startup": [],
            "after_startup": [],
            "before_shutdown": [],
            "after_shutdown": [],
            "before_restart": [],
            "after_restart": [],
            "service_starting": [],
            "service_started": [],
            "service_failed": [],
            "service_recovered": [],
            "runtime_ready": [],
        }

    def transition_to(self, target_state: RuntimeStateType) -> None:
        """Enforce transition restrictions and log state machines updates."""
        allowed = self.VALID_TRANSITIONS.get(self.state, set())
        if target_state not in allowed:
            err_msg = f"Transition from '{self.state}' to '{target_state}' is not allowed."
            logger.error("State transition conflict", current=self.state, target=target_state)
            raise InvalidStateTransitionError(err_msg)

        old_state = self.state
        self.state = target_state
        logger.info("Runtime state transitioned", old_state=old_state, new_state=target_state)

    def register_hook(self, name: str, callback: Callable[[], Any]) -> None:
        """Register a callback handler for a specific lifecycle event."""
        if name not in self._hooks:
            raise LifecycleError(f"Lifecycle hook '{name}' is unrecognized.")
        self._hooks[name].append(callback)
        logger.debug("Registered lifecycle hook callback", hook=name)

    def _trigger_hook(self, name: str) -> None:
        """Sequentially execute all registered callbacks for a specific lifecycle event."""
        for callback in self._hooks.get(name, []):
            try:
                callback()
            except Exception as e:
                logger.error("Lifecycle hook execution failed", hook=name, error=str(e))

    def calculate_startup_order(self) -> list[str]:
        """Run topological sort on services to calculate startup sequence."""
        services = self._registry.list_services()
        graph = {s.name: s.dependencies for s in services}

        visited: dict[str, int] = {}
        order: list[str] = []

        def visit(name: str) -> None:
            state = visited.get(name, 0)
            if state == 1:
                raise LifecycleDependencyError(f"Circular dependency detected involving '{name}'")
            if state == 2:
                return

            visited[name] = 1
            for dep in graph.get(name, []):
                if dep not in graph:
                    raise LifecycleDependencyError(
                        f"Service '{name}' depends on unregistered dependency '{dep}'"
                    )
                visit(dep)
            visited[name] = 2
            order.append(name)

        for name in graph:
            if name not in visited:
                visit(name)

        return order

    def startup(self) -> None:
        """Run startup cycle, dynamically sorting and initializing dependencies."""
        self.transition_to("INITIALIZING")
        self._trigger_hook("before_startup")

        self.transition_to("STARTING")

        try:
            startup_order = self.calculate_startup_order()
            logger.info("Calculated startup order sequence", order=startup_order)

            for service_name in startup_order:
                self._trigger_hook("service_starting")
                self._registry.update_service(service_name, "INITIALIZING")

                # Resolve instance (triggers DI container resolution and creation)
                try:
                    instance = self._registry.resolve_instance(service_name)
                    # If instance has initialize/start callbacks, execute them
                    if instance is not None:
                        if hasattr(instance, "initialize") and callable(instance.initialize):
                            instance.initialize()
                        elif hasattr(instance, "start") and callable(instance.start):
                            instance.start()

                    self._registry.update_service(service_name, "READY")
                    self._trigger_hook("service_started")
                except Exception as service_err:
                    self._registry.update_service(service_name, "FAILED")
                    self._trigger_hook("service_failed")
                    raise LifecycleError(
                        f"Failed to initialize service '{service_name}': {service_err}"
                    ) from service_err

            self.transition_to("READY")
            self._trigger_hook("after_startup")
            self._trigger_hook("runtime_ready")

            # Dispatch system startup event
            startup_event = Event(
                name="system.startup",
                category="Lifecycle",
                source="LifecycleOrchestrator",
                payload={"status": "READY"},
            )
            self._event_bus.publish_sync(startup_event)

        except Exception as e:
            self.transition_to("FAILED")
            logger.error("Startup orchestrator execution failed", error=str(e))
            raise

    def shutdown(self) -> None:
        """Execute dynamic graceful shutdowns in reverse order, releasing resources."""
        self.transition_to("STOPPING")
        self._trigger_hook("before_shutdown")

        # Dispatch system shutdown event
        shutdown_event = Event(
            name="system.shutdown",
            category="Lifecycle",
            source="LifecycleOrchestrator",
            payload={"status": "STOPPING"},
        )
        self._event_bus.publish_sync(shutdown_event)

        try:
            # Shutdown in reverse startup order
            startup_order = self.calculate_startup_order()
            shutdown_order = list(reversed(startup_order))
            logger.info("Shutdown sequence path", order=shutdown_order)

            for service_name in shutdown_order:
                try:
                    # Retrieve the service if resolved
                    # Note: We resolve without throwing to allow un-initialized
                    # elements to bypass close cleanups
                    if self._container.is_registered(service_name):
                        instance = self._container.resolve(service_name)
                        if instance is not None:
                            if hasattr(instance, "shutdown") and callable(instance.shutdown):
                                instance.shutdown()
                            elif hasattr(instance, "close") and callable(instance.close):
                                instance.close()
                    self._registry.update_service(service_name, "STOPPED")
                except Exception as shutdown_err:
                    logger.error(
                        "Graceful shutdown of service failed",
                        service=service_name,
                        error=str(shutdown_err),
                    )

            self.transition_to("STOPPED")
            self._trigger_hook("after_shutdown")

        except Exception as e:
            self.transition_to("FAILED")
            logger.error("Shutdown orchestrator execution failed", error=str(e))
            raise

    def restart(self) -> None:
        """Shutdown the active orchestrator sequence and boot a fresh instance cycle."""
        self._trigger_hook("before_restart")
        self.shutdown()

        # Reset orchestrator state path
        self.state = "CREATED"
        self.startup()
        self._trigger_hook("after_restart")
