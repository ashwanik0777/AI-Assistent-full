"""Enterprise Organizational Intelligence, Best Practices & Collective Learning Platform for AIRA.

Provides insight engines, best practice builders, playbooks lifecycle trackers, and metrics engines.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.organizational_intelligence")


class OrganizationalIntelligenceError(Exception):
    """Base exception raised for best practice generation or playbooks transitions failures."""

    pass


@dataclass
class BestPracticeRecord:
    """Record representing a governance-approved best practice playbook template."""

    practice_id: str
    title: str
    organization_scope: str  # e.g. Team, Department, Organization Wide
    applicable_teams: list[str]
    evidence_references: list[str]
    approval_status: str = "Draft"  # Draft, Review, Approved, Published, Deprecated, Archived
    owner: str = "admin"
    version: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)


class TeamInsightEngine:
    """Mines team execution outcomes to identify successful reusable patterns."""

    def mine_reusable_pattern(self, success_rates: dict[str, float]) -> str | None:
        """Analyze team outcomes success rates and recommend if a playbook should be generated."""
        for team, rate in success_rates.items():
            if rate > 0.9:
                return (
                    f"Pattern identified: Team '{team}' "
                    f"has >90% success rate on workflow execution."
                )
        return None


class BestPracticeGenerator:
    """Formulates new best practice template records from validated insight text."""

    def generate_practice(
        self, practice_id: str, title: str, scope: str, teams: list[str], refs: list[str]
    ) -> BestPracticeRecord:
        """Create new BestPracticeRecord in Draft state."""
        return BestPracticeRecord(
            practice_id=practice_id,
            title=title,
            organization_scope=scope,
            applicable_teams=teams,
            evidence_references=refs,
        )


class PlaybookManager:
    """Enforces playbooks lifecycle transitions and validates catalog integrity rules."""

    def __init__(self) -> None:
        self.catalog: dict[str, BestPracticeRecord] = {}

    def save_record(self, record: BestPracticeRecord) -> None:
        """Catalog playbook."""
        self.catalog[record.practice_id] = record

    def transition_state(self, practice_id: str, to_state: str) -> None:
        """Update record status check transitions policies."""
        rec = self.catalog.get(practice_id)
        if not rec:
            raise OrganizationalIntelligenceError(
                f"Transition failed: Best practice '{practice_id}' not found."
            )

        allowed = {"Draft", "Review", "Approved", "Published", "Deprecated", "Archived"}
        if to_state not in allowed:
            raise OrganizationalIntelligenceError(
                f"Transition failed: Status state '{to_state}' is not supported."
            )

        # Enforce rule: cannot approve without evidence references (validation gate)
        if to_state == "Approved" and not rec.evidence_references:
            raise OrganizationalIntelligenceError(
                f"Approval rejected: Best practice '{practice_id}' has no evidence references."
            )

        rec.approval_status = to_state


class OrganizationRecommendationEngine:
    """Compiles recommendations suggestions lists for corporate deployment profiles."""

    def recommend_profile_update(self, pattern: str) -> str:
        """Formulate recommendation mapping based on mined pattern details."""
        if "success" in pattern.lower():
            return "Recommendation: Adopt team workflow as organization template standards."
        return "Recommendation: Audit deployment profile rules."


class CollectiveMetricsEngine:
    """Calculates organizational adoption success and reuse rates aggregates."""

    def compute_metrics(self, total_teams: int, adopting_teams: int) -> dict[str, Any]:
        """Compute metrics ratio details dictionary."""
        rate = (adopting_teams / total_teams) * 100.0 if total_teams > 0 else 0.0
        return {
            "adoption_rate": rate,
            "participation_count": adopting_teams,
            "reuse_score": rate * 0.8,
        }


class OrganizationalIntelligenceManager:
    """Coordinating manager mining insights, updating catalogs, and publishing events."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.insight_engine = TeamInsightEngine()
        self.generator = BestPracticeGenerator()
        self.playbook_manager = PlaybookManager()
        self.recommendation_engine = OrganizationRecommendationEngine()
        self.metrics_engine = CollectiveMetricsEngine()

    def process_team_outcomes(
        self,
        practice_id: str,
        title: str,
        scope: str,
        teams: list[str],
        success_rates: dict[str, float],
        evidence_refs: list[str],
    ) -> BestPracticeRecord | None:
        """Mine outcomes, generate draft best practice, and catalog."""
        pattern = self.insight_engine.mine_reusable_pattern(success_rates)
        if not pattern:
            return None

        # Generate practice playbook
        record = self.generator.generate_practice(practice_id, title, scope, teams, evidence_refs)
        self.playbook_manager.save_record(record)

        self.event_bus.publish_sync(
            Event(
                name="best_practice.created",
                category="OrganizationalIntelligence",
                source="OrganizationalIntelligenceManager",
                payload={"practice_id": practice_id, "title": title},
            )
        )

        return record

    def promote_playbook(self, practice_id: str, state: str) -> None:
        """Transition playbook status and publish approval/update events."""
        self.playbook_manager.transition_state(practice_id, state)

        if state == "Approved":
            self.event_bus.publish_sync(
                Event(
                    name="playbook.approved",
                    category="OrganizationalIntelligence",
                    source="OrganizationalIntelligenceManager",
                    payload={"practice_id": practice_id},
                )
            )

        self.event_bus.publish_sync(
            Event(
                name="catalog.updated",
                category="OrganizationalIntelligence",
                source="OrganizationalIntelligenceManager",
                payload={"practice_id": practice_id, "status": state},
            )
        )

    def publish_recommendation(self, pattern: str) -> str:
        """Formulate recommendation and publish recommendation updates events."""
        rec = self.recommendation_engine.recommend_profile_update(pattern)

        self.event_bus.publish_sync(
            Event(
                name="recommendation.published",
                category="OrganizationalIntelligence",
                source="OrganizationalIntelligenceManager",
                payload={"recommendation_msg": rec},
            )
        )

        return rec

    def compute_collective_metrics(self, total: int, adopting: int) -> dict[str, Any]:
        """Compute metrics and publish logs statistics events."""
        metrics = self.metrics_engine.compute_metrics(total, adopting)

        self.event_bus.publish_sync(
            Event(
                name="metrics.generated",
                category="OrganizationalIntelligence",
                source="OrganizationalIntelligenceManager",
                payload=metrics,
            )
        )

        return metrics
