"""Enterprise Workflow Context, Variables & State Engine for AIRA.

Provides variable stores (System, Workflow, Temporary scopes), string value resolvers,
running execution states tracking, and registered artifact metadata catalogs.
"""

import re
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.workflow_context")


class WorkflowContextError(Exception):
    """Raised when variable validations, state transitions, or resolver lookups fail."""

    pass


class VariableStore:
    """Manages variables across System, Workflow, and Temporary scopes."""

    def __init__(self) -> None:
        self.scopes: dict[str, dict[str, Any]] = {"SYSTEM": {}, "WORKFLOW": {}, "TEMPORARY": {}}
        # Reserved names list
        self.reserved_names = {"state", "current_step", "cursor", "retry_count", "token"}

    def set_variable(self, name: str, value: Any, scope: str = "WORKFLOW") -> bool:
        """Create or update a variable value in the specified scope."""
        scope_upper = scope.upper()
        if scope_upper not in self.scopes:
            raise WorkflowContextError(f"Unsupported variable scope: '{scope}'")

        if name in self.reserved_names:
            raise WorkflowContextError(
                f"Variable name '{name}' is reserved and cannot be modified."
            )

        if not name or not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", name):
            raise WorkflowContextError(f"Invalid variable name format: '{name}'")

        is_new = name not in self.scopes[scope_upper]
        self.scopes[scope_upper][name] = value
        return is_new

    def get_variable(self, name: str) -> Any | None:
        """Lookup variable value across scopes (Temporary -> Workflow -> System)."""
        for scope in ["TEMPORARY", "WORKFLOW", "SYSTEM"]:
            if name in self.scopes[scope]:
                return self.scopes[scope][name]
        return None

    def delete_variable(self, name: str) -> None:
        """Remove variable key from all active scopes."""
        deleted = False
        for scope in ["TEMPORARY", "WORKFLOW", "SYSTEM"]:
            if name in self.scopes[scope]:
                del self.scopes[scope][name]
                deleted = True
        if not deleted:
            raise WorkflowContextError(f"Variable '{name}' not found for deletion.")

    def clone_variables(self) -> dict[str, dict[str, Any]]:
        """Return deep copy snapshot of current variables."""
        return {
            "SYSTEM": dict(self.scopes["SYSTEM"]),
            "WORKFLOW": dict(self.scopes["WORKFLOW"]),
            "TEMPORARY": dict(self.scopes["TEMPORARY"]),
        }


class VariableResolver:
    """Resolves string templates referencing stored context variables."""

    def __init__(self) -> None:
        self.pattern = re.compile(r"\$\{([a-zA-Z_][a-zA-Z0-9_]*)\}")

    def resolve_string(self, text: str, store: VariableStore) -> str:
        """Replace patterns like ${variable_name} with resolved variable values."""

        def replacer(match: re.Match) -> str:
            var_name = match.group(1)
            val = store.get_variable(var_name)
            if val is None:
                raise WorkflowContextError(
                    f"Variable '{var_name}' unresolved in resolution template."
                )
            return str(val)

        return self.pattern.sub(replacer, text)


class StateStore:
    """Manages active session execution state indicators."""

    def __init__(self) -> None:
        self.workflow_state: str = "DRAFT"
        self.current_step_id: str = ""
        self.completed_steps: list[str] = []
        self.failed_steps: list[str] = []
        self.retry_count: int = 0
        self.metadata: dict[str, Any] = {}

    def update_state(
        self,
        workflow_state: str,
        current_step_id: str,
        completed_steps: list[str],
        failed_steps: list[str],
        retry_count: int,
        metadata: dict[str, Any],
    ) -> None:
        """Overwrite running state indicators."""
        self.workflow_state = workflow_state
        self.current_step_id = current_step_id
        self.completed_steps = list(completed_steps)
        self.failed_steps = list(failed_steps)
        self.retry_count = retry_count
        self.metadata = dict(metadata)


class ArtifactStore:
    """Registers file references and logs path maps without reading physical contents."""

    def __init__(self) -> None:
        self.artifacts: dict[str, dict[str, Any]] = {}

    def register_artifact(self, name: str, path: str, metadata: dict[str, Any]) -> bool:
        """Add artifact metadata reference."""
        is_new = name not in self.artifacts
        self.artifacts[name] = {"path": path, "metadata": dict(metadata)}
        return is_new

    def get_artifact(self, name: str) -> dict[str, Any] | None:
        """Fetch registered artifact references."""
        return self.artifacts.get(name)


class WorkflowContextManager:
    """Integrates variable, state, and artifact stores into a unified workflow context."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.variables = VariableStore()
        self.resolver = VariableResolver()
        self.state = StateStore()
        self.artifacts = ArtifactStore()

    def set_var(self, name: str, value: Any, scope: str = "WORKFLOW") -> None:
        """Set context variable and notify event updates."""
        is_new = self.variables.set_variable(name, value, scope)
        event_name = "workflow.variable_created" if is_new else "workflow.variable_updated"

        self.event_bus.publish_sync(
            Event(
                name=event_name,
                category="Context",
                source="WorkflowContextManager",
                payload={"name": name, "scope": scope},
            )
        )

        self.event_bus.publish_sync(
            Event(
                name="workflow.context_updated",
                category="Context",
                source="WorkflowContextManager",
                payload={},
            )
        )

    def get_var(self, name: str) -> Any | None:
        """Fetch context variable value."""
        return self.variables.get_variable(name)

    def delete_var(self, name: str) -> None:
        """Remove variable key."""
        self.variables.delete_variable(name)

        self.event_bus.publish_sync(
            Event(
                name="workflow.variable_deleted",
                category="Context",
                source="WorkflowContextManager",
                payload={"name": name},
            )
        )

    def resolve(self, text: str) -> str:
        """Resolve string templates."""
        return self.resolver.resolve_string(text, self.variables)

    def update_workflow_state(
        self,
        workflow_state: str,
        current_step_id: str,
        completed_steps: list[str],
        failed_steps: list[str],
        retry_count: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Update workflow states indicators."""
        meta = metadata if metadata is not None else {}
        self.state.update_state(
            workflow_state, current_step_id, completed_steps, failed_steps, retry_count, meta
        )

        self.event_bus.publish_sync(
            Event(
                name="workflow.state_changed",
                category="Context",
                source="WorkflowContextManager",
                payload={"state": workflow_state, "step_id": current_step_id},
            )
        )

    def register_artifact_reference(self, name: str, path: str, metadata: dict[str, Any]) -> None:
        """Register artifact reference metadata details."""
        is_new = self.artifacts.register_artifact(name, path, metadata)
        event_name = "workflow.artifact_registered" if is_new else "workflow.artifact_updated"

        self.event_bus.publish_sync(
            Event(
                name=event_name,
                category="Context",
                source="WorkflowContextManager",
                payload={"name": name, "path": path},
            )
        )
