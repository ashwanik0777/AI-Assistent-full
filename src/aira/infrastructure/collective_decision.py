"""Enterprise Collective Decision Intelligence & Consensus Platform.

Provides proposal managers, consensus engines, and escalators.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.collective_decision")


class DecisionIntelligenceError(Exception):
    """Base exception raised for consensus failures or validation drifts."""

    pass


@dataclass
class DecisionProposal:
    """Proposal defining alternative choices, participants, consensus results, and statuses."""

    proposal_id: str
    objective: str
    participants: list[str]
    alternatives: list[str]
    consensus_result: dict[str, Any]
    minority_opinions: list[str]
    decision_rationale: str
    evidence_references: list[str]
    status: str = "Submitted"  # Submitted, ConsensusReached, Escalated, Approved
    metadata: dict[str, Any] = field(default_factory=dict)
    version: int = 1


class ProposalManager:
    """Submits and validates proposals structure alignment rules."""

    def __init__(self) -> None:
        self.proposals: dict[str, DecisionProposal] = {}

    def register_proposal(self, proposal: DecisionProposal) -> None:
        """Register proposal to local state."""
        if not proposal.objective:
            raise DecisionIntelligenceError(
                "Proposal validation failed: Objective must be defined."
            )
        self.proposals[proposal.proposal_id] = proposal


class ConsensusEngine:
    """Evaluates Unanimous, Majority, or Weighted Voting consensus strategies outcomes."""

    def calculate_majority_consensus(
        self, votes: dict[str, str], alternatives: list[str]
    ) -> tuple[str, float]:
        """Tally votes and return winner and support ratio."""
        if not votes:
            raise DecisionIntelligenceError("Consensus failed: No votes recorded.")

        tallies: dict[str, int] = {}
        for choice in votes.values():
            if choice not in alternatives:
                raise DecisionIntelligenceError(f"Invalid vote choice: '{choice}'")
            tallies[choice] = tallies.get(choice, 0) + 1

        winner = max(tallies, key=tallies.get)  # type: ignore
        total_votes = len(votes)
        support_ratio = float(tallies[winner]) / float(total_votes)
        return winner, support_ratio


class ConflictResolutionEngine:
    """Resolves resource or capability conflicts through policies mediation."""

    def attempt_resolution(self, proposal: DecisionProposal, conflicting_agents: list[str]) -> bool:
        """Mediate conflict and return resolve outcomes status."""
        # Simple policy: resolution succeeds if we can align on an alternative
        if len(proposal.alternatives) > 1:
            proposal.decision_rationale = (
                f"Conflict mediated: selected alternative '{proposal.alternatives[0]}' "
                f"between conflicting agents {conflicting_agents}."
            )
            return True
        return False


class DecisionProvenanceManager:
    """Tracks votes details and rationale histories archives for auditability."""

    def __init__(self) -> None:
        self.archives: dict[str, dict[str, Any]] = {}

    def archive_decision(self, proposal: DecisionProposal, votes: dict[str, str]) -> None:
        """Store permanent provenance traces summary."""
        self.archives[proposal.proposal_id] = {
            "proposal_id": proposal.proposal_id,
            "objective": proposal.objective,
            "votes": dict(votes),
            "rationale": proposal.decision_rationale,
            "status": proposal.status,
        }


class EscalationManager:
    """Routes unresolved consensus failures to committee governance reviews."""

    def escalate_proposal(self, proposal: DecisionProposal, reason: str) -> None:
        """Promote proposal state to Escalated and record reason details."""
        proposal.status = "Escalated"
        proposal.metadata["escalation_reason"] = reason


class DecisionIntelligencePlatform:
    """Coordinating manager resolving proposals, consensus checks, and governance escalations."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.proposal_manager = ProposalManager()
        self.consensus_engine = ConsensusEngine()
        self.conflict_resolver = ConflictResolutionEngine()
        self.provenance_manager = DecisionProvenanceManager()
        self.escalation_manager = EscalationManager()

    def submit_proposal(
        self, proposal_id: str, objective: str, participants: list[str], alternatives: list[str]
    ) -> DecisionProposal:
        """Register proposal record and publish events."""
        proposal = DecisionProposal(
            proposal_id=proposal_id,
            objective=objective,
            participants=participants,
            alternatives=alternatives,
            consensus_result={},
            minority_opinions=[],
            decision_rationale="",
            evidence_references=[],
        )

        self.proposal_manager.register_proposal(proposal)

        self.event_bus.publish_sync(
            Event(
                name="decision.proposal.submitted",
                category="DecisionIntelligence",
                source="DecisionIntelligencePlatform",
                payload={"proposal_id": proposal_id},
            )
        )

        return proposal

    def evaluate_votes_consensus(
        self, proposal_id: str, votes: dict[str, str], consensus_threshold: float = 0.5
    ) -> None:
        """Compute consensus scores, check threshold, and handle escalations if needed."""
        proposal = self.proposal_manager.proposals.get(proposal_id)
        if not proposal:
            raise DecisionIntelligenceError(f"Proposal not found: '{proposal_id}'")

        winner, ratio = self.consensus_engine.calculate_majority_consensus(
            votes, proposal.alternatives
        )

        if ratio >= consensus_threshold:
            proposal.status = "ConsensusReached"
            proposal.consensus_result = {"winner": winner, "support_ratio": ratio}
            proposal.decision_rationale = (
                f"Consensus reached on option '{winner}' with support {ratio * 100:.1f}%."
            )

            self.event_bus.publish_sync(
                Event(
                    name="decision.consensus.reached",
                    category="DecisionIntelligence",
                    source="DecisionIntelligencePlatform",
                    payload={"proposal_id": proposal_id, "winner": winner},
                )
            )
        else:
            # Trigger Conflict
            self.event_bus.publish_sync(
                Event(
                    name="decision.conflict.detected",
                    category="DecisionIntelligence",
                    source="DecisionIntelligencePlatform",
                    payload={"proposal_id": proposal_id},
                )
            )

            # Attempt conflict resolution
            resolved = self.conflict_resolver.attempt_resolution(proposal, proposal.participants)
            if resolved:
                proposal.status = "ConsensusReached"
                self.event_bus.publish_sync(
                    Event(
                        name="decision.consensus.reached",
                        category="DecisionIntelligence",
                        source="DecisionIntelligencePlatform",
                        payload={"proposal_id": proposal_id, "mediated": True},
                    )
                )
            else:
                # Trigger Escalation
                self.escalation_manager.escalate_proposal(
                    proposal,
                    reason=(
                        f"Consensus ratio {ratio:.2f} is below threshold {consensus_threshold:.2f}."
                    ),
                )

                self.event_bus.publish_sync(
                    Event(
                        name="decision.escalation.triggered",
                        category="DecisionIntelligence",
                        source="DecisionIntelligencePlatform",
                        payload={"proposal_id": proposal_id},
                    )
                )

    def authorize_decision(self, proposal_id: str, votes: dict[str, str]) -> None:
        """Approve proposal status, archive provenance trace records, and dispatch events."""
        proposal = self.proposal_manager.proposals.get(proposal_id)
        if not proposal:
            raise DecisionIntelligenceError(f"Proposal not found: '{proposal_id}'")

        # Decision recommendation must have reached consensus or been escalated to governance
        if proposal.status not in {"ConsensusReached", "Escalated"}:
            raise DecisionIntelligenceError(
                f"Authorization rejected: Proposal status is '{proposal.status}'."
            )

        proposal.status = "Approved"
        self.provenance_manager.archive_decision(proposal, votes)

        self.event_bus.publish_sync(
            Event(
                name="decision.approved",
                category="DecisionIntelligence",
                source="DecisionIntelligencePlatform",
                payload={"proposal_id": proposal_id},
            )
        )
