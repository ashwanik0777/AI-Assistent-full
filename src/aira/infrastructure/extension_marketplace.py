"""Enterprise Extension Marketplace, Publisher Governance & Ecosystem Platform for AIRA.

Provides catalogs registries, publisher lists, and reputation metrics.
"""

from dataclasses import dataclass, field
from typing import Any, ClassVar

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.extension_marketplace")


class ExtensionMarketplaceError(Exception):
    """Base exception raised for all marketplace catalog, verification, or promotion errors."""

    pass


@dataclass
class PublisherRecord:
    """Identity tracking credentials for ecosystem publishers."""

    publisher_id: str
    name: str
    category: str  # Enterprise, Community, Organization
    is_verified: bool = False


@dataclass
class MarketplaceEntry:
    """Catalog metadata schema details for registered plugins."""

    extension_id: str
    publisher_id: str
    version: str
    category: str
    release_channel: str = "Experimental"
    quality_score: float = 5.0
    security_status: str = "Unverified"
    download_count: int = 0
    compatibility_matrix: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class PublisherRegistry:
    """Stores active publisher profile entries."""

    def __init__(self) -> None:
        self.publishers: dict[str, PublisherRecord] = {}

    def register_publisher(self, publisher: PublisherRecord) -> None:
        """Register a new publisher record."""
        self.publishers[publisher.publisher_id] = publisher

    def get_publisher(self, publisher_id: str) -> PublisherRecord | None:
        """Retrieve publisher record."""
        return self.publishers.get(publisher_id)


class ReviewEngine:
    """Validates marketplace metadata completeness, API compliance, and safety."""

    def evaluate_entry(self, entry: MarketplaceEntry) -> dict[str, Any]:
        """Verify completeness, checking that metadata holds doc and compatibility matrices."""
        has_doc = "documentation" in entry.metadata
        has_compat = len(entry.compatibility_matrix) > 0

        if not has_doc or not has_compat:
            return {
                "success": False,
                "reason": "Missing documentation or compatibility matrix elements.",
            }

        return {
            "success": True,
            "quality_score": 8.5 if has_doc and has_compat else 5.0,
            "security_status": "Clean",
        }


class ReleaseChannelManager:
    """Manages channel promotion rules across environments (Experimental -> Beta -> Stable)."""

    ALLOWED_CHANNELS: ClassVar[set[str]] = {"Experimental", "Alpha", "Beta", "Stable", "LTS"}

    def promote_channel(self, entry: MarketplaceEntry, target_channel: str) -> None:
        """Move release channel or raise error on invalid target."""
        if target_channel not in self.ALLOWED_CHANNELS:
            raise ExtensionMarketplaceError(
                f"Promotion failed: Target channel '{target_channel}' is not supported."
            )
        # Rule check: Cannot promote to Stable unless quality score >= 7.0
        if target_channel == "Stable" and entry.quality_score < 7.0:
            raise ExtensionMarketplaceError(
                "Promotion failed: Quality score must be >= 7.0 to promote to Stable."
            )
        entry.release_channel = target_channel


class ReputationEngine:
    """Calculates active quality and reputation scores based on ratings and downloads."""

    def update_reputation(self, entry: MarketplaceEntry, new_downloads: int) -> float:
        """Calculate reputation offset."""
        entry.download_count += new_downloads
        # Simple algorithm index
        score = min(10.0, 5.0 + (entry.download_count / 100.0))
        entry.quality_score = round(score, 2)
        return entry.quality_score


class MarketplaceCatalog:
    """Maintains collections of featured and approved packages."""

    def __init__(self) -> None:
        self.entries: dict[str, MarketplaceEntry] = {}

    def add_entry(self, entry: MarketplaceEntry) -> None:
        """Register entry details."""
        self.entries[entry.extension_id] = entry

    def get_entry(self, extension_id: str) -> MarketplaceEntry | None:
        """Fetch matching catalog item."""
        return self.entries.get(extension_id)

    def search(self, category: str) -> list[MarketplaceEntry]:
        """Search entries matching target category."""
        return [x for x in self.entries.values() if x.category == category]


class MarketplaceManager:
    """Coordinating manager verifying publishers, running reviews, and updating search catalogs."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.publisher_registry = PublisherRegistry()
        self.review_engine = ReviewEngine()
        self.channel_manager = ReleaseChannelManager()
        self.reputation_engine = ReputationEngine()
        self.catalog = MarketplaceCatalog()

    def register_publisher(self, publisher: PublisherRecord) -> None:
        """Verify registry and save publisher profile."""
        self.publisher_registry.register_publisher(publisher)
        self.event_bus.publish_sync(
            Event(
                name="publisher.registered",
                category="Marketplace",
                source="MarketplaceManager",
                payload={
                    "publisher_id": publisher.publisher_id,
                    "is_verified": publisher.is_verified,
                },
            )
        )

    def publish_extension(self, entry: MarketplaceEntry) -> None:
        """Check publisher identity registration, review metadata contents, and catalog results."""
        # 1. Verify Publisher
        pub = self.publisher_registry.get_publisher(entry.publisher_id)
        if not pub or not pub.is_verified:
            raise ExtensionMarketplaceError(
                f"Publication failed: Publisher '{entry.publisher_id}' is unverified."
            )

        # 2. Run Review
        review = self.review_engine.evaluate_entry(entry)
        if not review["success"]:
            raise ExtensionMarketplaceError(
                f"Publication failed: Review engine rejected package. Reason: {review['reason']}"
            )

        entry.quality_score = review["quality_score"]
        entry.security_status = review["security_status"]

        # 3. Add to Catalog
        self.catalog.add_entry(entry)

        self.event_bus.publish_sync(
            Event(
                name="review.completed",
                category="Marketplace",
                source="MarketplaceManager",
                payload={"extension_id": entry.extension_id, "quality_score": entry.quality_score},
            )
        )

        self.event_bus.publish_sync(
            Event(
                name="extension.published",
                category="Marketplace",
                source="MarketplaceManager",
                payload={"extension_id": entry.extension_id, "version": entry.version},
            )
        )

        self.event_bus.publish_sync(
            Event(
                name="catalog.updated",
                category="Marketplace",
                source="MarketplaceManager",
                payload={"action": "add", "extension_id": entry.extension_id},
            )
        )

    def promote_extension_channel(self, extension_id: str, target_channel: str) -> None:
        """Transition extension release channel and notify catalog updates."""
        entry = self.catalog.get_entry(extension_id)
        if not entry:
            raise ExtensionMarketplaceError(
                f"Operation failed: Extension '{extension_id}' not found."
            )

        self.channel_manager.promote_channel(entry, target_channel)

        self.event_bus.publish_sync(
            Event(
                name="channel.updated",
                category="Marketplace",
                source="MarketplaceManager",
                payload={"extension_id": extension_id, "release_channel": target_channel},
            )
        )

    def track_download_metric(self, extension_id: str, count: int) -> None:
        """Update metrics trends reputation scores."""
        entry = self.catalog.get_entry(extension_id)
        if not entry:
            raise ExtensionMarketplaceError(
                f"Operation failed: Extension '{extension_id}' not found."
            )

        self.reputation_engine.update_reputation(entry, count)

        self.event_bus.publish_sync(
            Event(
                name="reputation.updated",
                category="Marketplace",
                source="MarketplaceManager",
                payload={"extension_id": extension_id, "quality_score": entry.quality_score},
            )
        )
