"""Enterprise Workflow Intelligence, Process Mining & Optimization Platform for AIRA.

Provides process miners, bottleneck detectors, optimizations estimators, and governance managers.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.workflow_intelligence")


class WorkflowIntelligenceError(Exception):
    """Base exception raised for process mining or unsafe optimizations failures."""

    pass


@dataclass
class WorkflowOptimizationProposal:
    """Proposal record encapsulating optimized workflow recommendations details."""

    proposal_id: str
    workflow_id: str
    workflow_version: str
    observed_bottleneck: str
    evidence_references: list[str]
    optimization_suggestion: str
    expected_impact: float  # Percentage time reduction, e.g. 18.0
    risk_assessment: str
    approval_status: str = "Draft"  # Draft, Pending Review, Approved, Published, Rejected, Archived
    priority: str = "Medium"
    metadata: dict[str, Any] = field(default_factory=dict)


class ProcessMiningEngine:
    """Analyzes execution logs lists to calculate average processing durations."""

    def mine_durations(self, step_durations: list[float]) -> float:
        """Calculate and return average execution duration float."""
        if not step_durations:
            return 0.0
        return sum(step_durations) / len(step_durations)


class BottleneckDetector:
    """Detects latency delays and flags steps exceeding processing thresholds."""

    def __init__(self, limit_ms: float = 1000.0) -> None:
        self.limit_ms = limit_ms

    def detect_bottleneck(self, step_name: str, avg_duration_ms: float) -> str | None:
        """Return warning details if average step latency exceeds limit threshold."""
        if avg_duration_ms > self.limit_ms:
            return f"Bottleneck detected: Step '{step_name}' duration is {avg_duration_ms}ms."
        return None


class OptimizationEngine:
    """Formulates workflow recommendations stubs."""

    def recommend_optimization(self, bottleneck: str) -> str:
        """Recommend optimization actions based on detected bottleneck text."""
        if "approval" in bottleneck.lower():
            return "Recommendation: Automate or parallelize approval steps."
        return "Recommendation: Reorder execution tasks sequence."


class ImpactEstimator:
    """Estimates speedup metrics and operational improvements percentages."""

    def estimate_speedup(self, avg_duration_ms: float) -> float:
        """Estimate percentage reduction index (e.g. 18% improvement on threshold latency)."""
        if avg_duration_ms > 2000.0:
            return 25.0
        if avg_duration_ms > 1000.0:
            return 18.0
        return 5.0


class WorkflowGovernanceManager:
    """Manages workflow optimization review workflows and checks transitions."""

    def __init__(self) -> None:
        self.proposals: dict[str, WorkflowOptimizationProposal] = {}
        # Maps workflow_id -> list of versions
        self.version_history: dict[str, list[str]] = {}

    def save_proposal(self, proposal: WorkflowOptimizationProposal) -> None:
        """Catalog proposal."""
        self.proposals[proposal.proposal_id] = proposal

    def update_status(self, proposal_id: str, status: str) -> None:
        """Enforce validation rules on review state transitions."""
        proposal = self.proposals.get(proposal_id)
        if not proposal:
            raise WorkflowIntelligenceError(
                f"Operation failed: Proposal '{proposal_id}' not found."
            )

        allowed = {"Draft", "Pending Review", "Approved", "Published", "Rejected", "Archived"}
        if status not in allowed:
            raise WorkflowIntelligenceError(
                f"Status update failed: Status '{status}' is not supported."
            )

        # Enforce safety rule: Reject unsafe or high-risk optimizations
        if status == "Approved" and "unsafe" in proposal.risk_assessment.lower():
            raise WorkflowIntelligenceError(
                f"Transition to Approved rejected: Optimization contains unsafe risk constraints: "
                f"{proposal.risk_assessment}"
            )

        proposal.approval_status = status


class WorkflowIntelligenceManager:
    """Coordinating manager mining execution logs, detecting bottlenecks, and proposing updates."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.miner = ProcessMiningEngine()
        self.detector = BottleneckDetector()
        self.optimizer = OptimizationEngine()
        self.estimator = ImpactEstimator()
        self.governance = WorkflowGovernanceManager()

    def analyze_and_propose(
        self,
        proposal_id: str,
        workflow_id: str,
        step_name: str,
        durations: list[float],
        evidence_refs: list[str],
        risk: str = "Low",
    ) -> WorkflowOptimizationProposal | None:
        """Analyze histories, compile bottlenecks, estimate impact, and generate proposal."""
        # 1. Mine durations
        avg = self.miner.mine_durations(durations)
        self.event_bus.publish_sync(
            Event(
                name="workflow.analyzed",
                category="WorkflowIntelligence",
                source="WorkflowIntelligenceManager",
                payload={"workflow_id": workflow_id, "avg_duration_ms": avg},
            )
        )

        # 2. Detect bottlenecks
        bottleneck = self.detector.detect_bottleneck(step_name, avg)
        if not bottleneck:
            return None

        self.event_bus.publish_sync(
            Event(
                name="pattern.identified",
                category="WorkflowIntelligence",
                source="WorkflowIntelligenceManager",
                payload={"workflow_id": workflow_id, "pattern": "high_latency"},
            )
        )

        # 3. Recommend optimization & estimate impact
        sugg = self.optimizer.recommend_optimization(bottleneck)
        impact = self.estimator.estimate_speedup(avg)

        self.event_bus.publish_sync(
            Event(
                name="impact.estimated",
                category="WorkflowIntelligence",
                source="WorkflowIntelligenceManager",
                payload={"workflow_id": workflow_id, "estimated_speedup": impact},
            )
        )

        # 4. Propose
        proposal = WorkflowOptimizationProposal(
            proposal_id=proposal_id,
            workflow_id=workflow_id,
            workflow_version="1.0.0",
            observed_bottleneck=bottleneck,
            evidence_references=evidence_refs,
            optimization_suggestion=sugg,
            expected_impact=impact,
            risk_assessment=risk,
        )
        self.governance.save_proposal(proposal)

        self.event_bus.publish_sync(
            Event(
                name="optimization.proposed",
                category="WorkflowIntelligence",
                source="WorkflowIntelligenceManager",
                payload={"proposal_id": proposal_id, "workflow_id": workflow_id},
            )
        )

        return proposal

    def approve_recommendation(self, proposal_id: str) -> None:
        """Approve proposal, transition status, and bump workflow version mappings."""
        proposal = self.governance.proposals.get(proposal_id)
        if not proposal:
            raise WorkflowIntelligenceError(
                f"Operation failed: Proposal '{proposal_id}' not found."
            )

        # Transition status via governance validator
        self.governance.update_status(proposal_id, "Approved")

        # Record version history bump
        wf_id = proposal.workflow_id
        current_versions = self.governance.version_history.setdefault(wf_id, ["1.0.0"])
        # Simple version bump
        parts = current_versions[-1].split(".")
        new_ver = f"{parts[0]}.{int(parts[1]) + 1}.0"
        current_versions.append(new_ver)
        proposal.workflow_version = new_ver

        self.event_bus.publish_sync(
            Event(
                name="recommendation.approved",
                category="WorkflowIntelligence",
                source="WorkflowIntelligenceManager",
                payload={"proposal_id": proposal_id, "new_version": new_ver},
            )
        )

        self.event_bus.publish_sync(
            Event(
                name="workflow_version.created",
                category="WorkflowIntelligence",
                source="WorkflowIntelligenceManager",
                payload={"workflow_id": wf_id, "version": new_ver},
            )
        )
