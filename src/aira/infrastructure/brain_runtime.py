"""Enterprise Brain Runtime Integration for AIRA.

Coordinates request lifecycles through model router, reasoning translator,
goal manager, planner, DAG builder, and schedule executor queues inside
safe sandboxed simulations.
"""

from typing import Any

import structlog

from aira.infrastructure.brain_core import BrainManager
from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.execution_planner import ExecutionPlannerManager
from aira.infrastructure.goal_manager import GoalManager
from aira.infrastructure.model_router import ModelRouterManager
from aira.infrastructure.planner import PlannerManager
from aira.infrastructure.reasoning_interface import ReasoningManager
from aira.infrastructure.service_registry import ServiceRegistry
from aira.infrastructure.task_graph import TaskGraphManager

logger = structlog.get_logger("aira.brain_runtime")


class BrainPipelineError(Exception):
    """Base exception for all end-to-end brain pipeline failures."""

    pass


class BrainRuntimePipeline:
    """Orchestrates the entire Brain thinking pipeline simulation flow."""

    def __init__(
        self,
        config: AppConfig,
        registry: ServiceRegistry,
        event_bus: EventBus,
        brain_core: BrainManager,
        model_router: ModelRouterManager,
        reasoning: ReasoningManager,
        goal_manager: GoalManager,
        planner: PlannerManager,
        task_graph: TaskGraphManager,
        execution_planner: ExecutionPlannerManager,
    ) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        # Dependencies
        self.brain_core = brain_core
        self.model_router = model_router
        self.reasoning = reasoning
        self.goal_manager = goal_manager
        self.planner = planner
        self.task_graph = task_graph
        self.execution_planner = execution_planner

        self.event_bus.publish_sync(
            Event(
                name="brain_runtime.ready",
                category="Brain",
                source="BrainRuntimePipeline",
                payload={},
            )
        )

    def execute_pipeline(
        self, prompt: str, request_id: str, brain_session_id: str
    ) -> dict[str, Any]:
        """Execute the end-to-end brain execution simulation workflow."""
        if not request_id.strip() or not brain_session_id.strip():
            raise BrainPipelineError("Request ID and Brain Session ID context must be defined.")

        self.event_bus.publish_sync(
            Event(
                name="brain_runtime.pipeline_started",
                category="Brain",
                source="BrainRuntimePipeline",
                payload={"request_id": request_id, "brain_session_id": brain_session_id},
            )
        )

        try:
            # 1. Model Router Layer
            raw_response = self.model_router.route_request(prompt)

            # 2. Reasoning Layer
            reasoning_obj = self.reasoning.process_response(
                raw_response,
                request_id,
                brain_session_id,
                self.model_router.provider_registry.list_all()[0].metadata.provider_id,
            )
            self.event_bus.publish_sync(
                Event(
                    name="brain_runtime.reasoning_completed",
                    category="Brain",
                    source="BrainRuntimePipeline",
                    payload={"reasoning_id": reasoning_obj.reasoning_id},
                )
            )

            # 3. Goal Layer
            goal_obj = self.goal_manager.create_goal(
                brain_session_id=brain_session_id,
                request_id=request_id,
                title=reasoning_obj.detected_intent or "Simulated Goal Title",
                description=reasoning_obj.summary,
            )
            self.event_bus.publish_sync(
                Event(
                    name="brain_runtime.goal_created",
                    category="Brain",
                    source="BrainRuntimePipeline",
                    payload={"goal_id": goal_obj.goal_id},
                )
            )

            # 4. Planning Layer
            self.goal_manager.update_goal_state(goal_obj.goal_id, "ANALYZING")
            plan_obj = self.planner.generate_plan(reasoning_obj)
            self.goal_manager.update_goal_state(goal_obj.goal_id, "PLANNED")
            self.event_bus.publish_sync(
                Event(
                    name="brain_runtime.plan_created",
                    category="Brain",
                    source="BrainRuntimePipeline",
                    payload={"plan_id": plan_obj.plan_id},
                )
            )

            # 5. Task Graph Layer
            graph_obj = self.task_graph.generate_graph(plan_obj)
            self.event_bus.publish_sync(
                Event(
                    name="brain_runtime.graph_built",
                    category="Brain",
                    source="BrainRuntimePipeline",
                    payload={"graph_id": graph_obj.graph_id},
                )
            )

            # 6. Execution Planner Layer
            schedule_obj = self.execution_planner.generate_schedule(graph_obj, "SEQUENTIAL")
            self.goal_manager.update_goal_state(goal_obj.goal_id, "READY")
            self.event_bus.publish_sync(
                Event(
                    name="brain_runtime.schedule_ready",
                    category="Brain",
                    source="BrainRuntimePipeline",
                    payload={"schedule_id": schedule_obj.schedule_id},
                )
            )

            # 7. Sandbox Preview compilation (No OS execution should occur)
            sandbox_preview = {
                "goal": goal_obj.title,
                "plan_summary": reasoning_obj.summary,
                "execution_steps": [
                    {
                        "step_id": item.task_node_id,
                        "order": item.execution_order,
                        "title": f"Action target: {item.required_capability}",
                        "status": "SANDBOX_SIMULATED",
                    }
                    for item in schedule_obj.execution_queue
                ],
                "required_skills": plan_obj.required_skills,
                "required_permissions": plan_obj.required_permissions,
                "estimated_duration": schedule_obj.estimated_duration,
                "complexity": plan_obj.estimated_complexity,
                "warnings": [],
                "blocked_steps": [],
                "future_execution_status": "READY_FOR_ENGINE",
            }

            self.event_bus.publish_sync(
                Event(
                    name="brain_runtime.sandbox_generated",
                    category="Brain",
                    source="BrainRuntimePipeline",
                    payload={"sandbox_preview": sandbox_preview},
                )
            )

            self.event_bus.publish_sync(
                Event(
                    name="brain_runtime.finished",
                    category="Brain",
                    source="BrainRuntimePipeline",
                    payload={"request_id": request_id},
                )
            )

            logger.info("Brain simulation pipeline executed successfully", request_id=request_id)
            return sandbox_preview

        except Exception as e:
            logger.error("Brain pipeline simulation execution failed", error=str(e))
            self.event_bus.publish_sync(
                Event(
                    name="brain_runtime.failed",
                    category="Brain",
                    source="BrainRuntimePipeline",
                    payload={"error": str(e)},
                )
            )
            raise BrainPipelineError(f"Pipeline flow failed: {e}") from e
