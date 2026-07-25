"""Enterprise Low-Code, No-Code & AI Solution Builder Platform for AIRA.

Provides visual builders, business rule engines, and publisher lifecycles.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.solution_builder")


class SolutionBuilderError(Exception):
    """Base exception raised for schema drifts, publishing violations, or guardrail blocks."""

    pass


@dataclass
class SolutionBlueprint:
    """Blueprint layout representing composed forms, data fields, and rules."""

    solution_id: str
    domain: str
    components: list[str]
    data_model: dict[str, Any]
    business_rules: list[dict[str, Any]]
    workflows: list[str]
    permissions: list[str]
    lifecycle_state: str = "Draft"  # Draft, Validation, Review, Approval, Publication, Archive
    version: str = "1.0.0"
    metadata: dict[str, Any] = field(default_factory=dict)


class VisualSolutionBuilder:
    """Stores visual solution blueprint configurations."""

    def __init__(self) -> None:
        self.blueprints: dict[str, SolutionBlueprint] = {}

    def register_solution(self, bp: SolutionBlueprint) -> None:
        """Register composed design parameters."""
        self.blueprints[bp.solution_id] = bp


class BusinessRuleBuilder:
    """Defines and checks reusable business rules keys."""

    def validate_rules(self, rules: list[dict[str, Any]]) -> bool:
        """Validate format schemas of conditional constraints."""
        return all("name" in r and "condition" in r for r in rules)


class DataModelDesigner:
    """Validates datatype schema maps keys."""

    def validate_schema(self, data_model: dict[str, Any]) -> bool:
        """Check field constraints properties types."""
        for _, properties in data_model.items():
            if not isinstance(properties, dict) or "type" not in properties:
                return False
        return True


class CitizenDeveloperGuardrails:
    """Enforces role permissions boundaries and intercepts restricted operations."""

    def audit_solution(self, bp: SolutionBlueprint) -> None:
        """Raise error if restricted permission tags are found."""
        restricted = {"PlatformAdmin", "RootAccess", "UnrestrictedNetwork"}
        for scope in bp.permissions:
            if scope in restricted:
                raise SolutionBuilderError(
                    f"Guardrail violation: Citizen developer cannot request "
                    f"restricted permission '{scope}'."
                )


class SolutionPublisher:
    """Governs solution publishing state transitions."""

    def transition_state(self, bp: SolutionBlueprint, next_state: str) -> None:
        """Evaluate state sequence rules."""
        current = bp.lifecycle_state

        allowed = {
            "Draft": {"Validation"},
            "Validation": {"Review"},
            "Review": {"Approval"},
            "Approval": {"Publication"},
            "Publication": {"Archive"},
            "Archive": set(),
        }

        if next_state not in allowed.get(current, set()):
            raise SolutionBuilderError(
                f"Publishing transition failed: Cannot transition solution '{bp.solution_id}' "
                f"from state '{current}' to '{next_state}'."
            )

        bp.lifecycle_state = next_state


class SolutionBuilderPlatform:
    """Coordinating manager resolving solution rules checks and publishing."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.builder = VisualSolutionBuilder()
        self.rule_builder = BusinessRuleBuilder()
        self.designer = DataModelDesigner()
        self.guardrails = CitizenDeveloperGuardrails()
        self.publisher = SolutionPublisher()

    def create_solution_blueprint(
        self,
        solution_id: str,
        domain: str,
        components: list[str],
        data_model: dict[str, Any],
        business_rules: list[dict[str, Any]],
        workflows: list[str],
        permissions: list[str],
    ) -> SolutionBlueprint:
        """Initialize blueprint configuration metadata and publish events."""
        bp = SolutionBlueprint(
            solution_id=solution_id,
            domain=domain,
            components=components,
            data_model=data_model,
            business_rules=business_rules,
            workflows=workflows,
            permissions=permissions,
        )

        self.builder.register_solution(bp)

        self.event_bus.publish_sync(
            Event(
                name="solution.created",
                category="SolutionBuilder",
                source="SolutionBuilderPlatform",
                payload={"solution_id": solution_id},
            )
        )

        return bp

    def run_guardrail_audits(self, solution_id: str) -> None:
        """Enforce guardrails checks and publish warnings if triggered."""
        bp = self.builder.blueprints.get(solution_id)
        if not bp:
            raise SolutionBuilderError(f"Solution blueprint not found: '{solution_id}'")

        try:
            self.guardrails.audit_solution(bp)
        except SolutionBuilderError as e:
            self.event_bus.publish_sync(
                Event(
                    name="solution.guardrail.triggered",
                    category="SolutionBuilder",
                    source="SolutionBuilderPlatform",
                    payload={"solution_id": solution_id, "violation": str(e)},
                )
            )
            raise

    def validate_solution_blueprint(self, solution_id: str) -> None:
        """Validate business rules and schemas, promote state, and publish events."""
        bp = self.builder.blueprints.get(solution_id)
        if not bp:
            raise SolutionBuilderError(f"Solution blueprint not found: '{solution_id}'")

        # 1. Rules Check
        if not self.rule_builder.validate_rules(bp.business_rules):
            raise SolutionBuilderError(
                f"Validation failed: Business rules formats for '{solution_id}' are invalid."
            )

        # 2. Data model Check
        if not self.designer.validate_schema(bp.data_model):
            raise SolutionBuilderError(
                f"Validation failed: Data model properties schema for '{solution_id}' is invalid."
            )

        # 3. Transition to Validation
        self.publisher.transition_state(bp, "Validation")

        self.event_bus.publish_sync(
            Event(
                name="solution.validation.completed",
                category="SolutionBuilder",
                source="SolutionBuilderPlatform",
                payload={"solution_id": solution_id},
            )
        )

    def publish_solution(self, solution_id: str) -> None:
        """Run validation promotions sequences and publish events."""
        bp = self.builder.blueprints.get(solution_id)
        if not bp:
            raise SolutionBuilderError(f"Solution blueprint not found: '{solution_id}'")

        # Sequentially advance staging validation states
        if bp.lifecycle_state == "Validation":
            self.publisher.transition_state(bp, "Review")
        if bp.lifecycle_state == "Review":
            self.publisher.transition_state(bp, "Approval")
        if bp.lifecycle_state == "Approval":
            self.publisher.transition_state(bp, "Publication")

            self.event_bus.publish_sync(
                Event(
                    name="solution.blueprint.generated",
                    category="SolutionBuilder",
                    source="SolutionBuilderPlatform",
                    payload={"solution_id": solution_id},
                )
            )

            self.event_bus.publish_sync(
                Event(
                    name="solution.published",
                    category="SolutionBuilder",
                    source="SolutionBuilderPlatform",
                    payload={"solution_id": solution_id},
                )
            )
