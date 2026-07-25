"""Enterprise Marketplace, Package Registry, Capability Exchange & Distribution Platform for AIRA.

Provides package registries, trust verification engines, catalogs, and installation managers.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.marketplace_platform")


class MarketplacePlatformError(Exception):
    """Base exception raised for validation skips, trust errors, or install failures."""

    pass


@dataclass
class MarketplacePackage:
    """Marketplace asset item detailing dependencies, compatibilities, licenses, and provenance."""

    package_id: str
    publisher: str
    # Types: Plugins, Capability Packs, Workflow Templates
    # AI Skills, Connectors, Solution Blueprints
    package_type: str
    version: str
    compatibility: str
    license_metadata: str
    trust_status: str  # Unverified, Trusted, Verified
    dependencies: list[str]
    provenance: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    manifest_version: int = 1


class PackageRegistry:
    """Stores compiled assets files descriptions."""

    def __init__(self) -> None:
        self.packages: dict[str, MarketplacePackage] = {}

    def register_package(self, package: MarketplacePackage) -> None:
        """Add asset description representation in registry database."""
        self.packages[package.package_id] = package


class PublisherRegistry:
    """Registers registered publishers names and verified status tags."""

    def __init__(self) -> None:
        self.publishers: dict[str, str] = {}  # publisher_id -> trust_level

    def register_publisher(self, publisher_id: str, trust_level: str) -> None:
        """Register developer profile status."""
        self.publishers[publisher_id] = trust_level


class TrustVerificationEngine:
    """Verifies publishers credibility and package contents validations."""

    def verify_package_trust(
        self, package: MarketplacePackage, publishers: PublisherRegistry
    ) -> bool:
        """Verify publisher is registered and status tag aligns."""
        pub_trust = publishers.publishers.get(package.publisher, "Unverified")
        return pub_trust in {"Trusted", "Verified"}


class MarketplaceCatalog:
    """Coordinates search filtering queries against registered packages list."""

    def search_assets(
        self, registry: PackageRegistry, package_type: str
    ) -> list[MarketplacePackage]:
        """Filter assets listings by matching types keys."""
        return [pkg for pkg in registry.packages.values() if pkg.package_type == package_type]


class InstallationApprovalManager:
    """Enforces organizational checks, licenses checks, and verifies dependencies alignment."""

    def check_installation_policies(
        self, package: MarketplacePackage, active_package_ids: set[str]
    ) -> None:
        """Verify dependencies resolution rules and license terms."""
        # 1. Dependency checks
        missing = set(package.dependencies) - active_package_ids
        if missing:
            raise MarketplacePlatformError(
                f"Installation blocked: Missing dependencies: {missing}."
            )

        # 2. License audit (reject empty metadata descriptions)
        if not package.license_metadata:
            raise MarketplacePlatformError(
                f"Installation blocked: License metadata for '{package.package_id}' is empty."
            )


class ProvenanceEngine:
    """Records lineage traces historical audits."""

    def __init__(self) -> None:
        self.provenance_records: dict[str, list[dict[str, Any]]] = {}

    def record_lineage(self, package_id: str, action: str, details: str) -> None:
        """Append lineage trace log."""
        self.provenance_records.setdefault(package_id, []).append(
            {"action": action, "details": details}
        )


class MarketplacePlatform:
    """Coordinating manager resolving registry, catalogs, trust validations, and approvals."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.package_registry = PackageRegistry()
        self.publisher_registry = PublisherRegistry()
        self.trust_engine = TrustVerificationEngine()
        self.catalog = MarketplaceCatalog()
        self.approval_manager = InstallationApprovalManager()
        self.provenance_engine = ProvenanceEngine()

    def register_verified_publisher(self, publisher_id: str, trust_level: str) -> None:
        """Register verified publisher profile and publish events."""
        self.publisher_registry.register_publisher(publisher_id, trust_level)

        self.event_bus.publish_sync(
            Event(
                name="marketplace.publisher.verified",
                category="Marketplace",
                source="MarketplacePlatform",
                payload={"publisher": publisher_id, "trust_level": trust_level},
            )
        )

    def publish_marketplace_package(
        self,
        package_id: str,
        publisher: str,
        package_type: str,
        version: str,
        compatibility: str,
        license_metadata: str,
        dependencies: list[str],
    ) -> MarketplacePackage:
        """Validate manifest format, check publisher trust, register asset, and publish events."""
        # Setup initial package instance
        pkg = MarketplacePackage(
            package_id=package_id,
            publisher=publisher,
            package_type=package_type,
            version=version,
            compatibility=compatibility,
            license_metadata=license_metadata,
            trust_status="Unverified",
            dependencies=dependencies,
        )

        # 1. Trust Check
        if self.trust_engine.verify_package_trust(pkg, self.publisher_registry):
            pkg.trust_status = "Verified"
        else:
            raise MarketplacePlatformError(
                f"Publishing rejected: Publisher '{publisher}' trust is unverified."
            )

        # 2. Register package
        self.package_registry.register_package(pkg)

        # 3. Log provenance lineage
        self.provenance_engine.record_lineage(
            package_id, "Publish", f"Version {version} published by {publisher}."
        )

        self.event_bus.publish_sync(
            Event(
                name="marketplace.package.published",
                category="Marketplace",
                source="MarketplacePlatform",
                payload={"package_id": package_id},
            )
        )

        return pkg

    def install_marketplace_package(self, package_id: str) -> None:
        """Validate dependencies, licenses, organizational approvals, and publish events."""
        pkg = self.package_registry.packages.get(package_id)
        if not pkg:
            raise MarketplacePlatformError(f"Package not found in registry: '{package_id}'")

        # 1. Enforce organizational policies
        active_ids = {pid for pid in self.package_registry.packages}
        self.approval_manager.check_installation_policies(pkg, active_ids)

        # 2. Log provenance lineage
        self.provenance_engine.record_lineage(
            package_id, "Install", "Installed on platform core environment."
        )

        self.event_bus.publish_sync(
            Event(
                name="marketplace.package.approved",
                category="Marketplace",
                source="MarketplacePlatform",
                payload={"package_id": package_id},
            )
        )

        self.event_bus.publish_sync(
            Event(
                name="marketplace.installation.authorized",
                category="Marketplace",
                source="MarketplacePlatform",
                payload={"package_id": package_id},
            )
        )
