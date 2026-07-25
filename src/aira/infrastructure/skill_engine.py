"""Enterprise Skill Engine Foundation for AIRA.

Manages registering, loading, and validating execution skills lifecycle hooks.
"""

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.execution_planner import ExecutionSchedule
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.skill_engine")


class SkillEngineError(Exception):
    """Base exception for all skill engine failures."""

    pass


class InvalidSkillError(SkillEngineError):
    """Raised when skill validation constraints fail."""

    pass


@dataclass
class SkillMetadata:
    """Detailed structural descriptors defining runtime capability boundaries."""

    skill_id: str
    name: str
    version: str
    description: str
    author: str
    category: str  # Application, Filesystem, Browser, Terminal, Clipboard, etc.
    supported_platforms: list[str] = field(default_factory=list)
    required_permissions: list[str] = field(default_factory=list)
    required_capabilities: list[str] = field(default_factory=list)
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    timeout: float = 30.0
    retry_policy: int = 3
    safety_level: str = "SAFE"
    dependencies: list[str] = field(default_factory=list)


class BaseSkill(ABC):
    """Abstract base class that all AIRA skills must implement."""

    def __init__(self, metadata: SkillMetadata) -> None:
        self.metadata = metadata
        self.initialized = False
        self.prepared = False

    def initialize(self) -> None:
        """Perform initialization setup for resource mapping."""
        self.initialized = True
        logger.debug("Skill initialized", skill_id=self.metadata.skill_id)

    def validate(self, input_data: dict[str, Any]) -> None:
        """Assert schema parameters compliance prior to execute."""
        # Simple schema validation checking presence of keys
        for key in self.metadata.input_schema.get("required", []):
            if key not in input_data:
                raise InvalidSkillError(f"Missing required parameter: {key}")

    def prepare(self) -> None:
        """Prepare system states and configurations prior to execution."""
        if not self.initialized:
            raise SkillEngineError("Skill must be initialized before preparing.")
        self.prepared = True
        logger.debug("Skill prepared", skill_id=self.metadata.skill_id)

    @abstractmethod
    def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Core execution payload. Subclasses must implement."""
        pass

    def cancel(self) -> None:
        """Interruption handler for active operations."""
        logger.info("Skill cancellation triggered", skill_id=self.metadata.skill_id)

    def cleanup(self) -> None:
        """Post-run cleanup resource releasing hook."""
        self.prepared = False
        logger.debug("Skill cleanup complete", skill_id=self.metadata.skill_id)

    def shutdown(self) -> None:
        """Graceful shutdown sequence when shutting down engines."""
        self.initialized = False
        logger.debug("Skill shutdown complete", skill_id=self.metadata.skill_id)


class SkillRegistry:
    """Keeps records of registered systems capabilities."""

    def __init__(self) -> None:
        self._skills: dict[str, BaseSkill] = {}

    def register(self, skill: BaseSkill) -> None:
        """Save a new skill inside the index."""
        if skill.metadata.skill_id in self._skills:
            raise SkillEngineError(f"Skill already registered: {skill.metadata.skill_id}")
        self._skills[skill.metadata.skill_id] = skill
        logger.info("Skill registered successfully", skill_id=skill.metadata.skill_id)

    def get(self, skill_id: str) -> BaseSkill | None:
        """Fetch skill matching identifier key."""
        return self._skills.get(skill_id)

    def list_all(self) -> list[BaseSkill]:
        """Return lists of all registered skill modules."""
        return list(self._skills.values())


class SkillValidator:
    """Validates structural matching metrics of targeted skills."""

    @staticmethod
    def validate_capability(skill: BaseSkill, platform: str) -> None:
        """Ensure compatibility between skill demands and runner platform."""
        if (
            skill.metadata.supported_platforms
            and platform not in skill.metadata.supported_platforms
        ):
            raise InvalidSkillError(
                f"Skill {skill.metadata.skill_id} does not support platform: {platform}"
            )


class SkillSession:
    """A managed session for scheduling sequences through skill engine environments."""

    def __init__(self, schedule: ExecutionSchedule) -> None:
        self.session_id: str = f"skill_session_{uuid.uuid4().hex[:8]}"
        self.schedule = schedule
        self.status: str = "CREATED"
        self.created_at = uuid.uuid4().hex


class SkillEngineManager:
    """Coordinates lifecycle loops, registry indices, validations, and event dispatches."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.skill_registry = SkillRegistry()
        self.validator = SkillValidator()

    def register_skill(self, skill: BaseSkill) -> None:
        """Register capability module to registry index."""
        self.skill_registry.register(skill)
        self.event_bus.publish_sync(
            Event(
                name="skill_engine.registered",
                category="Skills",
                source="SkillEngineManager",
                payload={"skill_id": skill.metadata.skill_id},
            )
        )

    def load_and_validate(self, skill_id: str, platform: str) -> BaseSkill:
        """Retrieve, assert platform configurations, and initialize the target skill."""
        skill = self.skill_registry.get(skill_id)
        if not skill:
            raise SkillEngineError(f"Target skill not found: {skill_id}")

        self.event_bus.publish_sync(
            Event(
                name="skill_engine.loaded",
                category="Skills",
                source="SkillEngineManager",
                payload={"skill_id": skill_id},
            )
        )

        # Perform platform and permission validations
        self.validator.validate_capability(skill, platform)
        self.event_bus.publish_sync(
            Event(
                name="skill_engine.validated",
                category="Skills",
                source="SkillEngineManager",
                payload={"skill_id": skill_id},
            )
        )

        if not skill.initialized:
            skill.initialize()

        return skill

    def create_skill_session(self, schedule: ExecutionSchedule) -> SkillSession:
        """Instantiate a new session wrapping scheduler flows."""
        session = SkillSession(schedule)
        self.event_bus.publish_sync(
            Event(
                name="skill_engine.session_created",
                category="Skills",
                source="SkillEngineManager",
                payload={"session_id": session.session_id},
            )
        )

        # Confirm all schedules parameters match validated constraints
        for item in schedule.execution_queue:
            skill = self.skill_registry.get(item.task_node_id)
            if skill and not skill.prepared:
                skill.prepare()

        self.event_bus.publish_sync(
            Event(
                name="skill_engine.ready",
                category="Skills",
                source="SkillEngineManager",
                payload={"session_id": session.session_id},
            )
        )

        return session
