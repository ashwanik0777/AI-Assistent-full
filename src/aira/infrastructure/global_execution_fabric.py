"""Global Execution Fabric Foundation Platform for AIRA.

Provides execution planner engines and validation interfaces.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.global_execution_fabric")


class GlobalExecutionFabricError(Exception):
    """Base exception raised for planning errors, policy validation checks, or session failures."""

    pass


@dataclass
class ExecutionContext:
    """Context block specifying targets, configurations policies, and trace identifiers."""

    execution_id: str
    execution_target: str  # Local, On-Premise, Private Cloud, Public Cloud, Hybrid, Simulation
    region: str
    environment_type: str
    provider_reference: str
    policy_reference: str
    security_context: str
    metadata: dict[str, Any] = field(default_factory=dict)
    version: int = 1


class ExecutionPlanner:
    """Constructs execution plans and maps requests to target provider frameworks."""

    def plan_execution(self, execution_id: str, target: str, policy_ref: str) -> ExecutionContext:
        """Create new ExecutionContext with default settings."""
        if not execution_id:
            raise GlobalExecutionFabricError("Planning failed: Execution ID is required.")

        return ExecutionContext(
            execution_id=execution_id,
            execution_target=target,
            region="us-east-1",
            environment_type="container",
            provider_reference="provider_sim_01",
            policy_reference=policy_ref,
            security_context="role:executor",
        )


class ExecutionRoutingInterface:
    """Validates compatibility rules and enforces routing policies checks."""

    def validate_routing(self, context: ExecutionContext) -> None:
        """Reject routing plans if policy conflicts exist (e.g. strict local-only policy)."""
        # Enforcement: block Public Cloud target if policy is strict local
        is_cloud = context.execution_target in ("Public Cloud", "Private Cloud")
        if is_cloud and "local-only" in context.policy_reference.lower():
            raise GlobalExecutionFabricError(
                f"Routing failed: Policy '{context.policy_reference}' blocks cloud targets."
            )


class ExecutionSessionCoordinator:
    """Manages active execution sessions and records routing histories logs."""

    def __init__(self) -> None:
        self.active_sessions: dict[str, ExecutionContext] = {}
        self.history: list[str] = []

    def create_session(self, context: ExecutionContext) -> None:
        """Enroll active execution session tracker."""
        self.active_sessions[context.execution_id] = context
        self.history.append(context.execution_id)

    def close_session(self, execution_id: str) -> None:
        """Remove trace from active sessions."""
        if execution_id in self.active_sessions:
            del self.active_sessions[execution_id]


class GlobalExecutionFabric:
    """Coordinating manager resolving execution contexts, routes, and events."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.planner = ExecutionPlanner()
        self.router = ExecutionRoutingInterface()
        self.session_coordinator = ExecutionSessionCoordinator()

    def request_execution(
        self, execution_id: str, target: str, policy_ref: str
    ) -> ExecutionContext:
        """Plan request, validate routing, coordinate session, and publish events sync."""
        # 1. Plan
        context = self.planner.plan_execution(execution_id, target, policy_ref)

        self.event_bus.publish_sync(
            Event(
                name="execution.planned",
                category="GlobalExecutionFabric",
                source="GlobalExecutionFabric",
                payload={"execution_id": execution_id},
            )
        )

        # 2. Validate Routing
        self.router.validate_routing(context)

        self.event_bus.publish_sync(
            Event(
                name="routing.validated",
                category="GlobalExecutionFabric",
                source="GlobalExecutionFabric",
                payload={"execution_id": execution_id},
            )
        )

        # 3. Create Session
        self.session_coordinator.create_session(context)

        self.event_bus.publish_sync(
            Event(
                name="session.created",
                category="GlobalExecutionFabric",
                source="GlobalExecutionFabric",
                payload={"execution_id": execution_id, "target": target},
            )
        )

        self.event_bus.publish_sync(
            Event(
                name="execution.routed",
                category="GlobalExecutionFabric",
                source="GlobalExecutionFabric",
                payload={"execution_id": execution_id},
            )
        )

        return context

    def complete_execution(self, execution_id: str) -> None:
        """Close active session and publish completion log events."""
        self.session_coordinator.close_session(execution_id)

        self.event_bus.publish_sync(
            Event(
                name="execution.completed",
                category="GlobalExecutionFabric",
                source="GlobalExecutionFabric",
                payload={"execution_id": execution_id},
            )
        )
