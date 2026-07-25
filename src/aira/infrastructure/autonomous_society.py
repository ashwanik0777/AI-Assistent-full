"""Enterprise Autonomous Society Foundation Platform for AIRA.

Provides society coordinators, agent registries, role assignment engines, and result aggregators.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.autonomous_society")


class AutonomousSocietyError(Exception):
    """Base exception raised for role assignment mismatches or collaboration session failures."""

    pass


@dataclass
class SocietyAgent:
    """Agent in the society specifying capabilities, trust level, and availability."""

    agent_id: str
    capabilities: list[str]
    trust_level: float
    availability: bool
    specialization: str


@dataclass
class CollaborationSession:
    """Session tracking goal, participating agents, assigned roles, and constraints."""

    session_id: str
    goal: str
    participating_agents: list[str]
    assigned_roles: dict[str, str]  # agent_id -> role
    responsibilities: dict[str, list[str]]  # agent_id -> responsibilities list
    constraints: dict[str, Any]
    governance_policies: list[str]
    evidence_references: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    version: int = 1


class AgentRegistry:
    """Tracks available specialized agents registered in the society."""

    def __init__(self) -> None:
        self.agents: dict[str, SocietyAgent] = {}

    def register_agent(self, agent: SocietyAgent) -> None:
        """Register agent entry."""
        self.agents[agent.agent_id] = agent


class RoleAssignmentEngine:
    """Matches roles to agents based on capabilities, trust levels, and availability."""

    def assign_role(self, agent: SocietyAgent, role: str, required_caps: list[str]) -> bool:
        """Verify that agent satisfies capability requirements, trust levels, and availability."""
        if not agent.availability:
            return False

        # Verify capabilities
        for c in required_caps:
            if c not in agent.capabilities:
                return False

        # Validate minimum trust level depending on role criticality
        min_trust = 0.8 if role in {"Planner", "Reviewer"} else 0.5
        return not agent.trust_level < min_trust


class CollaborationSessionManager:
    """Manages collaboration session registries and parameters validation."""

    def __init__(self) -> None:
        self.sessions: dict[str, CollaborationSession] = {}

    def create_session(
        self,
        session_id: str,
        goal: str,
        assigned_roles: dict[str, str],
        responsibilities: dict[str, list[str]],
        constraints: dict[str, Any],
        policies: list[str],
    ) -> CollaborationSession:
        """Construct session record."""
        session = CollaborationSession(
            session_id=session_id,
            goal=goal,
            participating_agents=list(assigned_roles.keys()),
            assigned_roles=assigned_roles,
            responsibilities=responsibilities,
            constraints=constraints,
            governance_policies=policies,
        )
        self.sessions[session_id] = session
        return session


class ResultAggregator:
    """Aggregates deliverables and evidences from multiple collaboration agents."""

    def aggregate_results(self, results: dict[str, dict[str, Any]]) -> dict[str, Any]:
        """Verify evidence logs completeness and return aggregated outcome dictionary."""
        evidences = []
        consolidated = {}

        for agent, data in results.items():
            if "deliverable" not in data or "evidence" not in data:
                raise AutonomousSocietyError(
                    f"Aggregation failed: Deliverable or evidence missing for agent '{agent}'."
                )
            consolidated[agent] = data["deliverable"]
            evidences.append(data["evidence"])

        return {
            "status": "Success",
            "consolidated_deliverables": consolidated,
            "aggregated_evidences": evidences,
        }


class SocietyCoordinator:
    """Coordinating manager resolving society initialization, assignments, and dispatches events."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.agent_registry = AgentRegistry()
        self.role_engine = RoleAssignmentEngine()
        self.session_manager = CollaborationSessionManager()
        self.aggregator = ResultAggregator()

    def start_collaboration(
        self,
        session_id: str,
        goal: str,
        role_requirements: dict[str, list[str]],  # role -> list of required capabilities
        constraints: dict[str, Any],
        policies: list[str],
    ) -> CollaborationSession:
        """Assign agents to required roles, validate assignments, and initialize session."""
        assigned_roles = {}
        responsibilities = {}

        # 1. Match roles to registered agents
        for role, req_caps in role_requirements.items():
            assigned_agent = None
            for agent in self.agent_registry.agents.values():
                if agent.agent_id not in assigned_roles and self.role_engine.assign_role(
                    agent, role, req_caps
                ):
                    assigned_agent = agent
                    break

            if not assigned_agent:
                raise AutonomousSocietyError(
                    f"Role assignment failed: No agent satisfies requirements for '{role}'."
                )

            assigned_roles[assigned_agent.agent_id] = role
            responsibilities[assigned_agent.agent_id] = [f"Execute deliverables for role: {role}"]

        # 2. Dispatch Roles Assigned Event
        self.event_bus.publish_sync(
            Event(
                name="society.roles.assigned",
                category="AutonomousSociety",
                source="SocietyCoordinator",
                payload={"session_id": session_id, "assignments": assigned_roles},
            )
        )

        # 3. Create Session
        session = self.session_manager.create_session(
            session_id=session_id,
            goal=goal,
            assigned_roles=assigned_roles,
            responsibilities=responsibilities,
            constraints=constraints,
            policies=policies,
        )

        self.event_bus.publish_sync(
            Event(
                name="society.session.created",
                category="AutonomousSociety",
                source="SocietyCoordinator",
                payload={"session_id": session_id},
            )
        )

        self.event_bus.publish_sync(
            Event(
                name="society.collaboration.started",
                category="AutonomousSociety",
                source="SocietyCoordinator",
                payload={"session_id": session_id},
            )
        )

        return session

    def update_agent_responsibilities(
        self, session_id: str, agent_id: str, new_responsibilities: list[str]
    ) -> None:
        """Update responsibilities and publish updates event."""
        session = self.session_manager.sessions.get(session_id)
        if not session:
            raise AutonomousSocietyError(f"Session not found: '{session_id}'")

        if agent_id not in session.assigned_roles:
            raise AutonomousSocietyError(
                f"Agent '{agent_id}' is not a participant of session '{session_id}'."
            )

        session.responsibilities[agent_id] = new_responsibilities

        self.event_bus.publish_sync(
            Event(
                name="society.responsibilities.updated",
                category="AutonomousSociety",
                source="SocietyCoordinator",
                payload={"session_id": session_id, "agent_id": agent_id},
            )
        )

    def aggregate_session_deliverables(
        self, session_id: str, deliverables: dict[str, dict[str, Any]]
    ) -> dict[str, Any]:
        """Aggregate data, validate outcomes, and notify events."""
        session = self.session_manager.sessions.get(session_id)
        if not session:
            raise AutonomousSocietyError(f"Session not found: '{session_id}'")

        # Verify all participants submitted deliverables
        for agent_id in session.assigned_roles:
            if agent_id not in deliverables:
                raise AutonomousSocietyError(
                    f"Aggregation failed: Deliverable missing for participating agent '{agent_id}'."
                )

        aggregated = self.aggregator.aggregate_results(deliverables)

        self.event_bus.publish_sync(
            Event(
                name="society.result.aggregated",
                category="AutonomousSociety",
                source="SocietyCoordinator",
                payload={"session_id": session_id, "status": aggregated["status"]},
            )
        )

        return aggregated
