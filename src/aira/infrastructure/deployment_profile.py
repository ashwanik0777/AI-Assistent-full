"""Enterprise Deployment Profiles & Environment Orchestration Platform for AIRA.

Provides profile manifests, configuration validators, feature flags managers, and drift detectors.
"""

import time
from dataclasses import dataclass, field
from typing import Any, ClassVar

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.deployment_profile")


class DeploymentProfileError(Exception):
    """Base exception raised for profile validation, environment conflicts, or snapshot failures."""

    pass


@dataclass
class DeploymentProfileManifest:
    """Configuration mapping enabling plugins, knowledge packs, and environment feature flags."""

    profile_id: str
    environment: str  # Development, Testing, Staging, Production, Enterprise, Offline
    enabled_extensions: list[str]
    enabled_knowledge_packs: list[str]
    feature_flags: dict[str, str] = field(default_factory=dict)
    compatibility: str = ">=0.9.0"
    metadata: dict[str, Any] = field(default_factory=dict)
    version: str = "1.0.0"


@dataclass
class DeploymentSnapshot:
    """Structural snapshot capturing enabled extensions and configuration states."""

    snapshot_id: str
    timestamp: float
    enabled_extensions: list[str]
    enabled_knowledge_packs: list[str]
    feature_flags: dict[str, str]


class ConfigurationValidator:
    """Enforces profile metadata consistency constraints checks."""

    def __init__(self, platform_version: str = "0.9.0") -> None:
        self.platform_version = platform_version

    def validate_profile(self, profile: DeploymentProfileManifest) -> None:
        """Check compatibility matrix and fields completeness."""
        # 1. Compatibility check
        req = profile.compatibility.replace(">=", "").strip()
        p_parts = [int(x) for x in self.platform_version.split(".")]
        r_parts = [int(x) for x in req.split(".")]
        if p_parts < r_parts:
            raise DeploymentProfileError(
                f"Validation failed: Incompatible version. Platform: '{self.platform_version}' "
                f"vs Profile: '{profile.compatibility}'."
            )


class EnvironmentManager:
    """Manages active environment modes bounds checks."""

    ALLOWED_ENVIRONMENTS: ClassVar[set[str]] = {
        "Development",
        "Testing",
        "Staging",
        "Production",
        "Enterprise",
        "Offline",
    }

    def validate_environment(self, env: str) -> None:
        """Raise error if the targeted environment name is not supported."""
        if env not in self.ALLOWED_ENVIRONMENTS:
            raise DeploymentProfileError(
                f"Environment validation failed: Mode '{env}' is not supported."
            )


class FeatureFlagManager:
    """Reads profile-specific feature flags settings."""

    def __init__(self) -> None:
        self.flags: dict[str, str] = {}

    def load_flags(self, flags: dict[str, str]) -> None:
        """Populate active flags list."""
        self.flags = flags.copy()

    def is_feature_enabled(self, feature_key: str) -> bool:
        """Return True feature key maps to enabled/true."""
        val = self.flags.get(feature_key, "Disabled")
        return val in ("Enabled", "true")


class DriftDetector:
    """Scans and audits current active platform compositions vs profile requirements."""

    def detect_drift(
        self,
        profile: DeploymentProfileManifest,
        active_extensions: list[str],
        active_knowledge_packs: list[str],
    ) -> list[str]:
        """Identify missing items, returning detailed configuration drifts descriptions."""
        drift_warnings = []
        # Check extensions
        for ext in profile.enabled_extensions:
            if ext not in active_extensions:
                drift_warnings.append(
                    f"Drift detected: Extension '{ext}' is enabled in profile but inactive."
                )
        # Check knowledge packs
        for kp in profile.enabled_knowledge_packs:
            if kp not in active_knowledge_packs:
                drift_warnings.append(
                    f"Drift detected: Knowledge Pack '{kp}' is enabled in profile but inactive."
                )
        return drift_warnings


class DeploymentSnapshotManager:
    """Creates configuration checkpoint entries to roll back drift changes."""

    def __init__(self) -> None:
        self.snapshots: dict[str, DeploymentSnapshot] = {}

    def create_snapshot(
        self,
        snapshot_id: str,
        enabled_extensions: list[str],
        enabled_knowledge_packs: list[str],
        feature_flags: dict[str, str],
    ) -> DeploymentSnapshot:
        """Save configuration snapshots record."""
        snap = DeploymentSnapshot(
            snapshot_id=snapshot_id,
            timestamp=time.time(),
            enabled_extensions=enabled_extensions.copy(),
            enabled_knowledge_packs=enabled_knowledge_packs.copy(),
            feature_flags=feature_flags.copy(),
        )
        self.snapshots[snapshot_id] = snap
        return snap

    def restore_snapshot(self, snapshot_id: str) -> DeploymentSnapshot:
        """Fetch targeted snap records."""
        snap = self.snapshots.get(snapshot_id)
        if not snap:
            raise DeploymentProfileError(
                f"Rollback failed: Snapshot '{snapshot_id}' does not exist."
            )
        return snap


class DeploymentManager:
    """Coordinating manager verifying profiles, detecting drift audits, and rolling back configs."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.validator = ConfigurationValidator()
        self.environment_manager = EnvironmentManager()
        self.flag_manager = FeatureFlagManager()
        self.drift_detector = DriftDetector()
        self.snapshot_manager = DeploymentSnapshotManager()

        self.active_profile: DeploymentProfileManifest | None = None
        self.active_extensions: list[str] = []
        self.active_knowledge_packs: list[str] = []

    def load_deployment_profile(self, profile: DeploymentProfileManifest) -> None:
        """Validate, verify environment context limits, load configurations, and publish events."""
        # 1. Validate
        self.validator.validate_profile(profile)
        self.environment_manager.validate_environment(profile.environment)

        self.active_profile = profile
        self.flag_manager.load_flags(profile.feature_flags)

        self.event_bus.publish_sync(
            Event(
                name="profile.loaded",
                category="Deployment",
                source="DeploymentManager",
                payload={"profile_id": profile.profile_id, "environment": profile.environment},
            )
        )

        self.event_bus.publish_sync(
            Event(
                name="configuration.validated",
                category="Deployment",
                source="DeploymentManager",
                payload={"profile_id": profile.profile_id},
            )
        )

    def trigger_deployment(self) -> None:
        """Trigger composition updates mappings."""
        if not self.active_profile:
            raise DeploymentProfileError("Deployment failed: No profile has been loaded.")

        self.event_bus.publish_sync(
            Event(
                name="deployment.started",
                category="Deployment",
                source="DeploymentManager",
                payload={"profile_id": self.active_profile.profile_id},
            )
        )

        # Update active mappings simulation
        self.active_extensions = self.active_profile.enabled_extensions.copy()
        self.active_knowledge_packs = self.active_profile.enabled_knowledge_packs.copy()

        self.event_bus.publish_sync(
            Event(
                name="deployment.completed",
                category="Deployment",
                source="DeploymentManager",
                payload={"profile_id": self.active_profile.profile_id},
            )
        )

    def audit_configuration_drift(self) -> list[str]:
        """Scan current active items vs profile to report variations."""
        if not self.active_profile:
            raise DeploymentProfileError("Audit failed: No profile has been loaded.")

        drifts = self.drift_detector.detect_drift(
            self.active_profile, self.active_extensions, self.active_knowledge_packs
        )
        if drifts:
            self.event_bus.publish_sync(
                Event(
                    name="drift.detected",
                    category="Deployment",
                    source="DeploymentManager",
                    payload={"drifts_count": len(drifts)},
                )
            )
        return drifts

    def create_deployment_snapshot(self, snapshot_id: str) -> None:
        """Backup active configurations profile settings."""
        self.snapshot_manager.create_snapshot(
            snapshot_id,
            self.active_extensions,
            self.active_knowledge_packs,
            self.flag_manager.flags,
        )
        self.event_bus.publish_sync(
            Event(
                name="snapshot.created",
                category="Deployment",
                source="DeploymentManager",
                payload={"snapshot_id": snapshot_id},
            )
        )

    def rollback_deployment(self, snapshot_id: str) -> None:
        """Restore active settings database indexes from target snapshot."""
        snap = self.snapshot_manager.restore_snapshot(snapshot_id)
        self.active_extensions = snap.enabled_extensions.copy()
        self.active_knowledge_packs = snap.enabled_knowledge_packs.copy()
        self.flag_manager.load_flags(snap.feature_flags)

        self.event_bus.publish_sync(
            Event(
                name="rollback.completed",
                category="Deployment",
                source="DeploymentManager",
                payload={"snapshot_id": snapshot_id},
            )
        )
