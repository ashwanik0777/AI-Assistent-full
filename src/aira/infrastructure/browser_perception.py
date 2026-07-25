"""Enterprise Browser Perception & Page Intelligence Engine for AIRA.

Defines browser contracts, analyzes accessibility trees, DOM topologies, and navigation graphs.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.perception_engine import ObservationBuilder, PerceptionEngine
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.browser_perception")


class BrowserPerceptionError(Exception):
    """Raised when browser metadata querying or DOM analysis fails."""

    pass


@dataclass
class BrowserTab:
    """Tab node representation within a browser session window."""

    tab_id: str
    title: str
    url: str
    is_active: bool = False


@dataclass
class BrowserSession:
    """Active session bounds containing open tabs, navigation paths history, and site rules."""

    session_id: str
    window_id: str
    tabs: list[BrowserTab] = field(default_factory=list)
    active_tab_id: str | None = None
    navigation_history: list[str] = field(default_factory=list)
    downloads_metadata: list[dict[str, Any]] = field(default_factory=list)
    permissions_metadata: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class PageModel:
    """Consolidated representation of a browser page DOM state and accessibility labels."""

    page_id: str
    url: str
    title: str
    tabs: list[BrowserTab] = field(default_factory=list)
    frames: list[dict[str, Any]] = field(default_factory=list)
    sections: list[dict[str, Any]] = field(default_factory=list)
    navigation_metadata: dict[str, Any] = field(default_factory=dict)
    forms_metadata: list[dict[str, Any]] = field(default_factory=list)
    accessibility_metadata: dict[str, Any] = field(default_factory=dict)
    visible_regions: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    version: str = "1.0.0"


class BaseBrowserProvider(ABC):
    """Abstract interface defining interchangeable browser browser adapters."""

    @abstractmethod
    def get_active_session(self) -> BrowserSession:
        """Query open tabs list and active window metadata details."""
        pass

    @abstractmethod
    def get_page_model(self) -> PageModel:
        """Parse active page elements, accessibility trees, and ARIA labels."""
        pass


class MockBrowserProvider(BaseBrowserProvider):
    """Simulated provider mirroring active Chromium tabs and documentation sites content."""

    def get_active_session(self) -> BrowserSession:
        tabs = [
            BrowserTab("tab_docs", "AIRA Developers Guide", "https://aira.dev/guide", True),
            BrowserTab("tab_github", "GitHub - AIRA Repo", "https://github.com/aira/core", False),
        ]
        return BrowserSession(
            session_id="sess_browser_01",
            window_id="win_chrome_01",
            tabs=tabs,
            active_tab_id="tab_docs",
            navigation_history=["https://aira.dev", "https://aira.dev/guide"],
        )

    def get_page_model(self) -> PageModel:
        tabs = [
            BrowserTab("tab_docs", "AIRA Developers Guide", "https://aira.dev/guide", True),
        ]
        return PageModel(
            page_id="page_docs_01",
            url="https://aira.dev/guide",
            title="AIRA Developers Guide",
            tabs=tabs,
            sections=[
                {"section_id": "sec_header", "role": "banner", "text": "AIRA Documentation Hub"},
                {"section_id": "sec_main", "role": "main", "text": "Sprint 8.3 Browser Perception"},
            ],
            forms_metadata=[
                {"form_id": "form_search", "inputs": [{"name": "q", "type": "search"}]}
            ],
            accessibility_metadata={
                "accessibility_tree": {
                    "role": "WebArea",
                    "name": "AIRA Developers Guide",
                    "children": [
                        {"role": "heading", "name": "Sprint 8.3 Browser Perception", "level": 1}
                    ],
                }
            },
        )


class DOMProvider:
    """Analyzes semantic HTML tags, input components, and ARIA landmarks."""

    def index_dom(self, page: PageModel) -> dict[str, Any]:
        """Convert page metadata list into semantic elements registry mappings."""
        return {
            "landmarks": [s.get("role") for s in page.sections if "role" in s],
            "forms_count": len(page.forms_metadata),
        }


class AccessibilityProvider:
    """Traverses page accessibility hierarchies, ARIA nodes, and active focus parameters."""

    def index_accessibility(self, page: PageModel) -> dict[str, Any]:
        """Extract accessibility role states mappings."""
        tree = page.accessibility_metadata.get("accessibility_tree", {})
        return {
            "root_role": tree.get("role"),
            "root_name": tree.get("name"),
        }


class BrowserMetadataProvider:
    """Reads tabs registries, cookies, permissions levels, and history lists."""

    def get_metadata(self, session: BrowserSession) -> dict[str, Any]:
        active_url = next((t.url for t in session.tabs if t.tab_id == session.active_tab_id), None)
        return {
            "active_tab_url": active_url,
            "history_depth": len(session.navigation_history),
        }


class PageModelBuilder:
    """Aggregates DOM and accessibility profiles into consolidated PageModels."""

    def build(self, raw_page: PageModel, dom: dict[str, Any], a11y: dict[str, Any]) -> PageModel:
        """Augment page model details metadata."""
        raw_page.metadata.update({"dom_index": dom, "a11y_index": a11y})
        return raw_page


class NavigationGraph:
    """Models tabs histories, relative redirects, and modal dialog paths."""

    def __init__(self) -> None:
        self.nodes: dict[str, Any] = {}
        self.edges: dict[str, list[str]] = {}

    def build_navigation_paths(self, session: BrowserSession) -> None:
        """Register navigation hops lists in navigation graph."""
        history = session.navigation_history
        for i, url in enumerate(history):
            self.nodes[url] = {"index": i}
            if url not in self.edges:
                self.edges[url] = []

            # Link consecutive redirect sites
            if i > 0:
                prev_url = history[i - 1]
                if url not in self.edges[prev_url]:
                    self.edges[prev_url].append(url)

    def query_redirects(self, url: str) -> list[str]:
        """Query downstream target redirect URLs."""
        return self.edges.get(url, [])


class BrowserPerceptionEngine:
    """Coordinator extracting page details, validations, and publishing observations.

    It collects page trees, accessibility details, and navigation graphs.
    """

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

        # Default to simulated Mock Browser Provider
        self.provider: BaseBrowserProvider = MockBrowserProvider()
        self.dom_provider = DOMProvider()
        self.a11y_provider = AccessibilityProvider()
        self.meta_provider = BrowserMetadataProvider()
        self.model_builder = PageModelBuilder()
        self.graph = NavigationGraph()

    def analyze_browser_page(self, session_id: str | None = None) -> PageModel:
        """Execute page modeling checks, validate schemas, and publish standard Observations."""
        # 1. Connect and Fetch Session
        session = self.provider.get_active_session()
        self.event_bus.publish_sync(
            Event(
                name="browser.connected",
                category="Perception",
                source="BrowserPerception",
                payload={"session_id": session.session_id, "active_tab_id": session.active_tab_id},
            )
        )

        # 2. Build Page Model
        raw_page = self.provider.get_page_model()
        dom_meta = self.dom_provider.index_dom(raw_page)
        self.event_bus.publish_sync(
            Event(
                name="dom.indexed",
                category="Perception",
                source="BrowserPerception",
                payload={"landmarks_count": len(dom_meta.get("landmarks", []))},
            )
        )

        a11y_meta = self.a11y_provider.index_accessibility(raw_page)
        self.event_bus.publish_sync(
            Event(
                name="accessibility.indexed",
                category="Perception",
                source="BrowserPerception",
                payload={"root_role": a11y_meta.get("root_role")},
            )
        )

        page = self.model_builder.build(raw_page, dom_meta, a11y_meta)
        self.event_bus.publish_sync(
            Event(
                name="page.modeled",
                category="Perception",
                source="BrowserPerception",
                payload={"page_id": page.page_id, "url": page.url},
            )
        )

        # 3. Navigation Graph Update
        self.graph.build_navigation_paths(session)
        self.event_bus.publish_sync(
            Event(
                name="navigation.updated",
                category="Perception",
                source="BrowserPerception",
                payload={"history_depth": len(session.navigation_history)},
            )
        )

        # 4. Validate page schemas integrity constraints
        if not page.url or not page.title:
            raise BrowserPerceptionError("Browser Page validation failed: URL or title is missing.")

        # 5. Build Observation Object and publish to Perception Engine
        obs_builder = ObservationBuilder(f"obs_{page.page_id}", "Browser", "PageModel")
        obs_builder.set_confidence(1.0)
        obs_builder.set_content(
            {
                "page_id": page.page_id,
                "url": page.url,
                "title": page.title,
                "forms_count": len(page.forms_metadata),
                "landmarks": dom_meta.get("landmarks", []),
            }
        )
        obs_builder.set_metadata("session_id", session.session_id)

        obs = obs_builder.build()
        self.perception_engine.process_observation(obs, session_id=session_id)

        self.event_bus.publish_sync(
            Event(
                name="observation.published",
                category="Perception",
                source="BrowserPerception",
                payload={"observation_id": obs.observation_id},
            )
        )

        return page
