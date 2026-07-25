"""Enterprise Visual Memory, Scene Understanding & Spatial Intelligence Platform.

Provides spatial intelligence, change detectors, and memory stores.
"""

import time
from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.perception_engine import ObservationBuilder, PerceptionEngine
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.visual_memory_intelligence")


class VisualMemoryError(Exception):
    """Raised when visual memory graph traversals or similarity matches fail."""

    pass


@dataclass
class SpatialMetadata:
    """Logical mapping of spatial layouts (e.g. Sidebar, Toolbar quadrants)."""

    layout_regions: list[dict[str, Any]] = field(default_factory=list)
    dialog_locations: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class SceneObject:
    """Evolving visual layout snapshot details containing bounds, applications, and documents."""

    scene_id: str
    timestamp: float
    applications: list[str] = field(default_factory=list)
    windows: list[dict[str, Any]] = field(default_factory=list)
    semantic_ui_elements: list[dict[str, Any]] = field(default_factory=list)
    documents: list[str] = field(default_factory=list)
    relationships: list[dict[str, Any]] = field(default_factory=list)
    visual_metadata: dict[str, Any] = field(default_factory=dict)
    spatial_metadata: SpatialMetadata = field(default_factory=SpatialMetadata)
    version: str = "1.0.0"


@dataclass
class VisualChangeReport:
    """Outlines modifications between two point-in-time scene snapshots."""

    added_windows: list[str] = field(default_factory=list)
    removed_windows: list[str] = field(default_factory=list)
    layout_changes: list[dict[str, Any]] = field(default_factory=list)
    navigation_changes: list[dict[str, Any]] = field(default_factory=list)
    ui_changes: list[dict[str, Any]] = field(default_factory=list)
    dialog_changes: list[dict[str, Any]] = field(default_factory=list)
    document_changes: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class VisualEpisode:
    """Tracks a sequence timeline of snapshots within an active workspace session."""

    episode_id: str
    session_id: str
    workspace_id: str
    scenes: list[SceneObject] = field(default_factory=list)
    timeline: list[float] = field(default_factory=list)
    observation_references: list[str] = field(default_factory=list)
    memory_links: list[str] = field(default_factory=list)


class SceneBuilder:
    """Assembles unified SceneObjects from UI trees and applications lists."""

    def build_scene_object(
        self,
        scene_id: str,
        apps: list[str],
        windows: list[dict[str, Any]],
        ui_elements: list[dict[str, Any]],
        docs: list[str],
        spatial: SpatialMetadata,
    ) -> SceneObject:
        return SceneObject(
            scene_id=scene_id,
            timestamp=time.time(),
            applications=apps,
            windows=windows,
            semantic_ui_elements=ui_elements,
            documents=docs,
            spatial_metadata=spatial,
        )


class SceneGraph:
    """Tracks graph connections pointing between elements, tabs, and documents."""

    def __init__(self) -> None:
        self.nodes: dict[str, Any] = {}
        # Map of source_id -> list of target_ids
        self.edges: dict[str, list[str]] = {}

    def build_graph(self, scene: SceneObject) -> None:
        """Populate graph nodes and build references links."""
        for app in scene.applications:
            self.nodes[app] = {"type": "Application"}
            if app not in self.edges:
                self.edges[app] = []

        for win in scene.windows:
            win_id = win.get("window_id", "unknown_win")
            self.nodes[win_id] = win
            if win_id not in self.edges:
                self.edges[win_id] = []

            # Link window to parent app if declared
            parent_app = win.get("application_name")
            if parent_app and parent_app in self.edges:
                self.link(parent_app, win_id)

    def link(self, source_id: str, target_id: str) -> None:
        """Create reference edge between graph nodes."""
        if source_id in self.edges and target_id not in self.edges[source_id]:
            self.edges[source_id].append(target_id)

    def query_connections(self, node_id: str) -> list[str]:
        """Retrieve target node references linked to this node."""
        return self.edges.get(node_id, [])


class SpatialIntelligenceEngine:
    """Translates physical coordinates boundaries into logical quadrants areas."""

    def analyze_spatial_layout(self, windows: list[dict[str, Any]]) -> SpatialMetadata:
        """Categorize window bounds coordinates into logical layouts regions."""
        regions = []
        for win in windows:
            x = win.get("x", 0)
            y = win.get("y", 0)

            # Categorize quadrants
            quadrant = "Center"
            if x < 200:
                quadrant = "LeftSidebar"
            elif y < 100:
                quadrant = "TopToolbar"

            regions.append(
                {
                    "window_id": win.get("window_id"),
                    "quadrant": quadrant,
                    "logical_area": "MainWorkspace" if win.get("width", 0) > 800 else "SubPanel",
                }
            )
        return SpatialMetadata(layout_regions=regions)


class SceneSimilarityEngine:
    """Computes similarity metrics and layout alignment scores."""

    def compare_scenes(self, scene_a: SceneObject, scene_b: SceneObject) -> float:
        """Return similarity percentage scoring [0.0, 1.0]."""
        # Exact match
        if scene_a.scene_id == scene_b.scene_id:
            return 1.0

        # Match apps count and windows list structures
        intersection = set(scene_a.applications).intersection(set(scene_b.applications))
        union = set(scene_a.applications).union(set(scene_b.applications))
        if not union:
            return 1.0

        return len(intersection) / len(union)


class ChangeDetectionEngine:
    """Compares subsequent snapshots, identifying layout changes and dialog updates."""

    def detect_changes(self, before: SceneObject, after: SceneObject) -> VisualChangeReport:
        """Diff before and after layouts, returning a structured change report."""
        before_wins = {str(w["window_id"]) for w in before.windows if w.get("window_id")}
        after_wins = {str(w["window_id"]) for w in after.windows if w.get("window_id")}

        added = list(after_wins - before_wins)
        removed = list(before_wins - after_wins)

        layout_diffs = []
        for win_id in after_wins.intersection(before_wins):
            win_b = next((w for w in before.windows if w.get("window_id") == win_id), {})
            win_a = next((w for w in after.windows if w.get("window_id") == win_id), {})
            if win_b.get("x") != win_a.get("x") or win_b.get("y") != win_a.get("y"):
                layout_diffs.append(
                    {
                        "window_id": win_id,
                        "change": "position_shifted",
                        "delta": {"x": win_a.get("x", 0) - win_b.get("x", 0)},
                    }
                )

        return VisualChangeReport(
            added_windows=added,
            removed_windows=removed,
            layout_changes=layout_diffs,
        )


class VisualMemoryStore:
    """Maintains sliding database history of point-in-time visual layouts snapshots."""

    def __init__(self, capacity: int = 100) -> None:
        self.capacity = capacity
        self.history: list[SceneObject] = []

    def store_scene(self, scene: SceneObject) -> None:
        """Append scene, evicting oldest item if capacity threshold is exceeded."""
        self.history.append(scene)
        if len(self.history) > self.capacity:
            self.history.pop(0)


class VisualEpisodeManager:
    """Handles visual episodes tracking active timelines of sessions workspaces."""

    def __init__(self) -> None:
        self.episodes: dict[str, VisualEpisode] = {}

    def create_episode(self, episode_id: str, session_id: str, workspace_id: str) -> VisualEpisode:
        episode = VisualEpisode(
            episode_id=episode_id, session_id=session_id, workspace_id=workspace_id
        )
        self.episodes[episode_id] = episode
        return episode


class VisualMemoryManager:
    """Subsystem coordinator tracking scene graphs, similarity, and layout changes."""

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

        self.builder = SceneBuilder()
        self.graph = SceneGraph()
        self.spatial_engine = SpatialIntelligenceEngine()
        self.similarity_engine = SceneSimilarityEngine()
        self.change_detector = ChangeDetectionEngine()
        self.store = VisualMemoryStore()
        self.episode_manager = VisualEpisodeManager()

    def record_scene(
        self,
        scene_id: str,
        apps: list[str],
        windows: list[dict[str, Any]],
        ui_elements: list[dict[str, Any]],
        docs: list[str],
        episode_id: str | None = None,
        session_id: str | None = None,
    ) -> SceneObject:
        """Analyze layout quadrants, build graphs, and detect changes.

        Afterwards, store in history, and publish observations.
        """
        # 1. Analyze spatial areas and build scene object
        spatial = self.spatial_engine.analyze_spatial_layout(windows)
        scene = self.builder.build_scene_object(scene_id, apps, windows, ui_elements, docs, spatial)

        # 2. Update Graph & Store
        self.graph.build_graph(scene)
        self.event_bus.publish_sync(
            Event(
                name="scene.stored",
                category="Perception",
                source="VisualMemory",
                payload={"scene_id": scene.scene_id},
            )
        )

        # Compare with previous if available to detect layout changes
        if self.store.history:
            prev = self.store.history[-1]
            similarity = self.similarity_engine.compare_scenes(prev, scene)
            self.event_bus.publish_sync(
                Event(
                    name="scene.compared",
                    category="Perception",
                    source="VisualMemory",
                    payload={
                        "scene_id": scene.scene_id,
                        "prev_scene_id": prev.scene_id,
                        "similarity": similarity,
                    },
                )
            )

            changes = self.change_detector.detect_changes(prev, scene)
            if changes.added_windows or changes.removed_windows or changes.layout_changes:
                self.event_bus.publish_sync(
                    Event(
                        name="scene.changed",
                        category="Perception",
                        source="VisualMemory",
                        payload={
                            "added_count": len(changes.added_windows),
                            "removed_count": len(changes.removed_windows),
                        },
                    )
                )

        self.store.store_scene(scene)

        # 3. Associate with Episode if available
        if episode_id and episode_id in self.episode_manager.episodes:
            episode = self.episode_manager.episodes[episode_id]
            episode.scenes.append(scene)
            episode.timeline.append(time.time())
            self.event_bus.publish_sync(
                Event(
                    name="visual_episode.created",
                    category="Perception",
                    source="VisualMemory",
                    payload={"episode_id": episode_id, "scenes_count": len(episode.scenes)},
                )
            )

        self.event_bus.publish_sync(
            Event(
                name="memory.updated",
                category="Perception",
                source="VisualMemory",
                payload={"history_depth": len(self.store.history)},
            )
        )

        # 4. Build Observation Object and publish to Perception Engine
        obs_builder = ObservationBuilder(f"obs_vm_{scene.scene_id}", "Screen", "VisualSceneMemory")
        obs_builder.set_confidence(1.0)
        obs_builder.set_content(
            {
                "scene_id": scene.scene_id,
                "apps_count": len(apps),
                "windows_count": len(windows),
                "documents_count": len(docs),
            }
        )
        obs_builder.set_metadata("history_index", len(self.store.history) - 1)

        obs = obs_builder.build()
        self.perception_engine.process_observation(obs, session_id=session_id)

        return scene
