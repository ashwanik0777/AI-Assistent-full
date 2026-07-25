"""Enterprise Procedural Memory Engine for AIRA.

Captures, validates, generalizes, and catalogs reusable task execution procedures.
"""

import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.procedural_memory")


class ProceduralMemoryError(Exception):
    """Raised when validation checks, generalization mappings, or library updates fail."""

    pass


class ProcedureState(Enum):
    """Lifecycle states of reusable procedures."""

    CREATED = "CREATED"
    VALIDATED = "VALIDATED"
    PUBLISHED = "PUBLISHED"
    UPDATED = "UPDATED"
    DEPRECATED = "DEPRECATED"
    ARCHIVED = "ARCHIVED"
    DELETED = "DELETED"


@dataclass
class ProcedureObject:
    """Enterprise parameterized procedure representation."""

    procedure_id: str
    name: str
    description: str
    goal: str
    supported_skills: list[str] = field(default_factory=list)
    required_capabilities: list[str] = field(default_factory=list)
    input_parameters: dict[str, Any] = field(default_factory=dict)
    expected_outputs: dict[str, Any] = field(default_factory=dict)
    version: str = "1.0.0"
    success_score: float = 1.0
    average_duration: float = 0.0
    failure_count: int = 0
    usage_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    state: ProcedureState = ProcedureState.CREATED


class ProcedureValidator:
    """Verifies parameterized structures compliance and versioning syntax."""

    def validate(self, proc: ProcedureObject) -> None:
        """Enforce validation rules checking properties."""
        if not proc.procedure_id:
            raise ProceduralMemoryError("Procedure validation failed: Missing ID.")

        if not proc.name or not proc.goal:
            raise ProceduralMemoryError("Procedure validation failed: Missing name or goal.")

        if not proc.version or len(proc.version.split(".")) != 3:
            raise ProceduralMemoryError(
                f"Invalid semantic versioning format syntax: '{proc.version}'."
            )


class ProcedureGeneralizer:
    """Translates workflow run details into parameterized template placeholders."""

    def generalize(self, raw_steps: list[dict[str, Any]], pattern: str) -> list[dict[str, Any]]:
        """Scan raw steps replacing targeted folders/parameters with general placeholder keys."""
        generalized = []
        for step in raw_steps:
            new_step = dict(step)
            # Generalize folder paths
            if "path" in new_step and pattern in new_step["path"]:
                new_step["path"] = new_step["path"].replace(pattern, "{workspace_dir}")
            generalized.append(new_step)
        return generalized


class SuccessAnalyzer:
    """Tracks run execution results, recalculates averages, and updates scoring."""

    def record_run(self, proc: ProcedureObject, duration: float, success: bool) -> None:
        """Increment count trackers and adjust scoring metrics."""
        proc.usage_count += 1
        if not success:
            proc.failure_count += 1

        # Calculate new average duration
        total_time = (proc.average_duration * (proc.usage_count - 1)) + duration
        proc.average_duration = round(total_time / proc.usage_count, 2)

        # Recalculate success score
        successes = proc.usage_count - proc.failure_count
        proc.success_score = round(successes / proc.usage_count, 2)


class ProcedureLibrary:
    """Thread-safe catalog repository storing generalized ProcedureObject templates."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.validator = ProcedureValidator()
        self.generalizer = ProcedureGeneralizer()
        self.analyzer = SuccessAnalyzer()
        self.procedures: dict[str, ProcedureObject] = {}
        self.lock = threading.Lock()

    def publish_procedure(self, proc: ProcedureObject) -> None:
        """Validate proposed procedure template and add to catalog registers."""
        with self.lock:
            # 1. Validate
            self.validator.validate(proc)
            proc.state = ProcedureState.VALIDATED

            # 2. Publish/Store
            proc.state = ProcedureState.PUBLISHED
            self.procedures[proc.procedure_id] = proc

            self.event_bus.publish_sync(
                Event(
                    name="procedure.published",
                    category="Memory",
                    source="ProcedureLibrary",
                    payload={"procedure_id": proc.procedure_id, "version": proc.version},
                )
            )

    def deprecate_procedure(self, procedure_id: str) -> None:
        """Transition target procedure state to DEPRECATED."""
        with self.lock:
            proc = self.procedures.get(procedure_id)
            if not proc:
                raise ProceduralMemoryError(f"Procedure with ID '{procedure_id}' not found.")

            proc.state = ProcedureState.DEPRECATED
            self.event_bus.publish_sync(
                Event(
                    name="procedure.deprecated",
                    category="Memory",
                    source="ProcedureLibrary",
                    payload={"procedure_id": procedure_id},
                )
            )

    def get_procedure(self, procedure_id: str) -> ProcedureObject | None:
        """Fetch matching generalized template from catalog registers."""
        with self.lock:
            return self.procedures.get(procedure_id)

    def list_all(self) -> list[ProcedureObject]:
        """Return list representing all registered procedures."""
        with self.lock:
            return list(self.procedures.values())
