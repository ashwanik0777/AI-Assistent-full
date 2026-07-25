"""Enterprise Screen Intelligence & Scene Analysis Engine for AIRA.

Provides display provider adapters, coordinates normalizations, and scene caching systems.
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

logger = structlog.get_logger("aira.screen_intelligence")


class ScreenIntelligenceError(Exception):
    """Raised when screen layout processing or display captures fail."""

    pass


@dataclass
class DisplayMetadata:
    """Metadata representing a single connected physical or virtual display device."""

    display_id: str
    width: int
    height: int
    scale: float = 1.0  # Retina / High DPI scale (e.g. 2.0)
    is_primary: bool = True
    x_offset: int = 0
    y_offset: int = 0
    orientation: str = "landscape"  # landscape, portrait


@dataclass
class WindowMetadata:
    """Metadata representing layout bounds and focus properties of a target application."""

    window_id: str
    application: str
    title: str
    x: int
    y: int
    width: int
    height: int
    is_visible: bool = True
    is_focused: bool = False
    z_order: int = 0
    state: str = "Normal"  # Normal, Minimized, Maximized


@dataclass
class ScreenScene:
    """Composite visual topology of all connected displays and active windows."""

    scene_id: str
    timestamp: float
    displays: list[DisplayMetadata] = field(default_factory=list)
    windows: list[WindowMetadata] = field(default_factory=list)
    focused_window_id: str | None = None
    display_resolution: str = "1920x1080"
    scaling: float = 1.0
    coordinate_system: str = "Normalized"
    metadata: dict[str, Any] = field(default_factory=dict)
    version: str = "1.0.0"


class BaseDisplayProvider(ABC):
    """Abstract interface for querying physical displays and window layers."""

    @abstractmethod
    def detect_displays(self) -> list[DisplayMetadata]:
        """Query physical screens layout configuration."""
        pass

    @abstractmethod
    def capture_window_metadata(self) -> list[WindowMetadata]:
        """Fetch details of visible and focused windows."""
        pass


class MockDisplayProvider(BaseDisplayProvider):
    """Simulated display adapter yielding static Retina display and workspace bounds metadata."""

    def detect_displays(self) -> list[DisplayMetadata]:
        return [
            DisplayMetadata(
                display_id="disp_primary",
                width=1920,
                height=1080,
                scale=2.0,
                is_primary=True,
                x_offset=0,
                y_offset=0,
            ),
            DisplayMetadata(
                display_id="disp_external",
                width=1440,
                height=900,
                scale=1.0,
                is_primary=False,
                x_offset=1920,
                y_offset=0,
            ),
        ]

    def capture_window_metadata(self) -> list[WindowMetadata]:
        return [
            WindowMetadata(
                window_id="win_vscode",
                application="VS Code",
                title="AIRA Assistent - src/app.py",
                x=100,
                y=50,
                width=1200,
                height=800,
                is_visible=True,
                is_focused=True,
                z_order=1,
            ),
            WindowMetadata(
                window_id="win_terminal",
                application="Terminal",
                title="zsh - python run_developer_verification.py",
                x=150,
                y=200,
                width=800,
                height=500,
                is_visible=True,
                is_focused=False,
                z_order=2,
            ),
        ]


class ScreenCaptureManager:
    """Manages active capture sessions and interfaces with native DisplayProviders."""

    def __init__(self, provider: BaseDisplayProvider) -> None:
        self.provider = provider

    def capture_scene_metadata(self) -> tuple[list[DisplayMetadata], list[WindowMetadata]]:
        """Fetch raw display layout configurations and active window metadata bounds."""
        try:
            displays = self.provider.detect_displays()
            windows = self.provider.capture_window_metadata()
            return displays, windows
        except Exception as e:
            raise ScreenIntelligenceError(f"Display capture operation failed: {e}") from e


class SceneBuilder:
    """Normalizes coordinate systems and compiles valid ScreenScene objects."""

    def build_scene(
        self, scene_id: str, displays: list[DisplayMetadata], windows: list[WindowMetadata]
    ) -> ScreenScene:
        """Construct scene topology and normalize window coordinates."""
        # Find primary display bounds
        primary_disp = next((d for d in displays if d.is_primary), None)
        resolution_str = "1920x1080"
        scale = 1.0
        if primary_disp:
            resolution_str = f"{primary_disp.width}x{primary_disp.height}"
            scale = primary_disp.scale

        # Identify focused window
        focused_win = next((w for w in windows if w.is_focused), None)
        focused_id = focused_win.window_id if focused_win else None

        # Coordinate Normalization checks
        for w in windows:
            # Shift windows falling entirely in coordinates systems bounds
            if w.x < 0:
                w.x = 0
            if w.y < 0:
                w.y = 0

        return ScreenScene(
            scene_id=scene_id,
            timestamp=time.time(),
            displays=displays,
            windows=windows,
            focused_window_id=focused_id,
            display_resolution=resolution_str,
            scaling=scale,
        )


class SceneCache:
    """Maintains sliding cache references of previous and latest screens scenes."""

    def __init__(self, expiration_seconds: float = 5.0) -> None:
        self.expiration_seconds = expiration_seconds
        self.latest_scene: ScreenScene | None = None
        self.previous_scene: ScreenScene | None = None
        self.last_cached_time: float = 0.0

    def update_cache(self, scene: ScreenScene) -> None:
        """Shift latest scene pointer to previous index and cache new scene."""
        self.previous_scene = self.latest_scene
        self.latest_scene = scene
        self.last_cached_time = time.time()

    def get_latest(self) -> ScreenScene | None:
        """Retrieve latest cached scene if it hasn't expired yet."""
        if not self.latest_scene:
            return None

        # Invalidate if expired
        if time.time() - self.last_cached_time > self.expiration_seconds:
            self.latest_scene = None
            self.previous_scene = None
            return None

        return self.latest_scene


class ScreenIntelligenceManager:
    """Principal coordinator building visual scenes and publishing Screen observations."""

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

        # Default to simulated Mock Display Provider
        self.provider = MockDisplayProvider()
        self.capture_manager = ScreenCaptureManager(self.provider)
        self.builder = SceneBuilder()
        self.cache = SceneCache()

    def analyze_screen(self, session_id: str | None = None) -> ScreenScene:
        """Orchestrate layout captures, validate topologies, and publish standard observations."""
        scene_id = f"scene_{int(time.time() * 1000)}"

        # 1. Capture & Build Scene
        displays, windows = self.capture_manager.capture_scene_metadata()
        self.event_bus.publish_sync(
            Event(
                name="scene.captured",
                category="Perception",
                source="ScreenIntelligence",
                payload={"scene_id": scene_id, "windows_count": len(windows)},
            )
        )

        scene = self.builder.build_scene(scene_id, displays, windows)

        # 2. Validate Scene Constraints
        if not scene.displays:
            raise ScreenIntelligenceError("Scene validation failed: No displays detected.")

        self.event_bus.publish_sync(
            Event(
                name="scene.validated",
                category="Perception",
                source="ScreenIntelligence",
                payload={"scene_id": scene_id},
            )
        )

        # 3. Publish updates events
        self.event_bus.publish_sync(
            Event(
                name="window_metadata.updated",
                category="Perception",
                source="ScreenIntelligence",
                payload={
                    "windows_count": len(windows),
                    "focused_window_id": scene.focused_window_id,
                },
            )
        )
        self.event_bus.publish_sync(
            Event(
                name="display.updated",
                category="Perception",
                source="ScreenIntelligence",
                payload={"displays_count": len(displays)},
            )
        )

        # 4. Cache Scene
        self.cache.update_cache(scene)
        self.event_bus.publish_sync(
            Event(
                name="scene.cached",
                category="Perception",
                source="ScreenIntelligence",
                payload={"scene_id": scene_id},
            )
        )

        # 5. Convert to standardized Observation Object and publish to Perception Engine
        obs_builder = ObservationBuilder(f"obs_{scene_id}", "Screen", "LayoutScene")
        obs_builder.set_confidence(1.0)
        obs_builder.set_content(
            {
                "focused_window_id": scene.focused_window_id,
                "display_resolution": scene.display_resolution,
                "windows_count": len(windows),
            }
        )
        obs_builder.set_metadata("scene_id", scene_id)

        obs = obs_builder.build()
        self.perception_engine.process_observation(obs, session_id=session_id)

        return scene
