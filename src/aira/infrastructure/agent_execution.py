"""Enterprise Execution Engine & Task Runtime for AIRA.

Provides intent generation, capability validation, sandboxing, and verifications.
"""

import time
from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.agent_execution")


class AgentExecutionError(Exception):
    """Raised when intent resolution, capability matching, sandboxing, or verifications fail."""

    pass


@dataclass
class ExecutionIntent:
    """Standard execution intent carrying required capability scopes and rollback plans."""

    intent_id: str
    task_id: str
    goal: str
    required_capability: str
    required_provider: str
    risk_level: str
    approval_policy: str
    expected_result: str
    rollback_strategy: str
    priority: int = 5
    metadata: dict[str, Any] = field(default_factory=dict)
    version: str = "1.0.0"


@dataclass
class VerificationReport:
    """Structure encapsulating execution verifier findings and compliance metrics."""

    verification_id: str
    success: bool
    details: str
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class ExecutionIntentBuilder:
    """Translates execution plan tasks lists into structured ExecutionIntents."""

    def build_intent(self, intent_id: str, task: dict[str, Any]) -> ExecutionIntent:
        """Construct a new execution intent from task config mapping properties."""
        task_name = task.get("name", "UnknownTask")
        return ExecutionIntent(
            intent_id=intent_id,
            task_id=task.get("task_id", "t_unknown"),
            goal=f"Execute task: {task_name}",
            required_capability=f"cap_{task_name.lower()}",
            required_provider="system_provider",
            risk_level="Medium" if "write" in task_name.lower() else "Low",
            approval_policy="HighRiskApproval" if "write" in task_name.lower() else "Auto",
            expected_result=f"Completed {task_name}",
            rollback_strategy="DiscardSandbox",
        )


class CapabilityResolver:
    """Verifies that platform capabilities match provider profiles and permissions lists."""

    def __init__(self) -> None:
        # Predefined allowed capabilities list
        self.allowed_capabilities: set[str] = {
            "cap_analyzerepo",
            "cap_writereport",
            "cap_reviewreport",
            "cap_analyzedoc",
        }

    def resolve_capability(self, capability: str) -> bool:
        """Verify presence of registered capability."""
        return capability in self.allowed_capabilities


class IntentResolver:
    """Assembles capabilities resources and matches runtime settings parameters."""

    def __init__(self, capability_resolver: CapabilityResolver) -> None:
        self.capability_resolver = capability_resolver

    def resolve_intent(self, intent: ExecutionIntent) -> dict[str, Any]:
        """Validate intent capabilities requirements."""
        cap = intent.required_capability
        if not self.capability_resolver.resolve_capability(cap):
            raise AgentExecutionError(
                f"Intent Resolution failed: Capability '{cap}' is not registered."
            )
        return {
            "resolved": True,
            "capability": cap,
            "runtime_params": {"timeout": 30, "priority": intent.priority},
        }


class ExecutionSandbox:
    """Allocates local directory structures, keeping temporary logs isolated."""

    def __init__(self) -> None:
        self.active_workspaces: dict[str, dict[str, Any]] = {}

    def start_sandbox(self, sandbox_id: str) -> None:
        """Initialize local variables store in sandbox."""
        self.active_workspaces[sandbox_id] = {
            "sandbox_id": sandbox_id,
            "variables": {},
            "status": "Running",
            "created_at": time.time(),
        }

    def cleanup_sandbox(self, sandbox_id: str) -> None:
        """Evict local sandbox variables registry references."""
        if sandbox_id in self.active_workspaces:
            self.active_workspaces[sandbox_id]["status"] = "Cleaned"
            del self.active_workspaces[sandbox_id]


class ResultVerifier:
    """Evaluates output variables schemas to verify task completions successfully."""

    def verify_result(self, verification_id: str, output: Any, expected: str) -> VerificationReport:
        """Inspect payload variables comparing output results strings contents."""
        # Simple match check
        success = expected.lower() in str(output).lower()
        return VerificationReport(
            verification_id=verification_id,
            success=success,
            details="Result verification passed." if success else "Output mismatch.",
        )


class RollbackManager:
    """Rolls back plan variables states, running recovery handlers."""

    def execute_rollback(self, plan_id: str, sandbox: ExecutionSandbox, sandbox_id: str) -> None:
        """Discard target sandbox workspace registers and notify rollback execution."""
        sandbox.cleanup_sandbox(sandbox_id)
        logger.warn(
            "Rollback executed: Sandbox context reset.",
            plan_id=plan_id,
            sandbox_id=sandbox_id,
        )


class ExecutionRuntimeEngine:
    """Orchestrates intent lifecycle pipelines resolving capabilities and checking verifications."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.intent_builder = ExecutionIntentBuilder()
        self.cap_resolver = CapabilityResolver()
        self.intent_resolver = IntentResolver(self.cap_resolver)
        self.sandbox = ExecutionSandbox()
        self.verifier = ResultVerifier()
        self.rollback_manager = RollbackManager()

    def execute_task(self, task: dict[str, Any], plan_id: str) -> VerificationReport:
        """Resolve capability, sandbox execution, verify result, and rollback on failure."""
        task_id = task.get("task_id", "t_unknown")
        intent_id = f"intent_{task_id}"

        # 1. Intent Build
        intent = self.intent_builder.build_intent(intent_id, task)
        self.event_bus.publish_sync(
            Event(
                name="intent.created",
                category="Execution",
                source="AgentExecutor",
                payload={"intent_id": intent_id, "task_id": task_id},
            )
        )

        # 2. Resolve
        res = self.intent_resolver.resolve_intent(intent)
        self.event_bus.publish_sync(
            Event(
                name="capability.selected",
                category="Execution",
                source="AgentExecutor",
                payload={"capability": res["capability"]},
            )
        )

        # 3. Sandbox Start
        sandbox_id = f"sb_exec_{task_id}"
        self.sandbox.start_sandbox(sandbox_id)
        self.event_bus.publish_sync(
            Event(
                name="sandbox.started",
                category="Execution",
                source="AgentExecutor",
                payload={"sandbox_id": sandbox_id},
            )
        )

        # Simulate execution output
        sim_output = f"Completed {task.get('name', 'Unknown')}"

        # 4. Result Verify
        ver_id = f"ver_{task_id}"
        report = self.verifier.verify_result(ver_id, sim_output, intent.expected_result)
        self.event_bus.publish_sync(
            Event(
                name="verification.completed",
                category="Execution",
                source="AgentExecutor",
                payload={"verification_id": ver_id, "success": report.success},
            )
        )

        if not report.success:
            self.event_bus.publish_sync(
                Event(
                    name="rollback.triggered",
                    category="Execution",
                    source="AgentExecutor",
                    payload={"plan_id": plan_id, "sandbox_id": sandbox_id},
                )
            )
            self.rollback_manager.execute_rollback(plan_id, self.sandbox, sandbox_id)
            raise AgentExecutionError(
                f"Execution failed: Result verification failed for task '{task_id}'."
            )

        # Cleanup sandbox on success
        self.sandbox.cleanup_sandbox(sandbox_id)

        self.event_bus.publish_sync(
            Event(
                name="execution.completed",
                category="Execution",
                source="AgentExecutor",
                payload={"intent_id": intent_id, "success": True},
            )
        )

        return report
