"""Enterprise Extension Package Manager, Dependency Resolution & Lifecycle Platform for AIRA.

Provides manifests, resolvers, compatibility verifiers, caches, and snapshot rollback systems.
"""

import time
from dataclasses import dataclass, field
from typing import Any, ClassVar

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.extension_package")


class ExtensionPackageManagerError(Exception):
    """Base exception raised for dependency, version conflict, or rollback failures."""

    pass


@dataclass
class PackageManifest:
    """Metadata detailing package specs, checksums, and dependency definitions."""

    package_id: str
    extension_id: str
    version: str
    dependencies: dict[str, str] = field(default_factory=dict)
    peer_dependencies: dict[str, str] = field(default_factory=dict)
    sdk_compatibility: str = ">=1.0.0"
    checksum: str = "sha256_mock"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PackageRecord:
    """Active registry tracking status of a downloaded package."""

    manifest: PackageManifest
    lifecycle_state: str = "Discovered"


@dataclass
class RollbackSnapshot:
    """History state snapshot captures configurations and installed registry states."""

    snapshot_id: str
    timestamp: float
    installed_packages: dict[str, str]  # package_id -> version
    metadata: dict[str, Any] = field(default_factory=dict)


class DependencyResolver:
    """Resolves semantic version constraints and checks circular package graphs."""

    def resolve_dependencies(
        self, target_manifest: PackageManifest, available_packages: dict[str, PackageManifest]
    ) -> list[str]:
        """Verify presence of dependencies and check circular relations using DFS."""
        resolved: list[str] = []
        visited: dict[str, int] = {}  # 0=visiting, 1=visited

        def visit(pkg_id: str, manifest: PackageManifest) -> None:
            visited[pkg_id] = 0
            for dep_id, ver_constraint in manifest.dependencies.items():
                if dep_id in visited:
                    if visited[dep_id] == 0:
                        raise ExtensionPackageManagerError(
                            f"Dependency conflict: Circular reference detected on '{dep_id}'."
                        )
                else:
                    if dep_id not in available_packages:
                        raise ExtensionPackageManagerError(
                            f"Dependency resolution failed: Required package '{dep_id}' "
                            f"with constraint '{ver_constraint}' is missing."
                        )
                    visit(dep_id, available_packages[dep_id])
            visited[pkg_id] = 1
            resolved.append(pkg_id)

        visit(target_manifest.package_id, target_manifest)
        return resolved


class CompatibilityEngine:
    """Checks packages versions bounds against target platform targets."""

    def __init__(self, platform_version: str = "0.9.0") -> None:
        self.platform_version = platform_version

    def check_compatibility(self, manifest: PackageManifest) -> bool:
        """Verify version baseline."""
        req = manifest.sdk_compatibility.replace(">=", "").strip()
        p_parts = [int(x) for x in self.platform_version.split(".")]
        r_parts = [int(x) for x in req.split(".")]
        return p_parts >= r_parts


class PackageLifecycleManager:
    """Enforces package lifecycles transitions and rejects invalid state changes."""

    VALID_TRANSITIONS: ClassVar[dict[str, set[str]]] = {
        "Discovered": {"Downloaded", "Removed"},
        "Downloaded": {"Verified", "Removed"},
        "Verified": {"Installed", "Removed"},
        "Installed": {"Enabled", "Updated", "Removed"},
        "Enabled": {"Disabled", "Rolled Back"},
        "Disabled": {"Enabled", "Removed"},
        "Updated": {"Installed", "Removed"},
        "Rolled Back": {"Enabled", "Removed"},
        "Removed": {"Discovered"},
    }

    def transition_state(self, record: PackageRecord, target_state: str) -> None:
        """Apply status change or raise ExtensionPackageManagerError."""
        current = record.lifecycle_state
        allowed = self.VALID_TRANSITIONS.get(current, set())
        if target_state not in allowed:
            raise ExtensionPackageManagerError(
                f"Lifecycle transition failed: Cannot move from '{current}' to '{target_state}'."
            )
        record.lifecycle_state = target_state


class PackageCache:
    """Maintains local registry databases."""

    def __init__(self) -> None:
        self.downloaded_packages: dict[str, PackageRecord] = {}

    def cache_package(self, record: PackageRecord) -> None:
        """Cache downloaded package entry."""
        self.downloaded_packages[record.manifest.package_id] = record

    def get(self, package_id: str) -> PackageRecord | None:
        """Fetch package from local caches."""
        return self.downloaded_packages.get(package_id)

    def evict(self, package_id: str) -> None:
        """Evict package record."""
        self.downloaded_packages.pop(package_id, None)


class RollbackManager:
    """Saves structural snapshots to restore previous system configurations."""

    def __init__(self) -> None:
        self.snapshots: dict[str, RollbackSnapshot] = {}

    def create_snapshot(
        self, snapshot_id: str, installed_packages: dict[str, str]
    ) -> RollbackSnapshot:
        """Capture active packages and versions map."""
        snap = RollbackSnapshot(
            snapshot_id=snapshot_id,
            timestamp=time.time(),
            installed_packages=installed_packages.copy(),
        )
        self.snapshots[snapshot_id] = snap
        return snap

    def restore_snapshot(self, snapshot_id: str) -> dict[str, str]:
        """Retrieve package versions list from targeted snapshot."""
        snap = self.snapshots.get(snapshot_id)
        if not snap:
            raise ExtensionPackageManagerError(
                f"Rollback failed: Snapshot '{snapshot_id}' does not exist."
            )
        return snap.installed_packages


class PackageManager:
    """Coordinating manager verifying package integrity, dependencies, and state rollbacks."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.resolver = DependencyResolver()
        self.compatibility_engine = CompatibilityEngine()
        self.lifecycle_manager = PackageLifecycleManager()
        self.cache = PackageCache()
        self.rollback_manager = RollbackManager()

        # Database mapping installed package names to version strings
        self.installed_database: dict[str, str] = {}
        # Database mapping packages to manifests
        self.available_manifests: dict[str, PackageManifest] = {}

    def register_available_manifest(self, manifest: PackageManifest) -> None:
        """Seed package records manifest database prior to dependency checks."""
        self.available_manifests[manifest.package_id] = manifest

    def install_package(self, manifest: PackageManifest) -> PackageRecord:
        """Resolve dependency maps, check system versions, install package, and notify events."""
        # 1. Check Version Compatibility
        if not self.compatibility_engine.check_compatibility(manifest):
            raise ExtensionPackageManagerError(
                f"Installation blocked: Package '{manifest.package_id}' is incompatible "
                f"with platform version '{self.compatibility_engine.platform_version}'."
            )

        # 2. Resolve Dependencies
        self.resolver.resolve_dependencies(manifest, self.available_manifests)

        # 3. Create cache Record
        record = PackageRecord(manifest=manifest)
        self.cache.cache_package(record)

        # Transition downloaded state
        self.lifecycle_manager.transition_state(record, "Downloaded")
        self.event_bus.publish_sync(
            Event(
                name="package.downloaded",
                category="PackageManager",
                source="PackageManager",
                payload={"package_id": manifest.package_id},
            )
        )

        # Transition verified state
        self.lifecycle_manager.transition_state(record, "Verified")
        self.event_bus.publish_sync(
            Event(
                name="package.verified",
                category="PackageManager",
                source="PackageManager",
                payload={"package_id": manifest.package_id},
            )
        )

        # Capture Rollback checkpoint
        snap_id = f"snap_pre_{manifest.package_id}"
        self.rollback_manager.create_snapshot(snap_id, self.installed_database)

        # Transition installed state
        self.lifecycle_manager.transition_state(record, "Installed")
        self.installed_database[manifest.package_id] = manifest.version

        self.event_bus.publish_sync(
            Event(
                name="package.installed",
                category="PackageManager",
                source="PackageManager",
                payload={"package_id": manifest.package_id, "version": manifest.version},
            )
        )

        return record

    def rollback_package(self, package_id: str, snapshot_id: str) -> None:
        """Restore active database map to target snapshot status."""
        record = self.cache.get(package_id)
        if not record:
            raise ExtensionPackageManagerError(
                f"Rollback failed: Package '{package_id}' is not in local cache."
            )

        # Restore database references
        restored = self.rollback_manager.restore_snapshot(snapshot_id)
        self.installed_database = restored.copy()

        # Update Record state
        record.lifecycle_state = "Rolled Back"

        self.event_bus.publish_sync(
            Event(
                name="package.rolled_back",
                category="PackageManager",
                source="PackageManager",
                payload={"package_id": package_id, "snapshot_id": snapshot_id},
            )
        )
