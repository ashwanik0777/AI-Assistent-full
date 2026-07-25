"""Enterprise Workflow Definition Language (WDL) Parser & Serializer for AIRA.

Provides schema validation, parsing, serialization, and deserialization for workflows
represented in YAML or JSON declarations.
"""

import json
from dataclasses import dataclass, field
from typing import Any

import structlog
import yaml

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.wdl_parser")


@dataclass
class StepDefinition:
    """Represents a single step declaration inside a workflow definition schema."""

    step_id: str
    title: str
    description: str
    skill: str
    input_mappings: dict[str, str] = field(default_factory=dict)
    output_mappings: dict[str, str] = field(default_factory=dict)
    retry_policy: dict[str, Any] = field(default_factory=dict)
    timeout: float = 30.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowDefinition:
    """Represents a validated, portable workflow definition blueprint."""

    workflow_id: str
    name: str
    version: str
    description: str
    author: str
    created_date: str
    updated_date: str
    tags: list[str]
    execution_plan_id: str
    goal_id: str
    brain_session_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    steps: list[StepDefinition] = field(default_factory=list)


class WdlValidationError(Exception):
    """Raised when workflow schema constraints or field requirements are violated."""

    pass


class WdlValidator:
    """Validates structural constraints, duplicate identifiers, and formatting bounds."""

    @staticmethod
    def validate(data: dict[str, Any]) -> None:
        """Assert schema correctness, throwing WdlValidationError on failure."""
        required_wf_fields = [
            "workflow_id",
            "name",
            "version",
            "description",
            "author",
            "created_date",
            "updated_date",
            "steps",
        ]
        for field_name in required_wf_fields:
            if field_name not in data or data[field_name] is None:
                raise WdlValidationError(f"Missing required workflow field: '{field_name}'")

        steps = data["steps"]
        if not isinstance(steps, list):
            raise WdlValidationError("Workflow 'steps' field must be a list configuration.")

        if len(steps) == 0:
            raise WdlValidationError("Workflow must contain at least one step definition.")

        # Ensure step ID uniqueness
        seen_step_ids = set()
        required_step_fields = ["step_id", "title", "description", "skill"]

        for step in steps:
            if not isinstance(step, dict):
                raise WdlValidationError("Workflow step configuration must be a map structure.")

            for sf in required_step_fields:
                if sf not in step or step[sf] is None:
                    raise WdlValidationError(f"Missing required step field: '{sf}'")

            sid = step["step_id"]
            if sid in seen_step_ids:
                raise WdlValidationError(f"Duplicate step identifier: '{sid}'")
            seen_step_ids.add(sid)


class WdlParser:
    """Parses WDL representations from JSON or YAML files/strings into structural models."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.validator = WdlValidator()

    def parse_yaml(self, yaml_content: str) -> WorkflowDefinition:
        """Parse YAML content, execute validations, and build WorkflowDefinition."""
        try:
            data = yaml.safe_load(yaml_content)
        except Exception as ex:
            raise WdlValidationError(
                f"Failed to parse malformed YAML configuration: {ex!s}"
            ) from ex

        if not isinstance(data, dict):
            raise WdlValidationError("Workflow definition root must be a map structure.")

        self.event_bus.publish_sync(
            Event(name="wdl.import_ready", category="WDL", source="WdlParser", payload={})
        )

        self.validator.validate(data)

        self.event_bus.publish_sync(
            Event(
                name="wdl.validated",
                category="WDL",
                source="WdlParser",
                payload={"workflow_id": data["workflow_id"]},
            )
        )

        # Build steps
        steps = []
        for s in data["steps"]:
            steps.append(
                StepDefinition(
                    step_id=s["step_id"],
                    title=s["title"],
                    description=s["description"],
                    skill=s["skill"],
                    input_mappings=s.get("input_mappings", {}),
                    output_mappings=s.get("output_mappings", {}),
                    retry_policy=s.get("retry_policy", {}),
                    timeout=float(s.get("timeout", 30.0)),
                    metadata=s.get("metadata", {}),
                )
            )

        wf_def = WorkflowDefinition(
            workflow_id=data["workflow_id"],
            name=data["name"],
            version=data["version"],
            description=data["description"],
            author=data["author"],
            created_date=data["created_date"],
            updated_date=data["updated_date"],
            tags=data.get("tags", []),
            execution_plan_id=data.get("execution_plan_id", ""),
            goal_id=data.get("goal_id", ""),
            brain_session_id=data.get("brain_session_id", ""),
            metadata=data.get("metadata", {}),
            steps=steps,
        )

        self.event_bus.publish_sync(
            Event(
                name="wdl.parsed",
                category="WDL",
                source="WdlParser",
                payload={"workflow_id": wf_def.workflow_id},
            )
        )

        self.event_bus.publish_sync(
            Event(
                name="wdl.loaded",
                category="WDL",
                source="WdlParser",
                payload={"workflow_id": wf_def.workflow_id},
            )
        )

        return wf_def

    def parse_json(self, json_content: str) -> WorkflowDefinition:
        """Parse JSON content, execute validations, and build WorkflowDefinition."""
        try:
            data = json.loads(json_content)
        except Exception as ex:
            raise WdlValidationError(
                f"Failed to parse malformed JSON configuration: {ex!s}"
            ) from ex

        if not isinstance(data, dict):
            raise WdlValidationError("Workflow definition root must be a map structure.")

        self.validator.validate(data)

        steps = []
        for s in data["steps"]:
            steps.append(
                StepDefinition(
                    step_id=s["step_id"],
                    title=s["title"],
                    description=s["description"],
                    skill=s["skill"],
                    input_mappings=s.get("input_mappings", {}),
                    output_mappings=s.get("output_mappings", {}),
                    retry_policy=s.get("retry_policy", {}),
                    timeout=float(s.get("timeout", 30.0)),
                    metadata=s.get("metadata", {}),
                )
            )

        return WorkflowDefinition(
            workflow_id=data["workflow_id"],
            name=data["name"],
            version=data["version"],
            description=data["description"],
            author=data["author"],
            created_date=data["created_date"],
            updated_date=data["updated_date"],
            tags=data.get("tags", []),
            execution_plan_id=data.get("execution_plan_id", ""),
            goal_id=data.get("goal_id", ""),
            brain_session_id=data.get("brain_session_id", ""),
            metadata=data.get("metadata", {}),
            steps=steps,
        )


class WdlSerializer:
    """Serializes WorkflowDefinition model structures back to JSON or YAML representations."""

    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus

    def serialize_yaml(self, definition: WorkflowDefinition) -> str:
        """Convert WorkflowDefinition back to raw YAML string data representation."""
        data = self._to_dict(definition)
        res = yaml.safe_dump(data, sort_keys=False)
        serialized = str(res) if res is not None else ""

        self.event_bus.publish_sync(
            Event(
                name="wdl.serialized",
                category="WDL",
                source="WdlSerializer",
                payload={"workflow_id": definition.workflow_id},
            )
        )

        self.event_bus.publish_sync(
            Event(name="wdl.export_ready", category="WDL", source="WdlSerializer", payload={})
        )

        return serialized

    def serialize_json(self, definition: WorkflowDefinition) -> str:
        """Convert WorkflowDefinition back to raw JSON string data representation."""
        data = self._to_dict(definition)
        return json.dumps(data, indent=2)

    def _to_dict(self, definition: WorkflowDefinition) -> dict[str, Any]:
        steps = []
        for s in definition.steps:
            steps.append(
                {
                    "step_id": s.step_id,
                    "title": s.title,
                    "description": s.description,
                    "skill": s.skill,
                    "input_mappings": s.input_mappings,
                    "output_mappings": s.output_mappings,
                    "retry_policy": s.retry_policy,
                    "timeout": s.timeout,
                    "metadata": s.metadata,
                }
            )

        return {
            "workflow_id": definition.workflow_id,
            "name": definition.name,
            "version": definition.version,
            "description": definition.description,
            "author": definition.author,
            "created_date": definition.created_date,
            "updated_date": definition.updated_date,
            "tags": definition.tags,
            "execution_plan_id": definition.execution_plan_id,
            "goal_id": definition.goal_id,
            "brain_session_id": definition.brain_session_id,
            "metadata": definition.metadata,
            "steps": steps,
        }
