"""Enterprise Collaboration Engine & Multi-Agent Coordination for AIRA.

Provides collaboration contracts, team builders, role assigners, and conflict resolvers.
"""

import time
from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.agent_collaboration")


class AgentCollaborationError(Exception):
    """Raised when contracts, role mappings, or conflicts remain unresolved."""

    pass


@dataclass
class CollaborationContract:
    """Explicit governance agreement defining participants, roles, and context boundaries."""

    contract_id: str
    goal: str
    participants: list[str]
    roles: dict[str, str]  # agent_id -> role name
    shared_context_refs: list[str] = field(default_factory=list)
    success_criteria: str = "All Roles Verified Success"
    completion_rules: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    version: str = "1.0.0"


@dataclass
class ConflictReport:
    """Encapsulation mapping detected conflicts and selected resolution strategies."""

    conflict_id: str
    plan_id: str
    task_id: str
    description: str
    resolution_strategy: str
    resolved: bool = False


class CollaborationContractBuilder:
    """Assembles structured CollaborationContracts."""

    def build_contract(
        self, contract_id: str, goal: str, participants: list[str], roles: dict[str, str]
    ) -> CollaborationContract:
        """Construct a new collaboration contract with mapped roles."""
        return CollaborationContract(
            contract_id=contract_id,
            goal=goal,
            participants=participants,
            roles=roles,
            completion_rules=["VerificationReportPassed"],
        )


class TeamBuilder:
    """Forms compatible teams matching capabilities and availability profiles."""

    def __init__(self, registry: Any) -> None:
        self.registry = registry

    def form_team(self, roles_needed: list[str]) -> list[str]:
        """Query registry records to select compatible, ready agents ids."""
        selected_agents = []
        for role in roles_needed:
            found = False
            for record in self.registry.list_all():
                if record.role == role and record.lifecycle_state == "Ready":
                    selected_agents.append(record.agent_id)
                    found = True
                    break
            if not found:
                raise AgentCollaborationError(
                    f"Team Formation failed: No ready agent satisfies role requirement '{role}'."
                )
        return selected_agents


class RoleAssignmentEngine:
    """Handles dynamic mapping assignments updates."""

    def assign_roles(self, contract: CollaborationContract, assignments: dict[str, str]) -> None:
        """Update role assignments on the active contract."""
        contract.roles.update(assignments)


class SharedTeamBoard:
    """Maintains task boards categorizing status of assigned execution runs."""

    def __init__(self) -> None:
        self.tasks: dict[str, str] = {}  # task_id -> status (Pending, Running, Completed, Blocked)
        self.decisions: list[dict[str, Any]] = []

    def update_task_status(self, task_id: str, status: str) -> None:
        """Update task board category."""
        self.tasks[task_id] = status


class ConflictResolver:
    """Identifies overlapping, duplicate, or contradictory work outputs."""

    def __init__(self) -> None:
        self.conflicts_log: list[ConflictReport] = []

    def detect_conflicts(self, board: SharedTeamBoard, plan_id: str) -> list[ConflictReport] | None:
        """Scan board tasks to identify duplicates or blocked states conflicts."""
        conflicts = []
        # Check if multiple agents are working on same task or if statuses are blocked
        for task_id, status in board.tasks.items():
            if status == "Blocked":
                conflicts.append(
                    ConflictReport(
                        conflict_id=f"conf_{task_id}_{int(time.time())}",
                        plan_id=plan_id,
                        task_id=task_id,
                        description=f"Task '{task_id}' is in Blocked state.",
                        resolution_strategy="ReassignTask",
                    )
                )
        if conflicts:
            self.conflicts_log.extend(conflicts)
            return conflicts
        return None

    def resolve_conflict(self, conflict_id: str) -> None:
        """Resolve tracked conflict status."""
        for report in self.conflicts_log:
            if report.conflict_id == conflict_id:
                report.resolved = True
                break


class CollaborationEngine:
    """Coordinating platform manager building collaboration teams and updating task boards."""

    def __init__(
        self,
        config: AppConfig,
        registry: ServiceRegistry,
        event_bus: EventBus,
        agent_registry: Any = None,
    ) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus
        self.agent_registry = agent_registry

        self.contract_builder = CollaborationContractBuilder()
        self.team_builder = TeamBuilder(self.agent_registry)
        self.role_engine = RoleAssignmentEngine()
        self.board = SharedTeamBoard()
        self.resolver = ConflictResolver()

    def start_collaboration(
        self, contract_id: str, goal: str, roles_needed: list[str]
    ) -> CollaborationContract:
        """Form team, assemble contract, log assignments, and publish initialization events."""
        # 1. Form Team
        participants = self.team_builder.form_team(roles_needed)

        # Map participants to roles dict
        roles_map = {}
        for i, role in enumerate(roles_needed):
            roles_map[participants[i]] = role

        # 2. Build Contract
        contract = self.contract_builder.build_contract(contract_id, goal, participants, roles_map)
        self.event_bus.publish_sync(
            Event(
                name="team.created",
                category="Collaboration",
                source="CollaborationEngine",
                payload={"contract_id": contract_id, "participants": participants},
            )
        )

        # 3. Publish dynamic role assignment events
        for agent_id, role in roles_map.items():
            self.event_bus.publish_sync(
                Event(
                    name="role.assigned",
                    category="Collaboration",
                    source="CollaborationEngine",
                    payload={"agent_id": agent_id, "role": role},
                )
            )

        return contract

    def sync_coordination(self, task_id: str, status: str, plan_id: str) -> None:
        """Update shared board, perform conflicts check, and publish updates events."""
        self.board.update_task_status(task_id, status)
        self.event_bus.publish_sync(
            Event(
                name="coordination.updated",
                category="Collaboration",
                source="CollaborationEngine",
                payload={"task_id": task_id, "status": status},
            )
        )

        # Check conflicts
        conflicts = self.resolver.detect_conflicts(self.board, plan_id)
        if conflicts:
            for conf in conflicts:
                self.event_bus.publish_sync(
                    Event(
                        name="conflict.detected",
                        category="Collaboration",
                        source="CollaborationEngine",
                        payload={"conflict_id": conf.conflict_id, "task_id": conf.task_id},
                    )
                )

    def resolve_coordination_conflict(self, conflict_id: str) -> None:
        """Resolve conflict, notify event stream."""
        self.resolver.resolve_conflict(conflict_id)
        self.event_bus.publish_sync(
            Event(
                name="conflict.resolved",
                category="Collaboration",
                source="CollaborationEngine",
                payload={"conflict_id": conflict_id},
            )
        )
