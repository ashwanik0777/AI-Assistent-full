"""Enterprise Goal Manager for AIRA.

Manages persistent agent objectives, tracks status lifecycles, and resolves
parent/child relationship chains.
"""

import uuid
from datetime import datetime
from typing import Any, Literal

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.goal_manager")

GoalState = Literal[
    "CREATED",
    "ANALYZING",
    "PLANNED",
    "READY",
    "IN_PROGRESS",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
    "ARCHIVED",
]

VALID_TRANSITIONS: dict[GoalState, list[GoalState]] = {
    "CREATED": ["ANALYZING", "CANCELLED"],
    "ANALYZING": ["PLANNED", "CANCELLED", "FAILED"],
    "PLANNED": ["READY", "CANCELLED", "FAILED"],
    "READY": ["IN_PROGRESS", "CANCELLED", "FAILED"],
    "IN_PROGRESS": ["COMPLETED", "FAILED", "CANCELLED"],
    "COMPLETED": ["ARCHIVED"],
    "FAILED": ["CREATED", "CANCELLED", "ARCHIVED"],
    "CANCELLED": ["CREATED", "ARCHIVED"],
    "ARCHIVED": [],
}


class GoalError(Exception):
    """Base exception for all Goal Manager failures."""

    pass


class InvalidGoalError(GoalError):
    """Raised when validating malformed goals or transition violations."""

    pass


class GoalObject:
    """Persistent objective containing metadata keys and relationships."""

    def __init__(
        self,
        brain_session_id: str,
        request_id: str,
        title: str,
        description: str,
        priority: int = 1,
        parent_goal_id: str | None = None,
        estimated_complexity: str = "MEDIUM",
        required_skills: list[str] | None = None,
        required_permissions: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.goal_id: str = uuid.uuid4().hex
        self.brain_session_id = brain_session_id
        self.request_id = request_id
        self.title = title
        self.description = description
        self.priority = priority
        self.current_state: GoalState = "CREATED"
        self.creation_time: datetime = datetime.now()
        self.last_update: datetime = datetime.now()

        self.parent_goal_id = parent_goal_id
        self.child_goal_ids: list[str] = []
        self.related_request_ids: list[str] = [request_id]

        self.estimated_complexity = estimated_complexity
        self.required_skills: list[str] = required_skills or []
        self.required_permissions: list[str] = required_permissions or []
        self.metadata: dict[str, Any] = metadata or {}

    def update_state(self, new_state: GoalState) -> None:
        """Progress state while keeping historical tracks."""
        self.current_state = new_state
        self.last_update = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        """Serialize goal properties."""
        return {
            "goal_id": self.goal_id,
            "brain_session_id": self.brain_session_id,
            "request_id": self.request_id,
            "title": self.title,
            "description": self.description,
            "priority": self.priority,
            "current_state": self.current_state,
            "creation_time": self.creation_time.isoformat(),
            "last_update": self.last_update.isoformat(),
            "parent_goal_id": self.parent_goal_id,
            "child_goal_ids": self.child_goal_ids,
            "related_request_ids": self.related_request_ids,
            "estimated_complexity": self.estimated_complexity,
            "required_skills": self.required_skills,
            "required_permissions": self.required_permissions,
            "metadata": self.metadata,
        }


class GoalRegistry:
    """Maintains active registry mappings of transient and long-lived goal objectives."""

    def __init__(self) -> None:
        self._goals: dict[str, GoalObject] = {}

    def register(self, goal: GoalObject) -> None:
        """Add goal to register."""
        if goal.goal_id in self._goals:
            raise InvalidGoalError(f"Duplicate goal registry check failed for ID: {goal.goal_id}")
        self._goals[goal.goal_id] = goal

    def get(self, goal_id: str) -> GoalObject | None:
        """Fetch goal by ID."""
        return self._goals.get(goal_id)

    def list_all(self) -> list[GoalObject]:
        """Fetch list of all goals."""
        return list(self._goals.values())

    def remove(self, goal_id: str) -> None:
        """Remove goal from registry."""
        if goal_id in self._goals:
            del self._goals[goal_id]


class GoalValidator:
    """Performs relationships checks, asserts unique keys, and validates transitions constraints."""

    @staticmethod
    def validate_transition(current: GoalState, target: GoalState) -> None:
        """Ensure state progression meets lifecycle paths. Raises InvalidGoalError."""
        if target not in VALID_TRANSITIONS.get(current, []):
            raise InvalidGoalError(f"Forbidden goal state transition from {current} to {target}.")

    @staticmethod
    def validate_parent_relationships(goal_id: str, registry: GoalRegistry) -> None:
        """Detect circular parent dependencies using DFS tree searches."""
        visited = set()
        current = registry.get(goal_id)

        while current and current.parent_goal_id:
            if current.parent_goal_id in visited:
                raise InvalidGoalError("Circular parent relationship detected inside goals chain.")
            visited.add(current.parent_goal_id)
            current = registry.get(current.parent_goal_id)


class GoalManager:
    """Coordinates goal registry lifecycles, states transitions, merges, and event notifications."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.goal_registry = GoalRegistry()
        self.validator = GoalValidator()

    def create_goal(
        self,
        brain_session_id: str,
        request_id: str,
        title: str,
        description: str,
        priority: int = 1,
        parent_goal_id: str | None = None,
    ) -> GoalObject:
        """Initialize, validate, register, and notify new goal objective instances."""
        goal = GoalObject(
            brain_session_id=brain_session_id,
            request_id=request_id,
            title=title,
            description=description,
            priority=priority,
            parent_goal_id=parent_goal_id,
        )

        # Wire child relationship if parent specified
        if parent_goal_id:
            parent = self.goal_registry.get(parent_goal_id)
            if not parent:
                raise InvalidGoalError(f"Parent goal {parent_goal_id} not registered.")
            parent.child_goal_ids.append(goal.goal_id)

        self.goal_registry.register(goal)
        self.validator.validate_parent_relationships(goal.goal_id, self.goal_registry)

        self.event_bus.publish_sync(
            Event(
                name="goal_manager.goal_created",
                category="Brain",
                source="GoalManager",
                payload=goal.to_dict(),
            )
        )

        logger.info("Goal created successfully", goal_id=goal.goal_id, title=title)
        return goal

    def update_goal_state(self, goal_id: str, target_state: GoalState) -> None:
        """Progress state while executing check rules and routing notifications."""
        goal = self.goal_registry.get(goal_id)
        if not goal:
            raise InvalidGoalError(f"Goal {goal_id} does not exist.")

        self.validator.validate_transition(goal.current_state, target_state)
        old_state = goal.current_state
        goal.update_state(target_state)

        event_name = f"goal_manager.goal_{target_state.lower()}"
        # Fallback names if not matching standard placeholders
        if target_state == "PLANNED":
            event_name = "goal_manager.goal_planned"
        elif target_state == "CANCELLED":
            event_name = "goal_manager.goal_cancelled"

        self.event_bus.publish_sync(
            Event(
                name=event_name,
                category="Brain",
                source="GoalManager",
                payload={
                    "goal_id": goal.goal_id,
                    "old_state": old_state,
                    "new_state": target_state,
                },
            )
        )

    def merge_goals(self, source_goal_id: str, target_goal_id: str) -> None:
        """Merge relations and requests of source goal into target, then remove source."""
        source = self.goal_registry.get(source_goal_id)
        target = self.goal_registry.get(target_goal_id)

        if not source or not target:
            raise GoalError("Merge rejected: source or target goal missing.")

        # Consolidate requests and descriptions
        target.related_request_ids.extend(source.related_request_ids)
        target.description += f" | Merged source description: {source.description}"
        target.child_goal_ids.extend(source.child_goal_ids)

        self.goal_registry.remove(source_goal_id)

        self.event_bus.publish_sync(
            Event(
                name="goal_manager.goal_updated",
                category="Brain",
                source="GoalManager",
                payload={"goal_id": target.goal_id, "action": "MERGE"},
            )
        )
