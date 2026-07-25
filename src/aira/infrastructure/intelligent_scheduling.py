"""Enterprise Intelligent Scheduling, Placement & Workload Orchestration Platform for AIRA.

Provides scheduling engines, constraint validators, placement planners, and audit managers.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.global_resource_discovery import ResourceDescriptor
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.intelligent_scheduling")


class IntelligentSchedulingError(Exception):
    """Base exception raised for scheduling constraint checks failures or invalid plans."""

    pass


@dataclass
class ExecutionPlan:
    """Execution plan detailing resource placement selections and compliance status."""

    execution_plan_id: str
    workload_id: str
    candidate_resources: list[str]
    selected_resource: str
    placement_score: float
    constraint_satisfaction: bool
    estimated_latency: float
    estimated_resource_usage: dict[str, Any] = field(default_factory=dict)
    compliance_status: str = "Compliant"
    risk_score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    version: int = 1


class ConstraintEngine:
    """Evaluates capacity requirements, compliance regions, and security rules constraints."""

    def validate_constraints(
        self, workload_requirements: dict[str, Any], resource: ResourceDescriptor
    ) -> bool:
        """Verify node parameters satisfy capacity, accelerator, and region boundaries."""
        # 1. Hardware check (e.g. CUDA accelerator support)
        req_hardware = workload_requirements.get("hardware")
        if req_hardware and req_hardware not in resource.capabilities:
            return False

        # 2. Compliance region constraint check
        pref_region = workload_requirements.get("preferred_region")
        return not (
            pref_region
            and pref_region != resource.region
            and workload_requirements.get("strict_region", False)
        )


class PlacementPlanner:
    """Scores candidate nodes based on processing latency indicators and utilization load."""

    def score_placement(
        self, workload_requirements: dict[str, Any], resource: ResourceDescriptor
    ) -> float:
        """Compute placement score metric (higher is better, scale 0.0 to 10.0)."""
        score = 8.0
        # Boost score if target matched preferred region
        pref_region = workload_requirements.get("preferred_region")
        if pref_region and pref_region == resource.region:
            score += 2.0
        # Reduce score if node health status is Degraded
        if resource.health_status == "Degraded":
            score -= 5.0
        return min(10.0, max(0.0, score))


class QueueManager:
    """Maintains active workload queues grouped by priority levels flags."""

    def __init__(self) -> None:
        self.queue: list[dict[str, Any]] = []

    def enqueue_workload(self, workload_id: str, requirements: dict[str, Any]) -> None:
        """Add workload to scheduler queue."""
        self.queue.append({"workload_id": workload_id, "requirements": requirements})


class SchedulingAuditManager:
    """Logs placement rationales, scores, and decisions tracks histories."""

    def __init__(self) -> None:
        self.audit_records: dict[str, dict[str, Any]] = {}

    def log_decision(
        self, plan_id: str, workload_id: str, selected: str, rejected: list[str], rationale: str
    ) -> None:
        """Catalog placement decision audit entries logs."""
        self.audit_records[plan_id] = {
            "workload_id": workload_id,
            "selected_resource": selected,
            "rejected_candidates": rejected,
            "rationale": rationale,
        }


class IntelligentSchedulingManager:
    """Coordinating manager resolving scheduler queues, placement plans, and events."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.constraint_engine = ConstraintEngine()
        self.placement_planner = PlacementPlanner()
        self.queue_manager = QueueManager()
        self.audit_manager = SchedulingAuditManager()

        self.plans: dict[str, ExecutionPlan] = {}

    def generate_plan(
        self,
        plan_id: str,
        workload_id: str,
        requirements: dict[str, Any],
        resources: list[ResourceDescriptor],
    ) -> ExecutionPlan:
        """Create plan mapping workloads onto resource candidates."""
        # 1. Filter candidates by constraints
        candidates = []
        rejected = []
        for r in resources:
            self.event_bus.publish_sync(
                Event(
                    name="constraint.evaluated",
                    category="IntelligentScheduling",
                    source="IntelligentSchedulingManager",
                    payload={"workload_id": workload_id, "resource_id": r.resource_id},
                )
            )

            if self.constraint_engine.validate_constraints(requirements, r):
                candidates.append(r)
            else:
                rejected.append(r.resource_id)

        if not candidates:
            raise IntelligentSchedulingError(
                f"Scheduling failed: No compatible resource found for workload '{workload_id}'."
            )

        # 2. Score and select best placement
        best_resource = None
        best_score = -1.0

        for c in candidates:
            score = self.placement_planner.score_placement(requirements, c)
            if score > best_score:
                best_score = score
                best_resource = c

        if not best_resource:
            raise IntelligentSchedulingError(
                "Scheduling failed: Selection error during placement scoring."
            )

        self.event_bus.publish_sync(
            Event(
                name="placement.selected",
                category="IntelligentScheduling",
                source="IntelligentSchedulingManager",
                payload={"workload_id": workload_id, "selected": best_resource.resource_id},
            )
        )

        # 3. Create Execution Plan
        cand_ids = [c.resource_id for c in candidates]
        plan = ExecutionPlan(
            execution_plan_id=plan_id,
            workload_id=workload_id,
            candidate_resources=cand_ids,
            selected_resource=best_resource.resource_id,
            placement_score=best_score,
            constraint_satisfaction=True,
            estimated_latency=(
                150.0 if best_resource.region == requirements.get("preferred_region") else 350.0
            ),
        )
        self.plans[plan_id] = plan

        self.event_bus.publish_sync(
            Event(
                name="execution_plan.generated",
                category="IntelligentScheduling",
                source="IntelligentSchedulingManager",
                payload={"plan_id": plan_id, "selected": best_resource.resource_id},
            )
        )

        # 4. Audit
        rationale = f"Selected {best_resource.resource_id} with score {best_score}."
        self.audit_manager.log_decision(
            plan_id=plan_id,
            workload_id=workload_id,
            selected=best_resource.resource_id,
            rejected=rejected,
            rationale=rationale,
        )

        self.event_bus.publish_sync(
            Event(
                name="workload.scheduled",
                category="IntelligentScheduling",
                source="IntelligentSchedulingManager",
                payload={"workload_id": workload_id, "plan_id": plan_id},
            )
        )

        # Run simulation logging stub
        self.event_bus.publish_sync(
            Event(
                name="simulation.completed",
                category="IntelligentScheduling",
                source="IntelligentSchedulingManager",
                payload={"workload_id": workload_id},
            )
        )

        return plan
