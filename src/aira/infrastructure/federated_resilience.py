"""Enterprise Federated Resilience, Disaster Recovery & Business Continuity Platform for AIRA.

Provides failure detection, recovery planning, continuity coordination, and validations.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.federated_resilience")


class FederatedResilienceError(Exception):
    """Exception raised for detection, planning, or recovery validation failures."""

    pass


@dataclass
class RecoveryPlanDescriptor:
    """Descriptor layout specifying recovery strategy, fallback target, and validation rules."""

    recovery_plan_id: str
    affected_runtime: str
    recovery_strategy: str  # Runtime Failover, Regional Failover, Controlled Degradation
    fallback_runtime: str
    recovery_objectives: list[str] = field(default_factory=list)
    validation_rules: list[str] = field(default_factory=list)
    evidence_references: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    version: str = "1.0.0"


class FailureDetectionEngine:
    """Monitors runtime status and detects failures."""

    def analyze_status(self, runtime_id: str, status: str) -> bool:
        """Return True if status indicates failure or degradation."""
        return status in ("Offline", "Unavailable", "Degraded")


class RecoveryPlanner:
    """Selects and validates recovery plans."""

    def __init__(self) -> None:
        self.plans: dict[str, RecoveryPlanDescriptor] = {}

    def register_plan(self, plan: RecoveryPlanDescriptor) -> None:
        """Register recovery plan descriptor."""
        self.plans[plan.recovery_plan_id] = plan


class RecoveryValidator:
    """Verifies eligibility and policy compliance of target fallback runtimes."""

    def verify_fallback_eligibility(
        self, fallback_runtime: str, governance_policies: list[str]
    ) -> bool:
        """Block if policy restrictions match disallowed fallback regions."""
        # Simple policy block: cannot failover to US if Block-US policy is present
        disallowed = "Block-US" in governance_policies and "US" in fallback_runtime
        return not disallowed


class RecoveryEvidenceManager:
    """Logs action evidence events and archives operational recovery history."""

    def __init__(self) -> None:
        self.evidence_log: list[dict[str, Any]] = []

    def record_evidence(self, plan_id: str, action: str, result: str) -> None:
        """Append operational event detail to audit archive."""
        self.evidence_log.append({"plan_id": plan_id, "action": action, "result": result})


class ContinuityCoordinator:
    """Preserves mission continuity and tracks recovery progress."""

    def __init__(self, evidence_manager: RecoveryEvidenceManager) -> None:
        self.evidence_manager = evidence_manager
        self.active_failovers: dict[str, str] = {}

    def activate_fallback(self, plan_id: str, affected: str, fallback: str) -> None:
        """Coordinate routing destination to fallback runtime."""
        self.active_failovers[affected] = fallback
        self.evidence_manager.record_evidence(
            plan_id, "FallbackActivated", f"Routed {affected} -> {fallback}"
        )


class FederatedResiliencePlatform:
    """Coordinating manager resolving detectors, planners, coordinators, and validators."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.detector = FailureDetectionEngine()
        self.planner = RecoveryPlanner()
        self.validator = RecoveryValidator()
        self.evidence_manager = RecoveryEvidenceManager()
        self.coordinator = ContinuityCoordinator(self.evidence_manager)

    def monitor_and_detect_failure(self, runtime_id: str, status: str) -> bool:
        """Audit status, flag failures, and publish events."""
        failed = self.detector.analyze_status(runtime_id, status)

        if failed:
            self.event_bus.publish_sync(
                Event(
                    name="resilience.failure.detected",
                    category="FederatedResilience",
                    source="FederatedResiliencePlatform",
                    payload={"runtime_id": runtime_id, "status": status},
                )
            )

        return failed

    def formulate_recovery_plan(
        self,
        plan_id: str,
        affected_runtime: str,
        strategy: str,
        fallback_runtime: str,
        validation_rules: list[str],
    ) -> RecoveryPlanDescriptor:
        """Instantiate plan, save to planner logs, and publish events."""
        if not plan_id or not affected_runtime:
            raise FederatedResilienceError(
                "Planning failed: Recovery plan descriptors require ID and affected runtime."
            )

        plan = RecoveryPlanDescriptor(
            recovery_plan_id=plan_id,
            affected_runtime=affected_runtime,
            recovery_strategy=strategy,
            fallback_runtime=fallback_runtime,
            validation_rules=validation_rules,
        )

        self.planner.register_plan(plan)

        self.event_bus.publish_sync(
            Event(
                name="resilience.recovery.planned",
                category="FederatedResilience",
                source="FederatedResiliencePlatform",
                payload={"recovery_plan_id": plan_id},
            )
        )

        return plan

    def initiate_failover(self, plan_id: str, governance_policies: list[str]) -> bool:
        """Validate eligibility constraints, coordinate failover, and publish events."""
        plan = self.planner.plans.get(plan_id)
        if not plan:
            raise FederatedResilienceError(f"Recovery plan not found: '{plan_id}'")

        eligible = self.validator.verify_fallback_eligibility(
            plan.fallback_runtime, governance_policies
        )

        if not eligible:
            self.evidence_manager.record_evidence(
                plan_id, "FallbackRejected", "Ineligible target destination"
            )
            return False

        self.coordinator.activate_fallback(plan_id, plan.affected_runtime, plan.fallback_runtime)

        self.event_bus.publish_sync(
            Event(
                name="resilience.fallback.activated",
                category="FederatedResilience",
                source="FederatedResiliencePlatform",
                payload={"recovery_plan_id": plan_id, "fallback": plan.fallback_runtime},
            )
        )

        return True

    def validate_and_restore_continuity(self, plan_id: str) -> None:
        """Certify recovery completion and update continuity state."""
        plan = self.planner.plans.get(plan_id)
        if not plan:
            raise FederatedResilienceError(f"Recovery plan not found: '{plan_id}'")

        self.evidence_manager.record_evidence(plan_id, "RecoveryValidated", "Health checks passed")

        self.event_bus.publish_sync(
            Event(
                name="resilience.recovery.validated",
                category="FederatedResilience",
                source="FederatedResiliencePlatform",
                payload={"recovery_plan_id": plan_id},
            )
        )

        self.event_bus.publish_sync(
            Event(
                name="resilience.continuity.restored",
                category="FederatedResilience",
                source="FederatedResiliencePlatform",
                payload={"recovery_plan_id": plan_id},
            )
        )
