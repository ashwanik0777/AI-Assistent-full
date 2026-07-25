"""Enterprise Knowledge Evolution, Evidence Review & Knowledge Governance Platform for AIRA.

Provides proposal generators, review managers, approval state pipelines, and version controllers.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.knowledge_evolution")


class KnowledgeEvolutionError(Exception):
    """Base exception raised for proposal invalid transitions, review blocks, or version errors."""

    pass


@dataclass
class KnowledgeProposal:
    """Proposal record encapsulating domain improvements generated from feedback."""

    proposal_id: str
    knowledge_domain: str
    evidence_references: list[str]
    confidence_score: float
    reviewer_assignments: list[str]
    target_knowledge_pack: str
    approval_status: str = "Draft"  # Draft, Pending Review, Approved, Published, Rejected, Archived
    version_metadata: dict[str, Any] = field(default_factory=dict)
    priority: str = "Medium"
    metadata: dict[str, Any] = field(default_factory=dict)


class KnowledgeVersionManager:
    """Tracks version increments, changes logs, and rollback options for Knowledge Packs."""

    def __init__(self) -> None:
        # Maps pack_id -> list of versions configuration dicts
        self.version_history: dict[str, list[dict[str, Any]]] = {}
        self.changelogs: dict[str, list[str]] = {}

    def record_version(
        self, pack_id: str, version: str, facts: list[str], changelog_msg: str
    ) -> None:
        """Append facts snapshot version reference to historical trackers."""
        self.version_history.setdefault(pack_id, []).append(
            {"version": version, "facts": facts.copy()}
        )
        self.changelogs.setdefault(pack_id, []).append(f"Version {version}: {changelog_msg}")

    def rollback(self, pack_id: str) -> dict[str, Any]:
        """Evict active version and return previous configuration settings facts."""
        history = self.version_history.get(pack_id, [])
        if len(history) < 2:
            raise KnowledgeEvolutionError(
                f"Rollback failed: No previous version exists for '{pack_id}'."
            )
        # Pop current
        history.pop()
        return history[-1]


class KnowledgeEvolutionManager:
    """Coordinating manager verifying proposals and updating versions."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.version_manager = KnowledgeVersionManager()
        self.proposals: dict[str, KnowledgeProposal] = {}

    def create_proposal(
        self,
        proposal_id: str,
        domain: str,
        evidence_refs: list[str],
        confidence: float,
        target_pack: str,
        priority: str = "Medium",
    ) -> KnowledgeProposal:
        """Create proposal record, validate properties, and catalog in memory."""
        if not proposal_id or not domain or not target_pack:
            raise KnowledgeEvolutionError(
                "Proposal creation failed: ID, Domain, and Target Pack are required."
            )

        proposal = KnowledgeProposal(
            proposal_id=proposal_id,
            knowledge_domain=domain,
            evidence_references=evidence_refs,
            confidence_score=confidence,
            reviewer_assignments=[],
            target_knowledge_pack=target_pack,
            priority=priority,
        )

        self.proposals[proposal_id] = proposal

        self.event_bus.publish_sync(
            Event(
                name="proposal.created",
                category="KnowledgeEvolution",
                source="KnowledgeEvolutionManager",
                payload={"proposal_id": proposal_id, "domain": domain},
            )
        )

        return proposal

    def assign_reviewers(self, proposal_id: str, reviewers: list[str]) -> None:
        """Assign list of reviewers to proposal."""
        proposal = self.proposals.get(proposal_id)
        if not proposal:
            raise KnowledgeEvolutionError(f"Operation failed: Proposal '{proposal_id}' not found.")

        proposal.reviewer_assignments = reviewers
        proposal.approval_status = "Pending Review"

        self.event_bus.publish_sync(
            Event(
                name="review.assigned",
                category="KnowledgeEvolution",
                source="KnowledgeEvolutionManager",
                payload={"proposal_id": proposal_id, "reviewers": reviewers},
            )
        )

    def update_proposal_status(self, proposal_id: str, status: str) -> None:
        """Execute approval transitions and enforce compliance checks."""
        proposal = self.proposals.get(proposal_id)
        if not proposal:
            raise KnowledgeEvolutionError(f"Operation failed: Proposal '{proposal_id}' not found.")

        allowed = {
            "Draft",
            "Pending Review",
            "Approved",
            "Scheduled",
            "Published",
            "Rejected",
            "Archived",
        }
        if status not in allowed:
            raise KnowledgeEvolutionError(
                f"Status update failed: Status '{status}' is not supported."
            )

        # Enforce validation: Must have reviewers assigned to be Approved/Published
        if status in ("Approved", "Published") and not proposal.reviewer_assignments:
            raise KnowledgeEvolutionError(
                f"Status transition to '{status}' rejected: Reviewers must be assigned first."
            )

        proposal.approval_status = status

        if status == "Approved":
            self.event_bus.publish_sync(
                Event(
                    name="proposal.approved",
                    category="KnowledgeEvolution",
                    source="KnowledgeEvolutionManager",
                    payload={"proposal_id": proposal_id},
                )
            )

    def publish_proposal_update(
        self, proposal_id: str, new_version: str, evolved_facts: list[str]
    ) -> None:
        """Publish approved proposal, update version registries, and notify Knowledge Runtime."""
        proposal = self.proposals.get(proposal_id)
        if not proposal:
            raise KnowledgeEvolutionError(f"Operation failed: Proposal '{proposal_id}' not found.")

        if proposal.approval_status != "Approved":
            raise KnowledgeEvolutionError(
                f"Publication failed: Proposal '{proposal_id}' must be Approved first. "
                f"Current status: {proposal.approval_status}"
            )

        pack_id = proposal.target_knowledge_pack

        # Record version details
        msg = f"Evolved domain facts from proposal {proposal_id}"
        self.version_manager.record_version(pack_id, new_version, evolved_facts, msg)

        # Dynamically publish updates to KnowledgeRuntime registry if it is initialized
        try:
            runtime = self.registry.get_service("KnowledgeRuntime")
        except Exception:
            runtime = None
        if runtime:
            # Check pack exists, otherwise install first
            if pack_id in runtime.registry.active_packs:  # type: ignore
                runtime.registry.active_packs[pack_id].version = new_version  # type: ignore
                runtime.index.facts[pack_id] = evolved_facts.copy()  # type: ignore
            else:
                from aira.infrastructure.knowledge_pack import KnowledgePackManifest

                manifest = KnowledgePackManifest(
                    pack_id=pack_id,
                    name=pack_id,
                    version=new_version,
                    domains=[proposal.knowledge_domain],
                    supported_languages=["en"],
                )
                runtime.install_knowledge_pack(manifest, evolved_facts)  # type: ignore
                runtime.enable_knowledge_pack(pack_id)  # type: ignore

        proposal.approval_status = "Published"

        self.event_bus.publish_sync(
            Event(
                name="knowledge.published",
                category="KnowledgeEvolution",
                source="KnowledgeEvolutionManager",
                payload={"proposal_id": proposal_id, "pack_id": pack_id, "version": new_version},
            )
        )

    def rollback_pack(self, pack_id: str) -> None:
        """Restore pack facts configuration back to previous snapshot checkpoint."""
        restored = self.version_manager.rollback(pack_id)
        ver = restored["version"]
        facts = restored["facts"]

        try:
            runtime = self.registry.get_service("KnowledgeRuntime")
        except Exception:
            runtime = None
        if runtime and pack_id in runtime.registry.active_packs:  # type: ignore
            runtime.registry.active_packs[pack_id].version = ver  # type: ignore
            runtime.index.facts[pack_id] = facts.copy()  # type: ignore

        self.event_bus.publish_sync(
            Event(
                name="knowledge.rolled_back",
                category="KnowledgeEvolution",
                source="KnowledgeEvolutionManager",
                payload={"pack_id": pack_id, "restored_version": ver},
            )
        )

    def generate_governance_dashboard(self) -> str:
        """Compile dashboard text detailing pending proposals and quality latency aggregates."""
        pending = [p for p in self.proposals.values() if p.approval_status == "Pending Review"]
        approved = [p for p in self.proposals.values() if p.approval_status == "Approved"]
        published = [p for p in self.proposals.values() if p.approval_status == "Published"]
        rejected = [p for p in self.proposals.values() if p.approval_status == "Rejected"]

        return (
            "# Knowledge Governance Dashboard\n\n"
            f"* **Pending Review Proposals:** {len(pending)}\n"
            f"* **Approved Proposals:** {len(approved)}\n"
            f"* **Published Updates:** {len(published)}\n"
            f"* **Rejected Proposals:** {len(rejected)}\n"
            f"* **Total Governance Records:** {len(self.proposals)}\n"
        )
