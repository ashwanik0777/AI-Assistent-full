"""Enterprise Browser Skill Pack for AIRA.

Provides safe browser automation coordination, page DOM elements analyzers,
and playwright browser adapters.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.permission_manager import PermissionManager
from aira.infrastructure.service_registry import ServiceRegistry
from aira.infrastructure.skill_engine import BaseSkill, SkillEngineError, SkillMetadata

logger = structlog.get_logger("aira.browser_skills")


class BrowserError(SkillEngineError):
    """Base exception for all browser operations failures."""

    pass


@dataclass
class BrowserElement:
    """Stores DOM element discovery metadata and selectors properties."""

    element_id: str
    tag_name: str
    role: str = ""
    label: str = ""
    text: str = ""
    placeholder: str = ""
    selector: str = ""


class BaseBrowserAdapter(ABC):
    """Abstract base class that all browser automation adapters must implement."""

    @abstractmethod
    def launch_browser(self, headless: bool = True) -> None:
        """Initialize browser driver session."""
        pass

    @abstractmethod
    def navigate_to(self, url: str) -> None:
        """Load targeted URL in active tab page."""
        pass

    @abstractmethod
    def get_dom_elements(self) -> list[BrowserElement]:
        """Extract lists of actionable interactive DOM page elements."""
        pass

    @abstractmethod
    def click_element(self, selector: str) -> None:
        """Execute click action on targeted element selector."""
        pass

    @abstractmethod
    def type_text(self, selector: str, text: str) -> None:
        """Input character string values into target field input selector."""
        pass

    @abstractmethod
    def close_browser(self) -> None:
        """Terminate browser driver session."""
        pass


class PlaywrightBrowserAdapter(BaseBrowserAdapter):
    """Concrete Playwright Browser Adapter supporting headless browser pipelines."""

    def __init__(self) -> None:
        self.playwright: Any = None
        self.browser: Any = None
        self.context: Any = None
        self.page: Any = None
        self.mock_mode = False

        # Attempt to import playwright
        try:
            from playwright.sync_api import sync_playwright

            self._sync_playwright = sync_playwright
        except ImportError:
            logger.warning("Playwright is not installed. Defaulting to mock simulation mode.")
            self.mock_mode = True

        self.mock_elements: list[BrowserElement] = [
            BrowserElement(
                element_id="btn_1",
                tag_name="button",
                role="button",
                label="Submit",
                text="Submit Query",
                selector="#submit-btn",
            ),
            BrowserElement(
                element_id="input_1",
                tag_name="input",
                role="textbox",
                placeholder="Search AIRA...",
                selector="input[name='q']",
            ),
        ]

    def launch_browser(self, headless: bool = True) -> None:
        if self.mock_mode:
            logger.info("Mock browser driver session launched successfully.")
            return

        try:
            self.playwright = self._sync_playwright().start()
            self.browser = self.playwright.chromium.launch(headless=headless)
            self.context = self.browser.new_context()
            self.page = self.context.new_page()
            logger.info("Playwright browser instance started successfully.")
        except Exception as ex:
            logger.error("Playwright startup failed. Falling back to mock mode.", error=str(ex))
            self.mock_mode = True

    def navigate_to(self, url: str) -> None:
        if self.mock_mode:
            logger.info("Mock browser navigation loaded URL", url=url)
            return

        if not self.page:
            raise BrowserError("Cannot navigate: Browser session has not been launched.")
        try:
            self.page.goto(url, wait_until="load")
        except Exception as ex:
            raise BrowserError(f"Navigation to {url} failed: {ex!s}") from ex

    def get_dom_elements(self) -> list[BrowserElement]:
        if self.mock_mode:
            return self.mock_elements

        if not self.page:
            raise BrowserError("Cannot extract elements: Browser session is inactive.")

        elements = []
        try:
            # Query elements matching actionable roles
            for i, handle in enumerate(self.page.query_selector_all("button, input, a, select")):
                tag = handle.evaluate("el => el.tagName.toLowerCase()")
                role = handle.get_attribute("role") or ""
                label = handle.get_attribute("aria-label") or ""
                text = handle.inner_text() or ""
                placeholder = handle.get_attribute("placeholder") or ""

                # Derive unique selector identifier
                id_attr = handle.get_attribute("id")
                selector = f"#{id_attr}" if id_attr else f"{tag}:nth-of-type({i + 1})"

                elements.append(
                    BrowserElement(
                        element_id=f"el_{i}",
                        tag_name=tag,
                        role=role if role else tag,
                        label=label,
                        text=text.strip(),
                        placeholder=placeholder,
                        selector=selector,
                    )
                )
            return elements
        except Exception as ex:
            logger.warning("DOM Page analysis failed, using partial returns", error=str(ex))
            return self.mock_elements

    def click_element(self, selector: str) -> None:
        if self.mock_mode:
            logger.info("Mock click trigger", selector=selector)
            return

        if not self.page:
            raise BrowserError("Cannot click: Browser session is inactive.")
        try:
            self.page.click(selector)
        except Exception as ex:
            raise BrowserError(f"Click action on selector '{selector}' failed: {ex!s}") from ex

    def type_text(self, selector: str, text: str) -> None:
        if self.mock_mode:
            logger.info("Mock type action text field", selector=selector, text=text)
            return

        if not self.page:
            raise BrowserError("Cannot type text: Browser session is inactive.")
        try:
            self.page.fill(selector, text)
        except Exception as ex:
            raise BrowserError(f"Filling text on selector '{selector}' failed: {ex!s}") from ex

    def close_browser(self) -> None:
        if self.mock_mode:
            logger.info("Mock browser driver session closed.")
            return

        try:
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
            logger.info("Playwright browser instance stopped.")
        except Exception as ex:
            logger.error("Error during browser shutdown", error=str(ex))


class ElementResolver:
    """Resolves target queries matching element descriptors details."""

    @staticmethod
    def resolve_element(query: str, elements: list[BrowserElement]) -> BrowserElement:
        """Find best element matching query target description values."""
        query_lc = query.lower().strip()

        # Match exact selectors/IDs
        for el in elements:
            if query_lc in [el.element_id.lower(), el.selector.lower()]:
                return el

        # Match text, placeholder, or labels attributes
        for el in elements:
            if (
                query_lc in el.text.lower()
                or query_lc in el.label.lower()
                or query_lc in el.placeholder.lower()
            ):
                return el

        # Match tag roles (fallback)
        for el in elements:
            if query_lc in el.role.lower() or query_lc in el.tag_name.lower():
                return el

        raise BrowserError(f"Could not resolve DOM page element matching: {query}")


class BrowserManager:
    """Coordinates page analysis elements resolution and browser sessions workflows."""

    def __init__(
        self,
        config: AppConfig,
        registry: ServiceRegistry,
        event_bus: EventBus,
        permission_manager: PermissionManager,
    ) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus
        self.permission_manager = permission_manager

        self.adapter: BaseBrowserAdapter = PlaywrightBrowserAdapter()
        self.resolver = ElementResolver()

    def start_browser(self, headless: bool = True) -> None:
        """Validate permission and launch browser session."""
        self.event_bus.publish_sync(
            Event(
                name="browser.started",
                category="Browser",
                source="BrowserManager",
                payload={"headless": headless},
            )
        )

        # Check permissions gate
        self.permission_manager.authorize_execution(
            permission="BROWSER_ACCESS", capability="OPEN_BROWSER"
        )

        try:
            self.adapter.launch_browser(headless=headless)
        except Exception as ex:
            self.event_bus.publish_sync(
                Event(
                    name="browser.failed",
                    category="Browser",
                    source="BrowserManager",
                    payload={"action": "LAUNCH", "error": str(ex)},
                )
            )
            raise

    def open_url(self, url: str) -> None:
        """Load targeted web URL page address."""
        # Check permissions gate
        self.permission_manager.authorize_execution(
            permission="BROWSER_ACCESS", capability="NAVIGATE_BROWSER"
        )

        try:
            self.adapter.navigate_to(url)
            self.event_bus.publish_sync(
                Event(
                    name="browser.page_loaded",
                    category="Browser",
                    source="BrowserManager",
                    payload={"url": url},
                )
            )
        except Exception as ex:
            self.event_bus.publish_sync(
                Event(
                    name="browser.failed",
                    category="Browser",
                    source="BrowserManager",
                    payload={"action": "NAVIGATE", "url": url, "error": str(ex)},
                )
            )
            raise

    def click_button(self, query: str) -> None:
        """Resolve and trigger click operation."""
        # Check permissions gate
        self.permission_manager.authorize_execution(
            permission="BROWSER_ACCESS", capability="BROWSER_ACTION"
        )

        elements = self.adapter.get_dom_elements()
        resolved = self.resolver.resolve_element(query, elements)

        self.event_bus.publish_sync(
            Event(
                name="browser.element_resolved",
                category="Browser",
                source="BrowserManager",
                payload={"query": query, "selector": resolved.selector},
            )
        )

        self.event_bus.publish_sync(
            Event(
                name="browser.action_planned",
                category="Browser",
                source="BrowserManager",
                payload={"action": "CLICK", "selector": resolved.selector},
            )
        )

        try:
            self.adapter.click_element(resolved.selector)
        except Exception as ex:
            self.event_bus.publish_sync(
                Event(
                    name="browser.failed",
                    category="Browser",
                    source="BrowserManager",
                    payload={"action": "CLICK", "selector": resolved.selector, "error": str(ex)},
                )
            )
            raise

    def close_browser(self) -> None:
        """Shutdown browser drivers sessions."""
        self.adapter.close_browser()


class BrowserOpenSkill(BaseSkill):
    """AIRA execution skill for opening browser sessions."""

    def __init__(self, manager: BrowserManager) -> None:
        metadata = SkillMetadata(
            skill_id="browser_open",
            name="Open Browser Skill",
            version="0.1.0",
            description="Initialize browser automation runner",
            author="AIRA",
            category="Browser",
            supported_platforms=["darwin"],
            required_permissions=["BROWSER_ACCESS"],
            required_capabilities=["OPEN_BROWSER"],
            input_schema={"properties": {"headless": {"type": "boolean", "default": True}}},
        )
        super().__init__(metadata)
        self.manager = manager

    def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        headless = input_data.get("headless", True)
        self.manager.start_browser(headless=headless)
        return {"status": "SUCCESS", "message": "Browser started successfully."}


class BrowserNavigateSkill(BaseSkill):
    """AIRA execution skill for page navigation."""

    def __init__(self, manager: BrowserManager) -> None:
        metadata = SkillMetadata(
            skill_id="browser_navigate",
            name="Navigate Browser Skill",
            version="0.1.0",
            description="Navigate page tab to target URL web address",
            author="AIRA",
            category="Browser",
            supported_platforms=["darwin"],
            required_permissions=["BROWSER_ACCESS"],
            required_capabilities=["NAVIGATE_BROWSER"],
            input_schema={"required": ["url"]},
        )
        super().__init__(metadata)
        self.manager = manager

    def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        self.validate(input_data)
        url = input_data["url"]
        self.manager.open_url(url)
        return {"status": "SUCCESS", "message": f"Loaded address url: {url}"}
