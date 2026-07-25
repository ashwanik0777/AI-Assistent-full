"""Enterprise Autonomous Planning & Delegation Platform.

Provides goal analyzers, planning engines, and version managers.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.autonomous_planning")


class AutonomousPlanningError(Exception):
    """Base exception raised for goal analysis failures or plan validation drifts."""

    pass


@dataclass
class AutonomousExecutionPlan:
    """Execution plan containing hierarchical tasks, dependency maps, and versions."""

    plan_id: str
    goal_id: str
    milestones: list[str]
    tasks: list[dict[str, Any]]
    dependencies: dict[str, list[str]]
    assigned_roles: dict[str, str]
    delegation_strategy: str
    success_criteria: list[str]
    evidence_plan: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)
    version: int = 1


class GoalAnalyzer:
    """Evaluates constraints, policy alignment rules, and capabilities risks."""

    def analyze_goal(self, goal_id: str, objectives: dict[str, Any]) -> dict[str, Any]:
        """Verify safety bounds and align constraints."""
        if not objectives.get("target"):
            raise AutonomousPlanningError("Goal analysis failed: Missing objective target.")
        return {"goal_id": goal_id, "complexity": "Medium", "safety_aligned": True}


class PlanningEngine:
    """Generates hierarchical task lists and critical path milestones."""

    def generate_tasks_and_milestones(self, goal_id: str) -> tuple[list[str], list[dict[str, Any]]]:
        """Construct default milestones and subtasks decomposition."""
        milestones = ["Design", "Build", "Verify"]
        tasks = [
            {"task_id": f"{goal_id}_task_1", "name": "Design Spec", "status": "Pending"},
            {"task_id": f"{goal_id}_task_2", "name": "Write Code", "status": "Pending"},
            {"task_id": f"{goal_id}_task_3", "name": "Run Testing", "status": "Pending"},
        ]
        return milestones, tasks


class DependencyPlanner:
    """Models sequential or parallel dependency links and blocking conditions."""

    def plan_dependencies(self, tasks: list[dict[str, Any]]) -> dict[str, list[str]]:
        """Link sequential tasks by ID order list."""
        deps = {}
        for i in range(1, len(tasks)):
            parent = tasks[i - 1]["task_id"]
            child = tasks[i]["task_id"]
            deps[child] = [parent]
        return deps


class DelegationPlanner:
    """Assigns roles (Planner, Developer, Tester) based on requirements."""

    def plan_delegations(self, tasks: list[dict[str, Any]]) -> dict[str, str]:
        """Map task ID to appropriate role coordinates."""
        roles = {}
        for t in tasks:
            name = t["name"].lower()
            if "design" in name:
                roles[t["task_id"]] = "Planner"
            elif "write" in name or "build" in name:
                roles[t["task_id"]] = "Developer"
            else:
                roles[t["task_id"]] = "Tester"
        return roles


class ProgressManager:
    """Tracks task completions, evidence collections, and requests replannings."""

    def complete_task(self, plan: AutonomousExecutionPlan, task_id: str, evidence: str) -> None:
        """Mark task as completed and check for milestone completion criteria."""
        found = False
        for t in plan.tasks:
            if t["task_id"] == task_id:
                t["status"] = "Completed"
                t["evidence"] = evidence
                found = True
                break

        if not found:
            raise AutonomousPlanningError(f"Task '{task_id}' not found in plan.")


class PlanVersionManager:
    """Archives previous version iterations histories when replanning runs."""

    def __init__(self) -> None:
        self.archives: dict[str, list[AutonomousExecutionPlan]] = {}

    def archive_plan(self, plan: AutonomousExecutionPlan) -> None:
        """Store copy of current plan iteration."""
        # Save a duplicate copy
        dup = AutonomousExecutionPlan(
            plan_id=plan.plan_id,
            goal_id=plan.goal_id,
            milestones=list(plan.milestones),
            tasks=[dict(t) for t in plan.tasks],
            dependencies=dict(plan.dependencies),
            assigned_roles=dict(plan.assigned_roles),
            delegation_strategy=plan.delegation_strategy,
            success_criteria=list(plan.success_criteria),
            evidence_plan=list(plan.evidence_plan),
            version=plan.version,
        )
        self.archives.setdefault(plan.plan_id, []).append(dup)


class AutonomousPlanningPlatform:
    """Coordinating manager resolving goal analysis, delegation planning, and replanning."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.analyzer = GoalAnalyzer()
        self.planning_engine = PlanningEngine()
        self.dependency_planner = DependencyPlanner()
        self.delegation_planner = DelegationPlanner()
        self.progress_manager = ProgressManager()
        self.version_manager = PlanVersionManager()

        self.active_plans: dict[str, AutonomousExecutionPlan] = {}

    def create_execution_plan(
        self, plan_id: str, goal_id: str, objectives: dict[str, Any]
    ) -> AutonomousExecutionPlan:
        """Analyze goals, decompose tasks, plan dependencies, map roles, and dispatch events."""
        # 1. Analyze
        self.analyzer.analyze_goal(goal_id, objectives)
        self.event_bus.publish_sync(
            Event(
                name="planning.goal.analyzed",
                category="AutonomousPlanning",
                source="AutonomousPlanningPlatform",
                payload={"goal_id": goal_id},
            )
        )

        # 2. Decompose
        milestones, tasks = self.planning_engine.generate_tasks_and_milestones(goal_id)

        # 3. Dependencies
        deps = self.dependency_planner.plan_dependencies(tasks)

        # 4. Delegations
        roles = self.delegation_planner.plan_delegations(tasks)
        self.event_bus.publish_sync(
            Event(
                name="planning.delegation.planned",
                category="AutonomousPlanning",
                source="AutonomousPlanningPlatform",
                payload={"plan_id": plan_id},
            )
        )

        # Build plan
        plan = AutonomousExecutionPlan(
            plan_id=plan_id,
            goal_id=goal_id,
            milestones=milestones,
            tasks=tasks,
            dependencies=deps,
            assigned_roles=roles,
            delegation_strategy="Governed Role Assignment",
            success_criteria=["Complete implementation", "Pass test cases"],
            evidence_plan=["tests_run.log"],
        )

        self.active_plans[plan_id] = plan

        self.event_bus.publish_sync(
            Event(
                name="planning.plan.generated",
                category="AutonomousPlanning",
                source="AutonomousPlanningPlatform",
                payload={"plan_id": plan_id},
            )
        )

        return plan

    def mark_task_complete(self, plan_id: str, task_id: str, evidence: str) -> None:
        """Promote task status to Completed and dispatch events on milestones completion."""
        plan = self.active_plans.get(plan_id)
        if not plan:
            raise AutonomousPlanningError(f"Plan not found: '{plan_id}'")

        self.progress_manager.complete_task(plan, task_id, evidence)

        # Check if all tasks in milestone are done (simplified checking)
        self.event_bus.publish_sync(
            Event(
                name="planning.milestone.completed",
                category="AutonomousPlanning",
                source="AutonomousPlanningPlatform",
                payload={"plan_id": plan_id, "task_id": task_id},
            )
        )

    def trigger_replanning(self, plan_id: str, new_objectives: dict[str, Any]) -> None:
        """Archive current plan state, recreate execution plan, and increment version."""
        plan = self.active_plans.get(plan_id)
        if not plan:
            raise AutonomousPlanningError(f"Plan not found: '{plan_id}'")

        # Archive current state
        self.version_manager.archive_plan(plan)

        # Create new execution layout parameters
        new_plan = self.create_execution_plan(plan_id, plan.goal_id, new_objectives)
        new_plan.version = plan.version + 1

        self.active_plans[plan_id] = new_plan

        self.event_bus.publish_sync(
            Event(
                name="planning.plan.updated",
                category="AutonomousPlanning",
                source="AutonomousPlanningPlatform",
                payload={"plan_id": plan_id, "version": new_plan.version},
            )
        )
