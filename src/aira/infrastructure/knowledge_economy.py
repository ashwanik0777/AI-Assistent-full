"""Enterprise Shared Knowledge Economy & Attribution Platform.

Provides registries, attribution engines, and recognition engines.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.knowledge_economy")


class KnowledgeEconomyError(Exception):
    """Base exception raised for contribution validation drifts or quality review failures."""

    pass


@dataclass
class KnowledgeContribution:
    """Contribution record specifying evidence, status, quality scores, and reuse metrics."""

    contribution_id: str
    contributor: str
    knowledge_domain: str
    evidence_references: list[str]
    review_status: str  # Submitted, Reviewed, Published, Rejected
    attribution: dict[str, Any]  # original_contributor, reviewers list
    quality_score: float
    reuse_metrics: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)
    version: int = 1


class ContributionRegistry:
    """Records governed knowledge submissions and drafts."""

    def __init__(self) -> None:
        self.contributions: dict[str, KnowledgeContribution] = {}

    def register_contribution(self, contrib: KnowledgeContribution) -> None:
        """Save contribution entry to database."""
        self.contributions[contrib.contribution_id] = contrib


class AttributionEngine:
    """Preserves contributor lineage and versions history."""

    def create_attribution(self, contributor: str, reviewers: list[str]) -> dict[str, Any]:
        """Format attribution lineage map."""
        return {
            "original_contributor": contributor,
            "reviewers": reviewers,
            "lineage_status": "Verified",
        }


class ContributionQualityEngine:
    """Evaluates evidence completeness, accuracy, and reuse ratios."""

    def evaluate_quality(self, evidence: list[str], reuse_frequency: int) -> float:
        """Calculate quality score between 0.0 and 1.0."""
        if not evidence:
            return 0.0
        # Basic scoring metrics
        base_score = 0.5 + (0.1 * len(evidence))
        bonus = min(0.3, reuse_frequency * 0.05)
        return min(1.0, base_score + bonus)


class KnowledgeDependencyGraph:
    """Models reuse graphs, domain dependencies, and contribution networks."""

    def __init__(self) -> None:
        self.dependencies: dict[str, list[str]] = {}

    def register_dependency(self, contribution_id: str, depends_on_id: str) -> None:
        """Link contribution dependency."""
        self.dependencies.setdefault(contribution_id, []).append(depends_on_id)


class RecognitionEngine:
    """Manages contributor expertise profiles and achievements (non-financial)."""

    def __init__(self) -> None:
        self.expertise_profiles: dict[str, dict[str, Any]] = {}

    def reward_contribution(self, contributor: str, quality_score: float) -> None:
        """Update expertise profile achievements and score values."""
        profile = self.expertise_profiles.setdefault(contributor, {"points": 0, "achievements": []})

        # Add points
        added_points = int(quality_score * 100)
        profile["points"] += added_points

        # Add quality achievement
        if quality_score >= 0.85 and "High Quality Contributor" not in profile["achievements"]:
            profile["achievements"].append("High Quality Contributor")


class KnowledgeEconomyPlatform:
    """Coordinating manager resolving contribution reviews, attribution, and recognition."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.contribution_registry = ContributionRegistry()
        self.attribution_engine = AttributionEngine()
        self.quality_engine = ContributionQualityEngine()
        self.dependency_graph = KnowledgeDependencyGraph()
        self.recognition_engine = RecognitionEngine()

    def submit_knowledge_contribution(
        self,
        contrib_id: str,
        contributor: str,
        domain: str,
        evidence: list[str],
        dependencies: list[str],
    ) -> KnowledgeContribution:
        """Validate input metadata, build attribution, record submission, and publish events."""
        if not evidence:
            raise KnowledgeEconomyError(
                f"Submission failed: Contribution '{contrib_id}' lacks sufficient evidence."
            )

        attr = self.attribution_engine.create_attribution(contributor, [])
        qual = self.quality_engine.evaluate_quality(evidence, reuse_frequency=0)

        contrib = KnowledgeContribution(
            contribution_id=contrib_id,
            contributor=contributor,
            knowledge_domain=domain,
            evidence_references=evidence,
            review_status="Submitted",
            attribution=attr,
            quality_score=qual,
            reuse_metrics={"reuse_count": 0},
        )

        self.contribution_registry.register_contribution(contrib)

        # Register dependencies
        for d in dependencies:
            self.dependency_graph.register_dependency(contrib_id, d)
            self.event_bus.publish_sync(
                Event(
                    name="knowledge_economy.dependency.updated",
                    category="KnowledgeEconomy",
                    source="KnowledgeEconomyPlatform",
                    payload={"contribution_id": contrib_id, "dependency": d},
                )
            )

        self.event_bus.publish_sync(
            Event(
                name="knowledge_economy.contribution.submitted",
                category="KnowledgeEconomy",
                source="KnowledgeEconomyPlatform",
                payload={"contribution_id": contrib_id},
            )
        )

        return contrib

    def complete_governance_review(self, contrib_id: str, reviewer_id: str, approved: bool) -> None:
        """Transition review status, assign reviewers to attribution, and publish events."""
        contrib = self.contribution_registry.contributions.get(contrib_id)
        if not contrib:
            raise KnowledgeEconomyError(f"Contribution not found: '{contrib_id}'")

        if not approved:
            contrib.review_status = "Rejected"
            self.event_bus.publish_sync(
                Event(
                    name="knowledge_economy.review.completed",
                    category="KnowledgeEconomy",
                    source="KnowledgeEconomyPlatform",
                    payload={"contribution_id": contrib_id, "approved": False},
                )
            )
            return

        contrib.review_status = "Published"
        contrib.attribution["reviewers"].append(reviewer_id)

        self.event_bus.publish_sync(
            Event(
                name="knowledge_economy.review.completed",
                category="KnowledgeEconomy",
                source="KnowledgeEconomyPlatform",
                payload={"contribution_id": contrib_id, "approved": True},
            )
        )

        self.event_bus.publish_sync(
            Event(
                name="knowledge_economy.published",
                category="KnowledgeEconomy",
                source="KnowledgeEconomyPlatform",
                payload={"contribution_id": contrib_id},
            )
        )

        # Reward contributor
        self.recognition_engine.reward_contribution(contrib.contributor, contrib.quality_score)
        self.event_bus.publish_sync(
            Event(
                name="knowledge_economy.recognition.updated",
                category="KnowledgeEconomy",
                source="KnowledgeEconomyPlatform",
                payload={"contributor": contrib.contributor},
            )
        )
