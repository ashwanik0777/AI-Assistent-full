"""Enterprise Learning Governance, Explainability, AI Accountability Platform.

Provides explainability engines, compliance reporters, and rollback planners.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.learning_governance")


class LearningGovernanceError(Exception):
    """Base exception raised for missing evidence, rollback, or approval governance failures."""

    pass


@dataclass
class LearningDecisionRecord:
    """Record summarizing governance decisions, linked evidence chains, and recovery plans."""

    decision_id: str
    proposal_reference: str
    evidence_references: list[str]
    reasoning_summary: str
    reviewer_assignments: list[str]
    approval_status: str = "Draft"  # Draft, Review, Approved, Published, Archived
    expected_impact: str = ""
    rollback_plan: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    version: int = 1


class ExplainabilityEngine:
    """Generates human-readable descriptions and rationales for recommendations."""

    def explain(self, record: LearningDecisionRecord) -> str:
        """Formulate a human-readable explanation summary."""
        return (
            f"Decision explanation: Proposal '{record.proposal_reference}' was evaluated. "
            f"Expected impact is: '{record.expected_impact}'. "
            f"Rationale summary: '{record.reasoning_summary}'."
        )


class DecisionProvenanceTracker:
    """Tracks observations origins, chain mapping, and version history."""

    def trace_lineage(self, record: LearningDecisionRecord) -> list[str]:
        """Compile complete lineage chain list."""
        return [f"Origin -> Evidence [{r}]" for r in record.evidence_references]


class AccountabilityManager:
    """Registers reviewer assignments and ownership records."""

    def assign_reviewers(self, record: LearningDecisionRecord, reviewers: list[str]) -> None:
        """Assign list of reviewers to the record."""
        record.reviewer_assignments = reviewers


class ComplianceReporter:
    """Generates compliance audits reports."""

    def generate_report(self, record: LearningDecisionRecord) -> dict[str, Any]:
        """Synthesize audit details report."""
        return {
            "decision_id": record.decision_id,
            "status": record.approval_status,
            "version": record.version,
            "traceability_count": len(record.evidence_references),
        }


class RollbackPlanner:
    """Designs recovery strategies and targets previous version mappings."""

    def create_plan(self, previous_version: str, checklist: list[str]) -> dict[str, Any]:
        """Construct standard rollback map."""
        return {
            "previous_version": previous_version,
            "recovery_checklist": checklist,
            "validation_status": "Ready",
        }


class LearningGovernanceManager:
    """Coordinating manager ensuring decision records validity and dispatching events."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.explainability_engine = ExplainabilityEngine()
        self.provenance_tracker = DecisionProvenanceTracker()
        self.accountability_manager = AccountabilityManager()
        self.compliance_reporter = ComplianceReporter()
        self.rollback_planner = RollbackPlanner()

        self.decisions: dict[str, LearningDecisionRecord] = {}

    def propose_governance_decision(
        self,
        decision_id: str,
        proposal_ref: str,
        evidence_refs: list[str],
        reasoning: str,
        impact: str,
    ) -> LearningDecisionRecord:
        """Create draft proposal and validate integrity rules."""
        # Enforce rule: cannot govern without evidence references (validation gate)
        if not evidence_refs:
            raise LearningGovernanceError(
                f"Governance failed: Decision '{decision_id}' has empty evidence references."
            )

        record = LearningDecisionRecord(
            decision_id=decision_id,
            proposal_reference=proposal_ref,
            evidence_references=evidence_refs,
            reasoning_summary=reasoning,
            reviewer_assignments=[],
            expected_impact=impact,
        )

        self.decisions[decision_id] = record
        return record

    def assign_reviewers_and_explain(self, decision_id: str, reviewers: list[str]) -> str:
        """Assign owners and publish explained events."""
        record = self.decisions.get(decision_id)
        if not record:
            raise LearningGovernanceError(f"Operation failed: Record '{decision_id}' not found.")

        self.accountability_manager.assign_reviewers(record, reviewers)
        explanation = self.explainability_engine.explain(record)

        self.event_bus.publish_sync(
            Event(
                name="decision.explained",
                category="LearningGovernance",
                source="LearningGovernanceManager",
                payload={"decision_id": decision_id, "explanation": explanation},
            )
        )

        return explanation

    def approve_decision(self, decision_id: str, previous_version: str) -> None:
        """Transition state to Approved, bind rollback strategy, and publish logs."""
        record = self.decisions.get(decision_id)
        if not record:
            raise LearningGovernanceError(f"Operation failed: Record '{decision_id}' not found.")

        # Bind rollback strategy
        plan = self.rollback_planner.create_plan(
            previous_version, checklist=["revert config files", "restart kernel runtime"]
        )
        record.rollback_plan = plan
        record.approval_status = "Approved"

        # Events
        self.event_bus.publish_sync(
            Event(
                name="rollback.created",
                category="LearningGovernance",
                source="LearningGovernanceManager",
                payload={"decision_id": decision_id, "rollback_version": previous_version},
            )
        )

        self.event_bus.publish_sync(
            Event(
                name="approval.recorded",
                category="LearningGovernance",
                source="LearningGovernanceManager",
                payload={"decision_id": decision_id},
            )
        )

    def trace_and_publish_compliance(self, decision_id: str) -> dict[str, Any]:
        """Compile compliance report, trace history lineage, and publish audit event."""
        record = self.decisions.get(decision_id)
        if not record:
            raise LearningGovernanceError(f"Operation failed: Record '{decision_id}' not found.")

        lineage = self.provenance_tracker.trace_lineage(record)
        report = self.compliance_reporter.generate_report(record)

        self.event_bus.publish_sync(
            Event(
                name="provenance.updated",
                category="LearningGovernance",
                source="LearningGovernanceManager",
                payload={"decision_id": decision_id, "lineage": lineage},
            )
        )

        self.event_bus.publish_sync(
            Event(
                name="compliance.generated",
                category="LearningGovernance",
                source="LearningGovernanceManager",
                payload=report,
            )
        )

        return report
