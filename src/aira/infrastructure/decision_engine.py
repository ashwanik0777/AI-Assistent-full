"""Enterprise Conditional Execution & Decision Engine for AIRA.

Provides condition operators evaluations, expression resolution mapping,
loop retry managers, and branching resolves.
"""

from enum import Enum
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry
from aira.infrastructure.workflow_context import WorkflowContextManager

logger = structlog.get_logger("aira.decision_engine")


class DecisionEngineError(Exception):
    """Raised when expression syntaxes, loops boundaries, or branch mappings fail."""

    pass


class ConditionOperator(Enum):
    """Supported logical comparison operators in condition evaluation steps."""

    EQUALS = "EQUALS"
    NOT_EQUALS = "NOT_EQUALS"
    GREATER_THAN = "GREATER_THAN"
    LESS_THAN = "LESS_THAN"
    CONTAINS = "CONTAINS"
    STARTS_WITH = "STARTS_WITH"
    ENDS_WITH = "ENDS_WITH"
    EXISTS = "EXISTS"
    NOT_EXISTS = "NOT_EXISTS"
    BOOLEAN = "BOOLEAN"
    NULL = "NULL"


class ConditionEngine:
    """Evaluates values against condition operators constraints."""

    def evaluate(self, left: Any, operator: ConditionOperator, right: Any = None) -> bool:
        """Compare left and right parameters under operator rules."""
        if operator == ConditionOperator.EQUALS:
            return bool(left == right)
        elif operator == ConditionOperator.NOT_EQUALS:
            return bool(left != right)
        elif operator == ConditionOperator.GREATER_THAN:
            try:
                return float(left) > float(right)
            except (ValueError, TypeError):
                return str(left) > str(right)
        elif operator == ConditionOperator.LESS_THAN:
            try:
                return float(left) < float(right)
            except (ValueError, TypeError):
                return str(left) < str(right)
        elif operator == ConditionOperator.CONTAINS:
            if left is None:
                return False
            return str(right) in str(left)
        elif operator == ConditionOperator.STARTS_WITH:
            if left is None:
                return False
            return str(left).startswith(str(right))
        elif operator == ConditionOperator.ENDS_WITH:
            if left is None:
                return False
            return str(left).endswith(str(right))
        elif operator == ConditionOperator.EXISTS:
            return left is not None
        elif operator == ConditionOperator.NOT_EXISTS:
            return left is None
        elif operator == ConditionOperator.BOOLEAN:
            return bool(left)
        elif operator == ConditionOperator.NULL:
            return left is None

        raise DecisionEngineError(f"Unsupported comparison operator: '{operator.value}'")


class ExpressionEngine:
    """Resolves string templates and evaluates variables within Decision Context."""

    def evaluate_expression(self, expression: str, context: WorkflowContextManager) -> Any:
        """Resolve and evaluate variable templates inside text expression parameters."""
        try:
            resolved = context.resolve(expression)
            return resolved
        except Exception as ex:
            raise DecisionEngineError(
                f"Failed to resolve expression '{expression}': {ex!s}"
            ) from ex


class BranchResolver:
    """Selects execution paths based on conditional criteria evaluation."""

    def select_branch(
        self, condition_result: bool, then_branch: str, else_branch: str | None = None
    ) -> str | None:
        """Determine target branch ID depending on branch conditions checks."""
        if condition_result:
            return then_branch
        return else_branch


class LoopEngine:
    """Manages loops iteration boundaries and coordinates retry count parameters."""

    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus

    def run_retry_check(self, attempt: int, max_retries: int) -> bool:
        """Verify if retry loop parameters satisfy maximum attempts boundaries."""
        if attempt < max_retries:
            self.event_bus.publish_sync(
                Event(
                    name="decision.workflow_continued",
                    category="Decision",
                    source="LoopEngine",
                    payload={"attempt": attempt + 1},
                )
            )
            return True
        return False


class DecisionEngineManager:
    """Unified entry coordinator for Conditional Execution & Decision Engine."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.condition_engine = ConditionEngine()
        self.expression_engine = ExpressionEngine()
        self.branch_resolver = BranchResolver()
        self.loop_engine = LoopEngine(event_bus)

    def evaluate_condition_step(
        self, left: Any, operator: ConditionOperator, right: Any = None
    ) -> bool:
        """Run verification through condition engine and notify event bus."""
        result = self.condition_engine.evaluate(left, operator, right)

        self.event_bus.publish_sync(
            Event(
                name="decision.condition_evaluated",
                category="Decision",
                source="DecisionEngineManager",
                payload={"operator": operator.value, "result": result},
            )
        )

        return result

    def resolve_branch(
        self, condition_result: bool, then_branch: str, else_branch: str | None = None
    ) -> str | None:
        """Evaluate targets branches mappings and notify selection event logs."""
        target = self.branch_resolver.select_branch(condition_result, then_branch, else_branch)

        self.event_bus.publish_sync(
            Event(
                name="decision.branch_selected",
                category="Decision",
                source="DecisionEngineManager",
                payload={"condition_result": condition_result, "selected_branch": target},
            )
        )

        return target

    def evaluate_expression_template(self, expression: str, context: WorkflowContextManager) -> Any:
        """Evaluate variables template checks and notify event bus."""
        res = self.expression_engine.evaluate_expression(expression, context)

        self.event_bus.publish_sync(
            Event(
                name="decision.expression_evaluated",
                category="Decision",
                source="DecisionEngineManager",
                payload={"expression": expression},
            )
        )

        return res
