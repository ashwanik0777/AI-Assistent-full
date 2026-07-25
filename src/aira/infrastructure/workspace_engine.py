"""Developer Workspace Engine subsystem for AIRA.

Manages workspaces metadata, project stack detection, and workspace state lifecycles.
"""

import os
import threading
from dataclasses import dataclass, field
from typing import Any, ClassVar

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.workspace_engine")


class WorkspaceError(Exception):
    """Raised when workspace registration, file detections, or lifecycle transitions fail."""

    pass


@dataclass
class WorkspaceObject:
    """Dataclass holding complete workspace configurations and states."""

    workspace_id: str
    name: str
    workspace_root: str
    repository_info: str = ""
    project_type: str = "Unknown"
    technology_stack: list[str] = field(default_factory=list)
    language_stack: list[str] = field(default_factory=list)
    build_system: str = "Unknown"
    package_manager: str = "Unknown"
    environment_variables: dict[str, str] = field(default_factory=dict)
    open_sessions: int = 0
    lifecycle_state: str = "Created"
    metadata: dict[str, Any] = field(default_factory=dict)


class WorkspaceValidator:
    """Verifies repository directory existence and detects files formats."""

    def validate_workspace(self, ws: WorkspaceObject) -> None:
        """Verify root directory existence constraints."""
        if not os.path.isdir(ws.workspace_root):
            msg = f"Workspace root path '{ws.workspace_root}' does not exist or is not a directory."
            raise WorkspaceError(msg)

    def detect_stack(self, workspace_root: str) -> dict[str, Any]:
        """Auto-detect workspace language stack and package manager markers."""
        detected = {
            "project_type": "Unknown",
            "technology_stack": [],
            "language_stack": [],
            "package_manager": "Unknown",
            "build_system": "Unknown",
        }

        # 1. Node.js detection checks
        if os.path.exists(os.path.join(workspace_root, "package.json")):
            detected["project_type"] = "Node.js Project"
            detected["language_stack"] = ["JavaScript/TypeScript"]
            detected["technology_stack"] = ["Node.js"]
            if os.path.exists(os.path.join(workspace_root, "package-lock.json")):
                detected["package_manager"] = "npm"
            elif os.path.exists(os.path.join(workspace_root, "yarn.lock")):
                detected["package_manager"] = "yarn"

        # 2. Python detection checks
        elif os.path.exists(os.path.join(workspace_root, "pyproject.toml")) or os.path.exists(
            os.path.join(workspace_root, "requirements.txt")
        ):
            detected["project_type"] = "Python Project"
            detected["language_stack"] = ["Python"]
            detected["technology_stack"] = ["Python Runtime"]
            if os.path.exists(os.path.join(workspace_root, "poetry.lock")):
                detected["package_manager"] = "Poetry"
            else:
                detected["package_manager"] = "pip"

        # 3. Rust detection checks
        elif os.path.exists(os.path.join(workspace_root, "Cargo.toml")):
            detected["project_type"] = "Rust Project"
            detected["language_stack"] = ["Rust"]
            detected["package_manager"] = "cargo"
            detected["build_system"] = "cargo build"

        # 4. Java detection checks
        elif os.path.exists(os.path.join(workspace_root, "pom.xml")):
            detected["project_type"] = "Java Project"
            detected["language_stack"] = ["Java"]
            detected["build_system"] = "Maven"

        return detected


class WorkspaceRegistry:
    """Registry maintaining references to all workspaces."""

    def __init__(self) -> None:
        self._workspaces: dict[str, WorkspaceObject] = {}
        self.lock = threading.Lock()

    def register(self, ws: WorkspaceObject) -> None:
        """Register a workspace object."""
        with self.lock:
            if ws.workspace_id in self._workspaces:
                raise WorkspaceError(f"Workspace '{ws.workspace_id}' is already registered.")
            self._workspaces[ws.workspace_id] = ws

    def get(self, workspace_id: str) -> WorkspaceObject | None:
        """Get workspace reference by ID."""
        with self.lock:
            return self._workspaces.get(workspace_id)

    def list_all(self) -> list[WorkspaceObject]:
        """List all registered workspaces."""
        with self.lock:
            return list(self._workspaces.values())


class DeveloperWorkspaceEngine:
    """Unified manager handling workspace CRUDs and lifecycle state transitions."""

    VALID_TRANSITIONS: ClassVar[dict[str, set[str]]] = {
        "Created": {"Opened", "Deleted"},
        "Opened": {"Active", "Closed", "Archived"},
        "Active": {"Idle", "Closed"},
        "Idle": {"Active", "Closed"},
        "Closed": {"Opened", "Archived", "Deleted"},
        "Archived": {"Opened", "Deleted"},
        "Deleted": set(),
    }

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.ws_registry = WorkspaceRegistry()
        self.validator = WorkspaceValidator()
        self.lock = threading.Lock()

    def create_workspace(self, ws: WorkspaceObject) -> None:
        """Validate and publish a new workspace registry entry."""
        with self.lock:
            self.validator.validate_workspace(ws)
            self.ws_registry.register(ws)
            self.event_bus.publish_sync(
                Event(
                    name="workspace.created",
                    category="Workspace",
                    source="WorkspaceEngine",
                    payload={"workspace_id": ws.workspace_id},
                )
            )

    def transition_state(self, workspace_id: str, new_state: str) -> None:
        """Perform workspace state lifecycle transition checks."""
        with self.lock:
            ws = self.ws_registry.get(workspace_id)
            if not ws:
                raise WorkspaceError(f"Workspace '{workspace_id}' not found.")

            current = ws.lifecycle_state
            if new_state not in self.VALID_TRANSITIONS.get(current, set()):
                msg = f"Invalid workspace lifecycle transition: '{current}' to '{new_state}'"
                raise WorkspaceError(msg)

            ws.lifecycle_state = new_state

            if new_state == "Opened":
                self.event_bus.publish_sync(
                    Event(
                        name="workspace.opened",
                        category="Workspace",
                        source="WorkspaceEngine",
                        payload={"workspace_id": workspace_id},
                    )
                )
            elif new_state == "Closed":
                self.event_bus.publish_sync(
                    Event(
                        name="workspace.closed",
                        category="Workspace",
                        source="WorkspaceEngine",
                        payload={"workspace_id": workspace_id},
                    )
                )
