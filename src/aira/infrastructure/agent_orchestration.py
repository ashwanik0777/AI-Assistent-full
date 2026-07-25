"""Enterprise Orchestration Engine & Execution Planning for AIRA.

Provides goal analysis, task graph sorting, checkpoints, and approvals.
"""

import time
from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.agent_orchestration")


class AgentOrchestrationError(Exception):
    """Raised when goal planning, dependencies validation, or approvals gating fail."""

    pass


@dataclass
class ExecutionPlan:
    """Consolidated representation defining tasks, dependency graphs and assigned agents."""

    plan_id: str
    goal_id: str
    task_list: list[dict[str, Any]]
    dependencies: dict[str, list[str]]
    assigned_agents: dict[str, str] = field(default_factory=dict)
    success_criteria: str = "All Tasks Completed"
    rollback_rules: list[str] = field(default_factory=list)
    approval_gates: list[str] = field(default_factory=list)
    priority: int = 5
    lifecycle_state: str = "Created"
    metadata: dict[str, Any] = field(default_factory=dict)
    version: str = "1.0.0"


@dataclass
class Checkpoint:
    """Historical checkpoint snapshot representing execution variables progress."""

    checkpoint_id: str
    plan_id: str
    timestamp: float = field(default_factory=time.time)
    state_snapshot: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class GoalAnalyzer:
    """Deconstructs user prompt objectives into structured task capabilities requirements."""

    def analyze_goal(self, goal_id: str, goal_prompt: str) -> dict[str, Any]:
        """Parse text prompt to infer requirements criteria."""
        if not goal_prompt:
            raise AgentOrchestrationError("Goal analysis failed: Prompt cannot be empty.")

        # Simple keyword matching inference
        prompt_lower = goal_prompt.lower()
        needs_write = "generate" in prompt_lower or "write" in prompt_lower
        required_roles = ["Planner"]
        if needs_write:
            required_roles.append("Developer")
        required_roles.append("Reviewer")

        return {
            "goal_id": goal_id,
            "required_roles": required_roles,
            "tasks_needed": (
                ["AnalyzeRepo"] + (["WriteReport"] if needs_write else []) + ["ReviewReport"]
            ),
        }


class ExecutionPlanner:
    """Assembles goal specifications into queryable ExecutionPlans."""

    def build_plan(self, plan_id: str, goal_analysis: dict[str, Any]) -> ExecutionPlan:
        """Construct standard execution plan with target tasks and dependencies mappings."""
        tasks = []
        deps = {}

        tasks_needed = goal_analysis["tasks_needed"]
        for i, task_name in enumerate(tasks_needed):
            tasks.append(
                {
                    "task_id": f"t_{task_name.lower()}",
                    "name": task_name,
                    "role_needed": goal_analysis["required_roles"][
                        min(i, len(goal_analysis["required_roles"]) - 1)
                    ],
                }
            )
            # Linear chain dependencies as default
            if i > 0:
                deps[f"t_{task_name.lower()}"] = [f"t_{tasks_needed[i - 1].lower()}"]
            else:
                deps[f"t_{task_name.lower()}"] = []

        # High-risk detection: if write tasks are involved, add approval gates
        gates = []
        if len(tasks_needed) > 2:
            gates.append("t_reviewreport")

        return ExecutionPlan(
            plan_id=plan_id,
            goal_id=goal_analysis["goal_id"],
            task_list=tasks,
            dependencies=deps,
            approval_gates=gates,
        )


class TaskGraphEngine:
    """Validates loop closures and computes topological sorts of task dependencies."""

    def resolve_topological_order(self, plan: ExecutionPlan) -> list[str]:
        """Sort tasks by dependency resolving paths to detect circular routes."""
        resolved = []
        visited = set()
        temp_visited = set()

        def visit(task_id: str) -> None:
            if task_id in temp_visited:
                raise AgentOrchestrationError("Circular dependency detected in task graph.")
            if task_id not in visited:
                temp_visited.add(task_id)
                for dep in plan.dependencies.get(task_id, []):
                    visit(dep)
                temp_visited.remove(task_id)
                visited.add(task_id)
                resolved.append(task_id)

        for task in plan.task_list:
            visit(task["task_id"])

        return resolved


class AgentAssignmentEngine:
    """Selects matching agents based on registries capabilities and version health tags."""

    def assign_agents(self, plan: ExecutionPlan, registry: Any) -> None:
        """Query agent registry to assign agents to tasks."""
        for task in plan.task_list:
            role = task["role_needed"]
            # Lookup in registry
            assigned_id = None
            for record in registry.list_all():
                if record.role == role and record.lifecycle_state == "Ready":
                    assigned_id = record.agent_id
                    break
            if not assigned_id:
                raise AgentOrchestrationError(
                    f"Agent Assignment failed: No Ready agent matches role '{role}'."
                )
            plan.assigned_agents[task["task_id"]] = assigned_id


class CheckpointManager:
    """Saves checkpoints progress snapshots and triggers rollbacks checks."""

    def __init__(self) -> None:
        self.checkpoints: dict[str, Checkpoint] = {}

    def save_checkpoint(
        self, checkpoint_id: str, plan_id: str, snapshot: dict[str, Any]
    ) -> Checkpoint:
        """Create new checkpoint save progress snapshot."""
        cp = Checkpoint(checkpoint_id=checkpoint_id, plan_id=plan_id, state_snapshot=snapshot)
        self.checkpoints[checkpoint_id] = cp
        return cp


class ApprovalGate:
    """Manages authorization requirements, updating gates logs flags."""

    def __init__(self) -> None:
        self.approvals: dict[str, str] = {}  # Map of task_id -> status (Pending, Approved, Denied)

    def request_approval(self, task_id: str) -> None:
        """Register task as waiting for authorization approval."""
        self.approvals[task_id] = "Pending"

    def approve(self, task_id: str) -> None:
        """Approve task execution permission."""
        if task_id in self.approvals:
            self.approvals[task_id] = "Approved"


class OrchestrationEngine:
    """Coordinator translating prompts into sorted execution graphs and gates."""

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

        self.analyzer = GoalAnalyzer()
        self.planner = ExecutionPlanner()
        self.graph_engine = TaskGraphEngine()
        self.assignment_engine = AgentAssignmentEngine()
        self.checkpoint_manager = CheckpointManager()
        self.approval_gate = ApprovalGate()

    def orchestrate_goal(self, goal_id: str, prompt: str) -> ExecutionPlan:
        """Run complete planning orchestration pipeline."""
        # 1. Goal Analysis
        analysis = self.analyzer.analyze_goal(goal_id, prompt)

        # 2. Plan Build
        plan_id = f"plan_{goal_id}"
        plan = self.planner.build_plan(plan_id, analysis)
        self.event_bus.publish_sync(
            Event(
                name="plan.created",
                category="Orchestration",
                source="AgentOrchestrator",
                payload={"plan_id": plan_id, "goal_id": goal_id},
            )
        )

        # 3. Task Graph Resolve
        self.graph_engine.resolve_topological_order(plan)

        # 4. Agent Assignment
        if self.agent_registry:
            self.assignment_engine.assign_agents(plan, self.agent_registry)

        plan.lifecycle_state = "Planned"

        # 5. Create Checkpoint
        cp_id = f"cp_{plan_id}_init"
        self.checkpoint_manager.save_checkpoint(cp_id, plan_id, {"plan_state": "Planned"})
        self.event_bus.publish_sync(
            Event(
                name="checkpoint.saved",
                category="Orchestration",
                source="AgentOrchestrator",
                payload={"checkpoint_id": cp_id, "plan_id": plan_id},
            )
        )

        return plan

    def run_plan_step(self, plan: ExecutionPlan, task_id: str) -> None:
        """Check approval gates before coordinating task scheduler items."""
        # Check approval gate
        if task_id in plan.approval_gates:
            gate_status = self.approval_gate.approvals.get(task_id)
            if not gate_status:
                self.approval_gate.request_approval(task_id)
                self.event_bus.publish_sync(
                    Event(
                        name="approval.requested",
                        category="Orchestration",
                        source="AgentOrchestrator",
                        payload={"plan_id": plan.plan_id, "task_id": task_id},
                    )
                )
                plan.lifecycle_state = "Waiting"
                raise AgentOrchestrationError(
                    f"Execution Paused: Task '{task_id}' requires approval."
                )

            if gate_status != "Approved":
                raise AgentOrchestrationError(
                    f"Execution Paused: Task '{task_id}' is waiting for approval."
                )

        # Simulate execution step
        self.event_bus.publish_sync(
            Event(
                name="task.scheduled",
                category="Orchestration",
                source="AgentOrchestrator",
                payload={"plan_id": plan.plan_id, "task_id": task_id},
            )
        )
