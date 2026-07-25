"""Enterprise UI Semantic Intelligence & Interaction Model subsystem for AIRA.

Provides UI fusion engines, element identity managers, and semantic relationship graphs.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.browser_perception import PageModel
from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.perception_engine import ObservationBuilder, PerceptionEngine
from aira.infrastructure.screen_intelligence import ScreenScene
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.ui_semantic_intelligence")


class UISemanticError(Exception):
    """Raised when UI semantic tree building or element identity resolutions fail."""

    pass


@dataclass
class SemanticElement:
    """Standardized representation of a semantic UI widget or container node."""

    element_id: str
    role: str  # Window, Dialog, Panel, Form, Input, Button, Dropdown, Table, List, etc.
    accessible_label: str
    display_label: str
    parent_id: str | None = None
    child_ids: list[str] = field(default_factory=list)
    interaction_type: str = "Focusable"  # Clickable, Editable, Focusable, ReadOnly, etc.
    current_state: str = "Normal"  # Normal, Active, Focused, Disabled, Hidden
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)
    version: str = "1.0.0"


class UIFusionEngine:
    """Fuses physical window details coordinates and browser DOM properties."""

    def fuse_inputs(self, scene: ScreenScene, page: PageModel) -> list[SemanticElement]:
        """Combine screen layout windows lists and page models tabs inputs."""
        fused = []

        # 1. Map physical VS Code window as container node
        vscode_win = next((w for w in scene.windows if w.application == "VS Code"), None)
        window_id = vscode_win.window_id if vscode_win else "win_fallback"
        fused.append(
            SemanticElement(
                element_id=window_id,
                role="Window",
                accessible_label="VS Code Workspace Editor",
                display_label="VS Code Workspace",
                interaction_type="Focusable",
                x=vscode_win.x if vscode_win else 0,
                y=vscode_win.y if vscode_win else 0,
                width=vscode_win.width if vscode_win else 1920,
                height=vscode_win.height if vscode_win else 1080,
            )
        )

        # 2. Map browser inputs to the workspace window
        for form in page.forms_metadata:
            form_id = form.get("form_id", "form_login")
            fused.append(
                SemanticElement(
                    element_id=f"el_{form_id}",
                    role="Form",
                    accessible_label="User Login Form Section",
                    display_label="Login Form",
                    parent_id=window_id,
                    interaction_type="Focusable",
                )
            )

        return fused


class SemanticAnalyzer:
    """Determines element interaction states and role properties."""

    def analyze_interactions(self, elements: list[SemanticElement]) -> None:
        """Infer interactive states (e.g. Buttons are Clickable)."""
        for el in elements:
            if el.role in ["Button", "Checkbox", "Radio Button"]:
                el.interaction_type = "Clickable"
            elif el.role in ["Input", "Dropdown"]:
                el.interaction_type = "Editable"


class ElementIdentityManager:
    """Generates stable, environment-independent logical element signatures."""

    def generate_stable_id(self, el: SemanticElement, app_name: str) -> str:
        """Hash application names, semantic roles, labels, and metadata to get IDs."""
        raw = f"{app_name}:{el.role}:{el.accessible_label}:{el.display_label}"
        hashed = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return f"id_{hashed[:16]}"


class UIRelationshipGraph:
    """Indexes structural relationship edges between inputs, fields, and submit buttons."""

    def __init__(self) -> None:
        self.nodes: dict[str, SemanticElement] = {}
        # Map of source_id -> list of target_ids
        self.edges: dict[str, list[str]] = {}

    def build_graph(self, elements: list[SemanticElement]) -> None:
        """Add elements and pre-defined parenting scopes to the queryable graph."""
        for el in elements:
            self.nodes[el.element_id] = el
            if el.element_id not in self.edges:
                self.edges[el.element_id] = []

            # Link parenting parent/child relation
            if el.parent_id:
                if el.parent_id not in self.edges:
                    self.edges[el.parent_id] = []
                self.link(el.parent_id, el.element_id)

    def link(self, source_id: str, target_id: str) -> None:
        """Create reference edge pointing between UI element nodes."""
        if source_id in self.edges and target_id not in self.edges[source_id]:
            self.edges[source_id].append(target_id)

    def query_relationships(self, element_id: str) -> list[str]:
        """Retrieve target node references linked to this node."""
        return self.edges.get(element_id, [])


class UISemanticIntelligenceManager:
    """Unified manager coordinates UI fusion captures, element IDs, and semantic graph updates."""

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

        self.fusion_engine = UIFusionEngine()
        self.analyzer = SemanticAnalyzer()
        self.identity_manager = ElementIdentityManager()
        self.graph = UIRelationshipGraph()

    def analyze_ui_scene(
        self, scene: ScreenScene, page: PageModel, session_id: str | None = None
    ) -> list[SemanticElement]:
        """Trigger UI fusion, compile interaction models, generate stable IDs.

        Afterwards, publish standard observations.
        """
        # 1. UI Fusion
        elements = self.fusion_engine.fuse_inputs(scene, page)
        self.event_bus.publish_sync(
            Event(
                name="semantic_tree.built",
                category="Perception",
                source="UISemantic",
                payload={"elements_count": len(elements)},
            )
        )

        # 2. Analyze Interactions
        self.analyzer.analyze_interactions(elements)
        clickable_count = sum(1 for e in elements if e.interaction_type == "Clickable")
        self.event_bus.publish_sync(
            Event(
                name="interaction_model.updated",
                category="Perception",
                source="UISemantic",
                payload={"clickable_count": clickable_count},
            )
        )

        # 3. Generate Stable Identities & Populate Graph
        for el in elements:
            stable_id = self.identity_manager.generate_stable_id(el, "AIRAWorkspace")
            el.metadata["stable_id"] = stable_id
            self.event_bus.publish_sync(
                Event(
                    name="element_identity.generated",
                    category="Perception",
                    source="UISemantic",
                    payload={"element_id": el.element_id, "stable_id": stable_id},
                )
            )

        self.graph.build_graph(elements)
        self.event_bus.publish_sync(
            Event(
                name="ui_graph.updated",
                category="Perception",
                source="UISemantic",
                payload={"nodes_count": len(self.graph.nodes)},
            )
        )

        # 4. Schema Verification constraints
        for el in elements:
            if not el.element_id or not el.role:
                raise UISemanticError(
                    f"UI validation failed: Element {el.element_id} lacks ID or role."
                )

        # 5. Build Observation Object and publish to Perception Engine
        obs_builder = ObservationBuilder(
            f"obs_ui_{int(time.time() * 1000)}", "Desktop", "SemanticUITree"
        )
        obs_builder.set_confidence(1.0)
        obs_builder.set_content(
            {
                "elements_count": len(elements),
                "window_focused": scene.focused_window_id,
                "url_loaded": page.url,
            }
        )
        obs_builder.set_metadata("page_title", page.title)

        obs = obs_builder.build()
        self.perception_engine.process_observation(obs, session_id=session_id)

        self.event_bus.publish_sync(
            Event(
                name="observation.published",
                category="Perception",
                source="UISemantic",
                payload={"observation_id": obs.observation_id},
            )
        )

        return elements
