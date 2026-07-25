"""Enterprise Desktop Application Intelligence Platform subsystem for AIRA.

Defines native OS providers, window managers, application model builders, and graphs.
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.perception_engine import ObservationBuilder, PerceptionEngine
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.desktop_application_intelligence")


class DesktopIntelligenceError(Exception):
    """Raised when accessibility queries or window operations fail."""

    pass


@dataclass
class DesktopWindow:
    """Native OS Window representation containing state, visibility, and dialog flags."""

    window_id: str
    title: str
    x: int
    y: int
    width: int
    height: int
    is_focused: bool = False
    is_floating: bool = False
    is_fullscreen: bool = False
    parent_window_id: str | None = None


@dataclass
class ApplicationModel:
    """Semantic model mapping application process specs and layout views."""

    app_id: str
    name: str
    process_id: int
    windows: list[DesktopWindow] = field(default_factory=list)
    active_view: str = "Editor"
    menus: list[str] = field(default_factory=list)
    toolbars: list[str] = field(default_factory=list)
    state_metadata: dict[str, Any] = field(default_factory=dict)
    version: str = "1.0.0"


@dataclass
class ApplicationSession:
    """Active session parameters mapping windows histories and loaded dialog nodes."""

    session_id: str
    app_id: str
    workspace_id: str
    window_history: list[str] = field(default_factory=list)
    active_view: str = "Editor"
    dialog_history: list[str] = field(default_factory=list)


@dataclass
class CrossAppContext:
    """Context state tracking clipboard metadata and shared workspace files."""

    active_applications: list[str] = field(default_factory=list)
    clipboard_metadata: dict[str, Any] = field(default_factory=dict)
    open_documents: list[dict[str, Any]] = field(default_factory=list)
    shared_files: list[str] = field(default_factory=list)


class BaseAccessibilityProvider(ABC):
    """Abstract interface defining platform-specific accessibility bindings."""

    @abstractmethod
    def query_accessibility_tree(self, app_name: str) -> dict[str, Any]:
        """Fetch platform accessibility hierarchy mappings."""
        pass


class MacOSAccessibilityProvider(BaseAccessibilityProvider):
    """macOS Accessibility adapter wrapper simulation."""

    def query_accessibility_tree(self, app_name: str) -> dict[str, Any]:
        return {
            "AXRole": "AXApplication",
            "AXTitle": app_name,
            "AXChildren": [{"AXRole": "AXWindow", "AXTitle": f"{app_name} Primary Window"}],
        }


class DesktopWindowManager:
    """Tracks window states, focused applications, and dialog hierarchies."""

    def __init__(self) -> None:
        self.focused_window_id: str | None = None
        self.window_z_order: list[str] = []

    def update_focus(self, window_id: str) -> None:
        """Update window focus pointers."""
        self.focused_window_id = window_id
        if window_id in self.window_z_order:
            self.window_z_order.remove(window_id)
        self.window_z_order.insert(0, window_id)


class ApplicationModelBuilder:
    """Assembles layout analysis models and processes structures."""

    def build_app_model(
        self, app_id: str, name: str, pid: int, windows: list[DesktopWindow]
    ) -> ApplicationModel:
        """Compile a valid ApplicationModel."""
        return ApplicationModel(
            app_id=app_id,
            name=name,
            process_id=pid,
            windows=windows,
        )


class ApplicationGraph:
    """Tracks relationship edges between application modules, views, and dialogs."""

    def __init__(self) -> None:
        self.nodes: dict[str, Any] = {}
        # Map of source_id -> list of target_ids
        self.edges: dict[str, list[str]] = {}

    def build_graph(self, app: ApplicationModel) -> None:
        """Register application properties in graph."""
        self.nodes[app.app_id] = app
        if app.app_id not in self.edges:
            self.edges[app.app_id] = []

        for win in app.windows:
            self.nodes[win.window_id] = win
            if win.window_id not in self.edges:
                self.edges[win.window_id] = []
            self.link(app.app_id, win.window_id)

    def link(self, source_id: str, target_id: str) -> None:
        """Create reference edge between nodes."""
        if source_id in self.edges and target_id not in self.edges[source_id]:
            self.edges[source_id].append(target_id)

    def query_hierarchy(self, node_id: str) -> list[str]:
        """Query children nodes of the target node."""
        return self.edges.get(node_id, [])


class CrossApplicationContextManager:
    """Maintains relationships between active clipboard and workspace files."""

    def __init__(self) -> None:
        self.context = CrossAppContext()

    def update_clipboard(self, content_type: str, char_count: int) -> None:
        """Record clipboard state updates."""
        self.context.clipboard_metadata = {
            "type": content_type,
            "length": char_count,
            "timestamp": time.time(),
        }


class DesktopPerceptionEngine:
    """Coordinator coordinating desktop scans, validating sessions, and publishing observations."""

    def __init__(
        self,
        config: AppConfig,
        registry: ServiceRegistry,
        event_bus: EventBus,
        perception_engine: PerceptionEngine,
    ) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus
        self.perception_engine = perception_engine

        # Default macOS Provider
        self.provider: BaseAccessibilityProvider = MacOSAccessibilityProvider()
        self.window_manager = DesktopWindowManager()
        self.builder = ApplicationModelBuilder()
        self.graph = ApplicationGraph()
        self.context_manager = CrossApplicationContextManager()

    def analyze_desktop_app(
        self, app_name: str, pid: int, session_id: str | None = None
    ) -> ApplicationModel:
        """Execute accessibility query maps, compile models, and publish observations."""
        app_id = f"app_{app_name.lower().replace(' ', '_')}"

        self.event_bus.publish_sync(
            Event(
                name="application.detected",
                category="Perception",
                source="DesktopPerception",
                payload={"app_name": app_name, "pid": pid},
            )
        )

        # 1. Fetch OS accessibility nodes details
        self.provider.query_accessibility_tree(app_name)

        # 2. Build Windows Lists & Application Model
        primary_win = DesktopWindow(
            window_id=f"win_{app_id}_main",
            title=f"{app_name} Workspace Window",
            x=100,
            y=100,
            width=1024,
            height=768,
            is_focused=True,
        )
        self.window_manager.update_focus(primary_win.window_id)
        self.event_bus.publish_sync(
            Event(
                name="window.updated",
                category="Perception",
                source="DesktopPerception",
                payload={"focused_window_id": primary_win.window_id},
            )
        )

        app_model = self.builder.build_app_model(app_id, app_name, pid, [primary_win])
        self.event_bus.publish_sync(
            Event(
                name="application.modeled",
                category="Perception",
                source="DesktopPerception",
                payload={"app_id": app_id, "windows_count": 1},
            )
        )

        # 3. Graph indexing
        self.graph.build_graph(app_model)
        self.event_bus.publish_sync(
            Event(
                name="application_graph.updated",
                category="Perception",
                source="DesktopPerception",
                payload={"nodes_count": len(self.graph.nodes)},
            )
        )

        # 4. Schema verification checks
        if app_model.process_id <= 0:
            raise DesktopIntelligenceError(
                f"Desktop validation failed: Invalid PID {app_model.process_id}."
            )

        # 5. Build Observation Object and publish to Perception Engine
        obs_builder = ObservationBuilder(f"obs_{app_model.app_id}", "Desktop", "ApplicationModel")
        obs_builder.set_confidence(1.0)
        obs_builder.set_content(
            {
                "app_id": app_model.app_id,
                "name": app_model.name,
                "pid": app_model.process_id,
                "focused_window_id": primary_win.window_id,
            }
        )
        obs_builder.set_metadata("session_app_id", app_id)

        obs = obs_builder.build()
        self.perception_engine.process_observation(obs, session_id=session_id)

        self.event_bus.publish_sync(
            Event(
                name="desktop_observation.published",
                category="Perception",
                source="DesktopPerception",
                payload={"observation_id": obs.observation_id},
            )
        )

        return app_model
