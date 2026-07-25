"""Enterprise Global Workflow & Mission Federation Platform for AIRA.

Provides mission registries, coordinators, local runtimes, and gateways.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.mission_federation")


class MissionFederationError(Exception):
    """Exception raised for coordination failures, validation gates, or evidence issues."""

    pass


@dataclass
class FederatedMissionDescriptor:
    """Descriptor layout specifying mission objectives, local tasks, and status flags."""

    mission_id: str
    mission_owner: str
    participating_organizations: list[str] = field(default_factory=list)
    mission_objectives: list[str] = field(default_factory=list)
    local_responsibilities: dict[str, str] = field(default_factory=dict)
    coordination_policies: list[str] = field(default_factory=list)
    evidence_rules: dict[str, str] = field(default_factory=dict)
    mission_status: str = "Created"  # Created, Active, Suspended, Closed
    version: str = "1.0.0"
    metadata: dict[str, Any] = field(default_factory=dict)


class GlobalMissionRegistry:
    """Registry inventory catalog managing federated global missions."""

    def __init__(self) -> None:
        self.missions: dict[str, FederatedMissionDescriptor] = {}

    def register_mission(self, descriptor: FederatedMissionDescriptor) -> None:
        """Save mission descriptor settings."""
        self.missions[descriptor.mission_id] = descriptor


class MissionPolicyManager:
    """Enforces compliance checks and evaluates participant eligibility."""

    def verify_eligibility(
        self, descriptor: FederatedMissionDescriptor, org_id: str, trust_level: str
    ) -> bool:
        """Validate if organization trust matches eligibility boundaries."""
        if trust_level == "Suspended":
            return False

        if "Strategic-Only" in descriptor.coordination_policies:
            return trust_level == "Strategic Partner"

        return True


class EvidenceExchangeGateway:
    """Verifies evidence submissions matching rules constraints."""

    def __init__(self) -> None:
        self.submitted_evidence: dict[str, list[dict[str, Any]]] = {}

    def submit_evidence(
        self, mission_id: str, org_id: str, task_key: str, evidence_payload: dict[str, Any]
    ) -> None:
        """Record task execution evidence details."""
        self.submitted_evidence.setdefault(mission_id, []).append(
            {"org_id": org_id, "task_key": task_key, "evidence": evidence_payload}
        )


class LocalMissionRuntime:
    """Runs tasks locally preserving regional autonomy parameters."""

    def execute_local_task(self, org_id: str, task_key: str) -> dict[str, Any]:
        """Execute tasks and return local evidence traces."""
        return {
            "executor": org_id,
            "task": task_key,
            "result": "Success",
            "checksum": f"hash_{org_id}_{task_key}",
        }


class MissionAuditManager:
    """Audits milestone progress and records E2E trace history."""

    def __init__(self) -> None:
        self.audit_log: list[dict[str, Any]] = []

    def record_activity(self, mission_id: str, org_id: str, activity: str, details: str) -> None:
        """Append audit log trace record."""
        self.audit_log.append(
            {"mission_id": mission_id, "org_id": org_id, "activity": activity, "details": details}
        )


class MissionCoordinator:
    """Orchestrates global coordination, dependencies, and escalation pathways."""

    def __init__(self, audit_manager: MissionAuditManager) -> None:
        self.audit_manager = audit_manager
        self.milestones: dict[str, dict[str, str]] = {}

    def complete_milestone(self, mission_id: str, org_id: str, milestone_key: str) -> None:
        """Mark milestone completed state."""
        self.milestones.setdefault(mission_id, {})[milestone_key] = "Completed"
        self.audit_manager.record_activity(
            mission_id, org_id, "MilestoneCompleted", f"Milestone '{milestone_key}' done."
        )

    def check_dependency_risk(self, mission_id: str, required_milestone: str) -> bool:
        """Return True if required milestone is not completed."""
        completed = self.milestones.get(mission_id, {}).get(required_milestone) == "Completed"
        return not completed


class MissionFederationPlatform:
    """Coordinating manager resolving mission registries and coordination workflows."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.global_registry = GlobalMissionRegistry()
        self.policy_manager = MissionPolicyManager()
        self.evidence_gateway = EvidenceExchangeGateway()
        self.local_runtime = LocalMissionRuntime()
        self.audit_manager = MissionAuditManager()
        self.coordinator = MissionCoordinator(self.audit_manager)

    def create_federated_mission(
        self,
        mission_id: str,
        mission_owner: str,
        participating_organizations: list[str],
        mission_objectives: list[str],
        local_responsibilities: dict[str, str],
        coordination_policies: list[str],
        evidence_rules: dict[str, str],
    ) -> FederatedMissionDescriptor:
        """Initialize mission descriptor, register profile, and publish events."""
        if not mission_id or not mission_owner:
            raise MissionFederationError(
                "Creation failed: Mission descriptors require ID and owner."
            )

        descriptor = FederatedMissionDescriptor(
            mission_id=mission_id,
            mission_owner=mission_owner,
            participating_organizations=participating_organizations,
            mission_objectives=mission_objectives,
            local_responsibilities=local_responsibilities,
            coordination_policies=coordination_policies,
            evidence_rules=evidence_rules,
            mission_status="Created",
        )

        self.global_registry.register_mission(descriptor)

        self.event_bus.publish_sync(
            Event(
                name="mission.created",
                category="MissionFederation",
                source="MissionFederationPlatform",
                payload={"mission_id": mission_id},
            )
        )

        return descriptor

    def join_mission(self, mission_id: str, org_id: str, trust_level: str) -> None:
        """Validate eligibility, update descriptors participants, and publish events."""
        desc = self.global_registry.missions.get(mission_id)
        if not desc:
            raise MissionFederationError(f"Mission descriptor not found: '{mission_id}'")

        eligible = self.policy_manager.verify_eligibility(desc, org_id, trust_level)
        if not eligible:
            self.audit_manager.record_activity(
                mission_id, org_id, "JoinFailed", "Ineligible trust status."
            )
            raise MissionFederationError(f"Join rejected: Organization '{org_id}' is ineligible.")

        if org_id not in desc.participating_organizations:
            desc.participating_organizations.append(org_id)

        self.audit_manager.record_activity(
            mission_id, org_id, "Joined", "Joined mission successfully."
        )

        self.event_bus.publish_sync(
            Event(
                name="mission.org.joined",
                category="MissionFederation",
                source="MissionFederationPlatform",
                payload={"mission_id": mission_id, "org_id": org_id},
            )
        )

    def submit_task_evidence(
        self, mission_id: str, org_id: str, task_key: str, evidence_payload: dict[str, Any]
    ) -> None:
        """Verify rule formats, submit to gateway, update audits, and publish events."""
        desc = self.global_registry.missions.get(mission_id)
        if not desc:
            raise MissionFederationError(f"Mission descriptor not found: '{mission_id}'")

        # Basic rule assert check
        required_rule = desc.evidence_rules.get(task_key)
        if required_rule and required_rule not in evidence_payload.get("checksum", ""):
            self.audit_manager.record_activity(
                mission_id, org_id, "EvidenceFailed", f"Invalid evidence signature for {task_key}."
            )
            raise MissionFederationError(
                f"Evidence validation failed: Drift on rule criteria for '{task_key}'."
            )

        self.evidence_gateway.submit_evidence(mission_id, org_id, task_key, evidence_payload)
        self.audit_manager.record_activity(
            mission_id, org_id, "EvidenceSubmitted", f"Evidence submitted for task '{task_key}'."
        )

        self.event_bus.publish_sync(
            Event(
                name="mission.evidence.submitted",
                category="MissionFederation",
                source="MissionFederationPlatform",
                payload={"mission_id": mission_id, "org_id": org_id, "task": task_key},
            )
        )

    def complete_mission_milestone(self, mission_id: str, org_id: str, milestone_key: str) -> None:
        """Mark milestone, notify coordinator, and publish events."""
        self.coordinator.complete_milestone(mission_id, org_id, milestone_key)

        self.event_bus.publish_sync(
            Event(
                name="mission.milestone.completed",
                category="MissionFederation",
                source="MissionFederationPlatform",
                payload={"mission_id": mission_id, "milestone": milestone_key},
            )
        )

    def close_mission(self, mission_id: str) -> None:
        """Update status closed and publish events."""
        desc = self.global_registry.missions.get(mission_id)
        if not desc:
            raise MissionFederationError(f"Mission descriptor not found: '{mission_id}'")

        desc.mission_status = "Closed"
        self.audit_manager.record_activity(
            mission_id, desc.mission_owner, "Closed", "Mission E2E closed."
        )

        self.event_bus.publish_sync(
            Event(
                name="mission.closed",
                category="MissionFederation",
                source="MissionFederationPlatform",
                payload={"mission_id": mission_id},
            )
        )
