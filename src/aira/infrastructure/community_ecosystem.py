"""Enterprise Community, Solution Templates & Ecosystem Collaboration Platform for AIRA.

Provides registries, workflow managers, and recognition point trackers.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.community_ecosystem")


class CommunityPlatformError(Exception):
    """Base exception raised for contribution rejections or validation shifts."""

    pass


@dataclass
class CommunityAsset:
    """Community asset details tracking contributor profiles, trust states, and history."""

    asset_id: str
    contributor: str
    organization: str
    # Types: Starter Kits, Workflow Templates, AI Applications
    # Reference Architectures, Plugins, Synthetic Datasets
    asset_type: str
    version: str
    compatibility: str
    trust_status: str = "Unverified"
    review_history: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    manifest_version: int = 1
    # States: Draft, Submission, Review, Validation, Publication, Deprecation, Archive
    status: str = "Draft"


class CommunityRegistry:
    """Tracks contributor profiles profiles and recognition scores points."""

    def __init__(self) -> None:
        self.contributors: dict[str, dict[str, Any]] = {}

    def register_contributor(self, contributor_id: str, organization: str) -> None:
        """Register profile details."""
        self.contributors[contributor_id] = {"organization": organization, "recognition_points": 0}

    def award_points(self, contributor_id: str, points: int) -> None:
        """Increment recognition points count."""
        if contributor_id in self.contributors:
            self.contributors[contributor_id]["recognition_points"] += points


class TemplateRegistry:
    """Houses visual and modular industry templates collections."""

    def __init__(self) -> None:
        self.assets: dict[str, CommunityAsset] = {}

    def register_asset(self, asset: CommunityAsset) -> None:
        """Register template configuration parameters."""
        self.assets[asset.asset_id] = asset


class ContributionWorkflowManager:
    """Governs asset review lifecycle phases transitions."""

    def transition_status(self, asset: CommunityAsset, next_status: str) -> None:
        """Validate state sequences sequence constraints."""
        current = asset.status

        allowed = {
            "Draft": {"Submission"},
            "Submission": {"Review"},
            "Review": {"Validation"},
            "Validation": {"Publication"},
            "Publication": {"Deprecation", "Archive"},
            "Deprecation": {"Archive"},
            "Archive": set(),
        }

        if next_status not in allowed.get(current, set()):
            raise CommunityPlatformError(
                f"Transition failed: Cannot transition asset '{asset.asset_id}' "
                f"from phase '{current}' to '{next_status}'."
            )

        asset.status = next_status


class CommunityEcosystemPlatform:
    """Coordinating manager resolving submissions, reviews, validation, and analytics points."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.community_registry = CommunityRegistry()
        self.template_registry = TemplateRegistry()
        self.workflow_manager = ContributionWorkflowManager()

    def submit_community_asset(
        self,
        asset_id: str,
        contributor: str,
        organization: str,
        asset_type: str,
        version: str,
        compatibility: str,
    ) -> CommunityAsset:
        """Create new community contribution asset model and publish submission events."""
        asset = CommunityAsset(
            asset_id=asset_id,
            contributor=contributor,
            organization=organization,
            asset_type=asset_type,
            version=version,
            compatibility=compatibility,
        )

        # Ensure contributor profile exists in registry
        if contributor not in self.community_registry.contributors:
            self.community_registry.register_contributor(contributor, organization)

        # Transition Draft -> Submission
        self.workflow_manager.transition_status(asset, "Submission")

        self.template_registry.register_asset(asset)

        self.event_bus.publish_sync(
            Event(
                name="community.contribution.submitted",
                category="CommunityEcosystem",
                source="CommunityEcosystemPlatform",
                payload={"asset_id": asset_id, "contributor": contributor},
            )
        )

        return asset

    def run_contribution_review(self, asset_id: str) -> None:
        """Validate compatibility tags, advance state, and publish events."""
        asset = self.template_registry.assets.get(asset_id)
        if not asset:
            raise CommunityPlatformError(f"Asset not found in templates registry: '{asset_id}'")

        # 1. Compatibility Check (reject if compatibility tag references outdated templates)
        if asset.compatibility < "v1.3":
            raise CommunityPlatformError(
                f"Validation failed: Asset '{asset_id}' requires compatibility "
                f"version >= v1.3 but is '{asset.compatibility}'."
            )

        # 2. Lifecycle transitions Submission -> Review -> Validation
        self.workflow_manager.transition_status(asset, "Review")
        self.workflow_manager.transition_status(asset, "Validation")

        asset.review_history.append("Quality Validation Passed")

        self.event_bus.publish_sync(
            Event(
                name="community.review.completed",
                category="CommunityEcosystem",
                source="CommunityEcosystemPlatform",
                payload={"asset_id": asset_id},
            )
        )

    def publish_community_asset(self, asset_id: str) -> None:
        """Promote validation state to published, award recognition points, and publish events."""
        asset = self.template_registry.assets.get(asset_id)
        if not asset:
            raise CommunityPlatformError(f"Asset not found in templates registry: '{asset_id}'")

        # 1. Lifecycle transition Validation -> Publication
        self.workflow_manager.transition_status(asset, "Publication")
        asset.trust_status = "Verified"

        # 2. Award Points & update recognition analytics
        self.community_registry.award_points(asset.contributor, 100)

        self.event_bus.publish_sync(
            Event(
                name="community.asset.published",
                category="CommunityEcosystem",
                source="CommunityEcosystemPlatform",
                payload={"asset_id": asset_id},
            )
        )

        self.event_bus.publish_sync(
            Event(
                name="community.recognition.updated",
                category="CommunityEcosystem",
                source="CommunityEcosystemPlatform",
                payload={
                    "contributor": asset.contributor,
                    "points": self.community_registry.contributors[asset.contributor][
                        "recognition_points"
                    ],
                },
            )
        )

    def generate_starter_kit_scaffold(self, asset_id: str) -> dict[str, Any]:
        """Verify publication status and compile starter kit template configs."""
        asset = self.template_registry.assets.get(asset_id)
        if not asset or asset.status != "Publication":
            raise CommunityPlatformError(
                f"Starter Kit generation failed: Asset '{asset_id}' must be published."
            )

        self.event_bus.publish_sync(
            Event(
                name="community.starterkit.generated",
                category="CommunityEcosystem",
                source="CommunityEcosystemPlatform",
                payload={"asset_id": asset_id},
            )
        )

        return {
            "asset_id": asset_id,
            "scaffolded": True,
            "template_path": f"/templates/community/{asset_id}",
        }
