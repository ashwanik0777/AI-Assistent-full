"""Enterprise IDE Intelligence Layer with an initial VS Code Adapter subsystem for AIRA.

Provides editor abstraction layers, session states, diagnostic collections, and navigation lookups.
"""

import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.ide_intelligence")


class IDEIntelligenceError(Exception):
    """Raised when IDE intelligence constraints or editor adapter operations fail."""

    pass


@dataclass
class IDESession:
    """Structured session state properties representation for connected development editors."""

    session_id: str
    workspace_id: str
    active_project: str
    opened_files: list[str] = field(default_factory=list)
    active_file: str = ""
    cursor_position: dict[str, int] = field(default_factory=lambda: {"line": 1, "character": 1})
    selected_text_metadata: dict[str, Any] = field(default_factory=dict)
    problems_count: int = 0
    diagnostics_summary: list[dict[str, Any]] = field(default_factory=list)
    open_terminals_metadata: list[dict[str, Any]] = field(default_factory=list)
    git_metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class BaseIDEAdapter(ABC):
    """Generic interface adapter contract matching editor client integrations."""

    @abstractmethod
    def connect(self) -> bool:
        """Initialize connection mapping structure."""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Close connection socket state."""
        pass

    @abstractmethod
    def get_session_metadata(self) -> IDESession:
        """Acquire latest editor state metrics snapshot."""
        pass

    @abstractmethod
    def open_file(self, file_path: str) -> bool:
        """Signal IDE client to open or focus a target file path."""
        pass

    @abstractmethod
    def navigate_to(self, file_path: str, line: int, char: int) -> bool:
        """Command client to scroll / place editor cursor position coordinates."""
        pass

    @abstractmethod
    def search_workspace(self, query: str) -> list[dict[str, Any]]:
        """Query editor indexing systems for files matches."""
        pass

    @abstractmethod
    def get_diagnostics(self) -> list[dict[str, Any]]:
        """Return list of project problems (syntax errors, lint issues, etc.)."""
        pass


class VSCodeAdapter(BaseIDEAdapter):
    """Concrete VS Code editor adapter communicating simulated capability structures."""

    def __init__(self, workspace_id: str, root_path: str) -> None:
        self.workspace_id = workspace_id
        self.root_path = root_path
        self._connected = False
        self._open_files = ["main.py", "app.py"]
        self._active_file = "main.py"
        self._cursor = {"line": 12, "character": 5}

    def connect(self) -> bool:
        self._connected = True
        return True

    def disconnect(self) -> None:
        self._connected = False

    def get_session_metadata(self) -> IDESession:
        if not self._connected:
            raise IDEIntelligenceError("VS Code Adapter is not connected.")

        diagnostics = self.get_diagnostics()
        return IDESession(
            session_id=f"session_vscode_{self.workspace_id}",
            workspace_id=self.workspace_id,
            active_project=os.path.basename(self.root_path),
            opened_files=self._open_files,
            active_file=self._active_file,
            cursor_position=self._cursor,
            selected_text_metadata={"length": 0, "content": ""},
            problems_count=len(diagnostics),
            diagnostics_summary=diagnostics,
            open_terminals_metadata=[{"terminal_id": 1, "shell": "zsh"}],
            git_metadata={"branch": "main", "dirty": False},
        )

    def open_file(self, file_path: str) -> bool:
        if file_path not in self._open_files:
            self._open_files.append(file_path)
        self._active_file = file_path
        return True

    def navigate_to(self, file_path: str, line: int, char: int) -> bool:
        self.open_file(file_path)
        self._cursor = {"line": line, "character": char}
        return True

    def search_workspace(self, query: str) -> list[dict[str, Any]]:
        # Simulated search result matching dummy configuration layout
        return [{"file": "main.py", "line": 5, "match": f"matches query: {query}"}]

    def get_diagnostics(self) -> list[dict[str, Any]]:
        # Simulated errors & warnings diagnostics summary payload
        return [
            {
                "file": "main.py",
                "line": 4,
                "severity": "Error",
                "message": "SyntaxError: invalid syntax",
                "source": "pyflakes",
            },
            {
                "file": "app.py",
                "line": 15,
                "severity": "Warning",
                "message": "Typechecking: missing type annotations",
                "source": "mypy",
            },
        ]


class WorkspaceAwarenessManager:
    """Maintains active directory parameters, active file pointers, and framework mappings."""

    def __init__(self, root_path: str) -> None:
        self.root_path = root_path
        self.active_file = "None"
        self.active_language = "None"
        self.active_framework = "None"

    def update_awareness(self, active_file: str, project_type: str) -> None:
        """Resolve files extensions parameters."""
        self.active_file = active_file
        ext = os.path.splitext(active_file)[-1].lower()
        if ext in [".py"]:
            self.active_language = "Python"
        elif ext in [".js", ".jsx", ".ts", ".tsx"]:
            self.active_language = "JavaScript/TypeScript"
        else:
            self.active_language = "Unknown"

        self.active_framework = project_type


class DiagnosticManager:
    """Organizes parsed syntax warnings and lint targets across session profiles."""

    def collect_diagnostics(self, diagnostics: list[dict[str, Any]]) -> dict[str, Any]:
        """Aggregate diagnostics counters by severity category."""
        errors_count = 0
        warnings_count = 0

        for diag in diagnostics:
            if diag.get("severity") == "Error":
                errors_count += 1
            else:
                warnings_count += 1

        return {"errors": errors_count, "warnings": warnings_count, "total": len(diagnostics)}


class CodeNavigationManager:
    """Manages active editor navigation, definitions jumps, and tracking records."""

    def resolve_definition(self, file: str, symbol: str) -> dict[str, Any]:
        """Retrieve simulated symbol definitions locations."""
        return {"symbol": symbol, "target_file": file, "target_line": 15, "target_char": 4}


class IDEIntelligenceManager:
    """Central manager orchestrating active IDE adapter instances and event cycles."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.active_adapter: BaseIDEAdapter | None = None
        self.awareness: WorkspaceAwarenessManager | None = None
        self.diagnostics = DiagnosticManager()
        self.navigation = CodeNavigationManager()

    def connect_adapter(self, adapter: BaseIDEAdapter) -> None:
        """Register client adapter connection and dispatch bus event."""
        adapter.connect()
        self.active_adapter = adapter

        # Seed awareness
        session = adapter.get_session_metadata()
        self.awareness = WorkspaceAwarenessManager(getattr(adapter, "root_path", ""))
        self.awareness.update_awareness(session.active_file, "Simulated Framework")

        self.event_bus.publish_sync(
            Event(
                name="ide.connected",
                category="IDE",
                source="IDEIntelligenceManager",
                payload={"session_id": session.session_id},
            )
        )

    def focus_file(self, file_path: str) -> None:
        """Signal client editor tabs focus update."""
        if not self.active_adapter:
            raise IDEIntelligenceError("No active IDE adapter registered.")

        self.active_adapter.open_file(file_path)
        if self.awareness:
            self.awareness.update_awareness(file_path, self.awareness.active_framework)

        self.event_bus.publish_sync(
            Event(
                name="file_focus.changed",
                category="IDE",
                source="IDEIntelligenceManager",
                payload={"active_file": file_path},
            )
        )

    def fetch_diagnostics(self) -> dict[str, Any]:
        """Return diagnostic health counts from client adapter."""
        if not self.active_adapter:
            raise IDEIntelligenceError("No active IDE adapter registered.")

        raw_diags = self.active_adapter.get_diagnostics()
        summary = self.diagnostics.collect_diagnostics(raw_diags)

        self.event_bus.publish_sync(
            Event(
                name="diagnostics.updated",
                category="IDE",
                source="IDEIntelligenceManager",
                payload=summary,
            )
        )
        return summary

    def disconnect_adapter(self) -> None:
        """Close connection mappings cleanly."""
        if self.active_adapter:
            self.active_adapter.disconnect()
            self.active_adapter = None

        self.event_bus.publish_sync(
            Event(
                name="ide.disconnected", category="IDE", source="IDEIntelligenceManager", payload={}
            )
        )
