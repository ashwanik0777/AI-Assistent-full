"""Enterprise Task Marketplace, Capability Discovery, Negotiation & Contract Platform for AIRA.

Provides marketplaces, capability matchers, negotiation engines, and contract managers.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.agent_identity import AgentProfile
from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.task_marketplace")


class TaskMarketplaceError(Exception):
    """Base exception raised for negotiation failures or contract validation drifts."""

    pass


@dataclass
class TaskContract:
    """Contract defining SLA targets, priorities, constraints, and state status."""

    contract_id: str
    task_id: str
    selected_agent: str
    capabilities: list[str]
    sla: dict[str, Any]
    priority: int
    success_criteria: list[str]
    governance_rules: list[str]
    # Draft, Negotiating, Approved, Active, Completed, Cancelled, Archived
    lifecycle_state: str = "Draft"
    metadata: dict[str, Any] = field(default_factory=dict)
    version: int = 1


class Marketplace:
    """Registers governed tasks requests, priorities, and dependency rules."""

    def __init__(self) -> None:
        self.tasks: dict[str, dict[str, Any]] = {}

    def publish_task(self, task_id: str, priority: int, requirements: dict[str, Any]) -> None:
        """Register task parameters."""
        self.tasks[task_id] = {
            "task_id": task_id,
            "priority": priority,
            "requirements": requirements,
            "status": "Published",
        }


class CapabilityMatcher:
    """Selects eligible candidate profiles based on required capabilities and trust levels."""

    def filter_candidates(
        self, profiles: list[AgentProfile], required_caps: list[str], min_trust: float
    ) -> list[AgentProfile]:
        """Filter profiles by capability lists and minimum trust limits."""
        candidates = []
        for p in profiles:
            if p.lifecycle_state == "Suspended":
                continue
            if p.trust_level < min_trust:
                continue

            # Check capabilities
            has_all = True
            for c in required_caps:
                if c not in p.capabilities:
                    has_all = False
                    break
            if has_all:
                candidates.append(p)
        return candidates


class NegotiationEngine:
    """Manages coordination negotiation parameters (deadline schedules, resources allocations)."""

    def negotiate_terms(
        self, task_id: str, candidate_id: str, proposed_deadline_sec: int
    ) -> dict[str, Any]:
        """Analyze proposed deadline and return finalized terms dictionary."""
        # Policy rules: accept if deadline is within bounds, reject or scale otherwise
        if proposed_deadline_sec < 60:
            raise TaskMarketplaceError("Negotiation failed: Proposed deadline is too short.")
        return {
            "task_id": task_id,
            "agent_id": candidate_id,
            "agreed_deadline_sec": proposed_deadline_sec,
            "negotiation_status": "Success",
        }


class ContractManager:
    """Manages task contract lifecycle state transitions validation rules."""

    def transition_state(self, contract: TaskContract, to_state: str) -> None:
        """Verify contract state transitions sequences."""
        allowed = {
            "Draft",
            "Negotiating",
            "Approved",
            "Active",
            "Completed",
            "Cancelled",
            "Archived",
        }
        if to_state not in allowed:
            raise TaskMarketplaceError(f"Unsupported contract lifecycle state: '{to_state}'")

        current = contract.lifecycle_state
        if current == "Completed" and to_state != "Completed":
            raise TaskMarketplaceError("Cannot transition from Completed state.")

        contract.lifecycle_state = to_state


class AssignmentEngine:
    """Finalizes agent execution allocation checks."""

    def authorize_assignment(self, contract: TaskContract) -> None:
        """Verify that contract is approved prior to assignment execution."""
        if contract.lifecycle_state != "Approved":
            raise TaskMarketplaceError(
                f"Assignment rejected: Contract '{contract.contract_id}' is not Approved."
            )


class TaskMarketplacePlatform:
    """Coordinating manager resolving marketplaces task publishings, matches, and contracts."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.marketplace = Marketplace()
        self.matcher = CapabilityMatcher()
        self.negotiation = NegotiationEngine()
        self.contract_manager = ContractManager()
        self.assignment = AssignmentEngine()

        self.contracts: dict[str, TaskContract] = {}

    def publish_marketplace_task(
        self, task_id: str, priority: int, requirements: dict[str, Any]
    ) -> None:
        """Publish task and dispatch event."""
        self.marketplace.publish_task(task_id, priority, requirements)
        self.event_bus.publish_sync(
            Event(
                name="task.published",
                category="TaskMarketplace",
                source="TaskMarketplacePlatform",
                payload={"task_id": task_id},
            )
        )

    def negotiate_and_create_contract(
        self,
        contract_id: str,
        task_id: str,
        profiles: list[AgentProfile],
        required_caps: list[str],
        trust_threshold: float,
        deadline_sec: int,
    ) -> TaskContract:
        """Select qualified agent, negotiate terms, create contract, and dispatch events."""
        # 1. Match
        candidates = self.matcher.filter_candidates(profiles, required_caps, trust_threshold)
        if not candidates:
            raise TaskMarketplaceError(
                f"Matching failed: No eligible agent satisfies constraints for task '{task_id}'."
            )
        selected = candidates[0]

        self.event_bus.publish_sync(
            Event(
                name="capability.matched",
                category="TaskMarketplace",
                source="TaskMarketplacePlatform",
                payload={"task_id": task_id, "matched_agent": selected.agent_id},
            )
        )

        # 2. Negotiate
        terms = self.negotiation.negotiate_terms(task_id, selected.agent_id, deadline_sec)

        self.event_bus.publish_sync(
            Event(
                name="negotiation.completed",
                category="TaskMarketplace",
                source="TaskMarketplacePlatform",
                payload={"task_id": task_id, "terms": terms},
            )
        )

        # 3. Create Contract
        contract = TaskContract(
            contract_id=contract_id,
            task_id=task_id,
            selected_agent=selected.agent_id,
            capabilities=required_caps,
            sla={"deadline_sec": terms["agreed_deadline_sec"]},
            priority=1,
            success_criteria=["Complete outputs verification"],
            governance_rules=["Audit compliance checks"],
        )

        self.contract_manager.transition_state(contract, "Approved")
        self.contracts[contract_id] = contract

        self.event_bus.publish_sync(
            Event(
                name="contract.approved",
                category="TaskMarketplace",
                source="TaskMarketplacePlatform",
                payload={"contract_id": contract_id},
            )
        )

        return contract

    def finalize_assignment(self, contract_id: str) -> None:
        """Verify contract approval, authorize assignment allocation, and dispatch event."""
        contract = self.contracts.get(contract_id)
        if not contract:
            raise TaskMarketplaceError(f"Contract not found: '{contract_id}'")

        self.assignment.authorize_assignment(contract)
        self.contract_manager.transition_state(contract, "Active")

        self.event_bus.publish_sync(
            Event(
                name="assignment.created",
                category="TaskMarketplace",
                source="TaskMarketplacePlatform",
                payload={"contract_id": contract_id, "assigned_agent": contract.selected_agent},
            )
        )
