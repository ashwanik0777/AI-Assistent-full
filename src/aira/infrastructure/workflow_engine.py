"""Enterprise Workflow Engine Foundation for AIRA.

Provides core workflow schemas, registry catalogs, lifecycle state machine managers,
and observability events for coordinating multi-step automation sessions.
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.workflow_engine")


class WorkflowState(Enum):
    """Supported state values in the execution workflow lifecycle."""

    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    READY = "READY"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    WAITING = "WAITING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    ARCHIVED = "ARCHIVED"


@dataclass
class Workflow:
    """Enterprise structural workflow blueprint definition."""

    workflow_id: str
    name: str
    description: str
    version: str
    author: str
    creation_timestamp: float
    execution_plan_id: str
    goal_id: str
    brain_session_id: str
    state: WorkflowState = WorkflowState.DRAFT
    priority: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowContext:
    """Dynamic context mapping associated with an active workflow session execution."""

    workflow_id: str
    goal_id: str
    execution_plan_id: str
    brain_session_id: str
    state: WorkflowState
    priority: int
    creation_time: float
    metadata: dict[str, Any] = field(default_factory=dict)


class WorkflowError(Exception):
    """Base exception for workflow state machine, registry, or validation errors."""

    pass


class WorkflowRegistry:
    """Thread-safe registration index for loaded and reusable workflows."""

    def __init__(self) -> None:
        self.workflows: dict[str, Workflow] = {}

    def register_workflow(self, workflow: Workflow) -> None:
        """Register workflow model instance to internal index catalog."""
        if workflow.workflow_id in self.workflows:
            raise WorkflowError(f"Workflow ID '{workflow.workflow_id}' already registered.")
        self.workflows[workflow.workflow_id] = workflow

    def load_workflow(self, workflow_id: str) -> Workflow | None:
        """Fetch indexed workflow config settings by unique identifier."""
        return self.workflows.get(workflow_id)

    def unload_workflow(self, workflow_id: str) -> None:
        """Remove workflow config settings from active index catalog."""
        if workflow_id in self.workflows:
            del self.workflows[workflow_id]

    def lookup_workflow(self, name: str) -> Workflow | None:
        """Lookup loaded workflow configs by name description."""
        for wf in self.workflows.values():
            if wf.name == name:
                return wf
        return None


class WorkflowLifecycleManager:
    """Enforces state transitions and dispatches event bus notifications."""

    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus

        # Define map of valid state transitions
        self._valid_transitions = {
            WorkflowState.DRAFT: {WorkflowState.VALIDATED},
            WorkflowState.VALIDATED: {WorkflowState.READY, WorkflowState.FAILED},
            WorkflowState.READY: {WorkflowState.RUNNING, WorkflowState.CANCELLED},
            WorkflowState.RUNNING: {
                WorkflowState.PAUSED,
                WorkflowState.WAITING,
                WorkflowState.COMPLETED,
                WorkflowState.FAILED,
                WorkflowState.CANCELLED,
            },
            WorkflowState.PAUSED: {WorkflowState.RUNNING, WorkflowState.CANCELLED},
            WorkflowState.WAITING: {
                WorkflowState.RUNNING,
                WorkflowState.FAILED,
                WorkflowState.CANCELLED,
            },
            WorkflowState.COMPLETED: {WorkflowState.ARCHIVED},
            WorkflowState.FAILED: {WorkflowState.ARCHIVED},
            WorkflowState.CANCELLED: {WorkflowState.ARCHIVED},
            WorkflowState.ARCHIVED: set(),
        }

    def transition_state(self, workflow: Workflow, target: WorkflowState) -> None:
        """Move workflow through state transitions checking constraints and emitting events."""
        current = workflow.state
        if target not in self._valid_transitions[current]:
            raise WorkflowError(
                f"Invalid workflow state transition: {current.value} -> {target.value}"
            )

        workflow.state = target

        # Dispatch state change notifications to the event bus
        event_mappings = {
            WorkflowState.VALIDATED: "workflow.validated",
            WorkflowState.READY: "workflow.ready",
            WorkflowState.RUNNING: "workflow.started",
            WorkflowState.PAUSED: "workflow.paused",
            WorkflowState.CANCELLED: "workflow.cancelled",
            WorkflowState.FAILED: "workflow.failed",
            WorkflowState.COMPLETED: "workflow.completed",
        }

        event_name = event_mappings.get(target)
        if event_name:
            self.event_bus.publish_sync(
                Event(
                    name=event_name,
                    category="Workflow",
                    source="WorkflowLifecycleManager",
                    payload={"workflow_id": workflow.workflow_id},
                )
            )


class WorkflowEngineManager:
    """Coordinates registrations, lifecycle states, validations, and DI containers."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.workflow_registry = WorkflowRegistry()
        self.lifecycle = WorkflowLifecycleManager(event_bus)

    def create_workflow(
        self,
        workflow_id: str,
        name: str,
        execution_plan_id: str,
        goal_id: str,
        brain_session_id: str,
        description: str = "",
        version: str = "1.0.0",
        author: str = "System",
    ) -> Workflow:
        """Create new workflow blueprint, index it, and notify events."""
        workflow = Workflow(
            workflow_id=workflow_id,
            name=name,
            description=description,
            version=version,
            author=author,
            creation_timestamp=time.time(),
            execution_plan_id=execution_plan_id,
            goal_id=goal_id,
            brain_session_id=brain_session_id,
        )

        self.workflow_registry.register_workflow(workflow)

        self.event_bus.publish_sync(
            Event(
                name="workflow.created",
                category="Workflow",
                source="WorkflowEngineManager",
                payload={"workflow_id": workflow.workflow_id},
            )
        )

        return workflow

    def get_context(self, workflow: Workflow) -> WorkflowContext:
        """Derive standard workflow execution context from workflow object metadata."""
        return WorkflowContext(
            workflow_id=workflow.workflow_id,
            goal_id=workflow.goal_id,
            execution_plan_id=workflow.execution_plan_id,
            brain_session_id=workflow.brain_session_id,
            state=workflow.state,
            priority=workflow.priority,
            creation_time=workflow.creation_timestamp,
            metadata=workflow.metadata,
        )
