"""Enterprise Resilience, Self-Healing, Failover & Disaster Recovery Platform for AIRA.

Provides incident detectors, recovery planners, failover managers, and recovery validators.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.disaster_recovery")


class DisasterRecoveryError(Exception):
    """Base exception raised for recovery planning failures or validation faults."""

    pass


@dataclass
class RecoveryPlan:
    """Design plan specifying incident context, strategies, validation steps, and versions."""

    plan_id: str
    incident_id: str
    affected_services: list[str]
    dependencies: list[str]
    recovery_strategy: str  # e.g., "Failover", "Re-init", "Degraded Mode"
    checkpoint_reference: str
    validation_plan: str
    rollback_plan: str
    metadata: dict[str, Any] = field(default_factory=dict)
    version: int = 1


class IncidentDetector:
    """Identifies component incidents and builds structured alert reports."""

    def detect_incident(
        self, incident_id: str, component: str, failure_type: str
    ) -> dict[str, Any]:
        """Construct incident payload."""
        return {
            "incident_id": incident_id,
            "component": component,
            "failure_type": failure_type,
            "status": "Active",
        }


class DependencyGraphEngine:
    """Evaluates cascading relationships mapping execution and memory links."""

    def __init__(self) -> None:
        self.dependencies: dict[str, list[str]] = {}

    def add_dependency(self, service: str, depends_on: str) -> None:
        """Register dependency relationship."""
        if service not in self.dependencies:
            self.dependencies[service] = []
        self.dependencies[service].append(depends_on)

    def get_cascading_affected(self, service: str) -> list[str]:
        """Resolve affected services list recursively."""
        affected = set()
        queue = [service]
        while queue:
            curr = queue.pop(0)
            if curr not in affected:
                affected.add(curr)
                for s, deps in self.dependencies.items():
                    if curr in deps:
                        queue.append(s)
        return list(affected)


class RecoveryPlanner:
    """Generates structured recovery checklists, checkpoints, and rollback strategies."""

    def create_plan(
        self, plan_id: str, incident: dict[str, Any], affected: list[str], dependencies: list[str]
    ) -> RecoveryPlan:
        """Construct structured recovery plan descriptor."""
        return RecoveryPlan(
            plan_id=plan_id,
            incident_id=incident["incident_id"],
            affected_services=affected,
            dependencies=dependencies,
            recovery_strategy="Failover",
            checkpoint_reference="cp_last_safe",
            validation_plan="run-health-checks",
            rollback_plan="restore-previous-provider",
        )


class FailoverManager:
    """Coordinates migration to secondary replicas or alternate execution providers."""

    def execute_failover(self, plan: RecoveryPlan, available_providers: list[str]) -> str:
        """Migrate to alternate provider. Reject if no provider is available."""
        if not available_providers:
            raise DisasterRecoveryError(
                "Failover failed: No alternate execution providers available."
            )
        return available_providers[0]


class RecoveryValidator:
    """Ensures dependency restoration and health checks validate successfully."""

    def validate_recovery(self, plan: RecoveryPlan, restored_healthy: dict[str, bool]) -> bool:
        """Verify all plan dependencies are marked healthy."""
        return all(restored_healthy.get(dep, False) for dep in plan.dependencies)


class RecoveryAuditManager:
    """Stores persistent records of incident alarms and outcome validation states."""

    def __init__(self) -> None:
        self.logs: list[dict[str, Any]] = []

    def log_action(self, plan_id: str, action: str, details: dict[str, Any]) -> None:
        """Append log trace entry."""
        self.logs.append({"plan_id": plan_id, "action": action, "details": details})


class DisasterRecoveryManager:
    """Coordinating manager capturing incidents, failure recovery, and event notifications."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.detector = IncidentDetector()
        self.graph_engine = DependencyGraphEngine()
        self.planner = RecoveryPlanner()
        self.failover_manager = FailoverManager()
        self.validator = RecoveryValidator()
        self.audit_manager = RecoveryAuditManager()

        self.active_plans: dict[str, RecoveryPlan] = {}

    def process_incident(
        self,
        incident_id: str,
        failed_service: str,
        failure_type: str,
        available_providers: list[str],
        restored_healthy: dict[str, bool],
    ) -> str:
        """Detect incident, run failover, validate restored state, and publish events."""
        # 1. Detect
        incident = self.detector.detect_incident(incident_id, failed_service, failure_type)
        self.event_bus.publish_sync(
            Event(
                name="incident.detected",
                category="DisasterRecovery",
                source="DisasterRecoveryManager",
                payload={"incident": incident},
            )
        )

        # 2. Plan
        affected = self.graph_engine.get_cascading_affected(failed_service)
        deps = self.graph_engine.dependencies.get(failed_service, [])
        plan = self.planner.create_plan(f"plan_{incident_id}", incident, affected, deps)
        self.active_plans[plan.plan_id] = plan

        self.event_bus.publish_sync(
            Event(
                name="recovery.planned",
                category="DisasterRecovery",
                source="DisasterRecoveryManager",
                payload={"plan_id": plan.plan_id},
            )
        )

        # 3. Failover
        new_provider = self.failover_manager.execute_failover(plan, available_providers)
        self.audit_manager.log_action(plan.plan_id, "Failover Executed", {"provider": new_provider})

        self.event_bus.publish_sync(
            Event(
                name="failover.triggered",
                category="DisasterRecovery",
                source="DisasterRecoveryManager",
                payload={"plan_id": plan.plan_id, "provider": new_provider},
            )
        )

        # 4. Validate
        is_healthy = self.validator.validate_recovery(plan, restored_healthy)
        if not is_healthy:
            self.audit_manager.log_action(
                plan.plan_id, "Validation Failed", {"reason": "Dependency offline"}
            )
            raise DisasterRecoveryError(f"Recovery validation failed for plan '{plan.plan_id}'.")

        self.event_bus.publish_sync(
            Event(
                name="recovery.validated",
                category="DisasterRecovery",
                source="DisasterRecoveryManager",
                payload={"plan_id": plan.plan_id},
            )
        )

        self.event_bus.publish_sync(
            Event(
                name="recovery.completed",
                category="DisasterRecovery",
                source="DisasterRecoveryManager",
                payload={"plan_id": plan.plan_id},
            )
        )

        return new_provider
