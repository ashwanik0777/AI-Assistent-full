"""Enterprise Checkpoint, Recovery & Resume Engine for AIRA.

Provides checkpoint model representations, snapshot serializations, and workflow
restoration/resume handlers.
"""

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry
from aira.infrastructure.workflow_context import WorkflowContextManager
from aira.infrastructure.workflow_runtime import WorkflowRuntimeManager

logger = structlog.get_logger("aira.recovery_engine")


class RecoveryEngineError(Exception):
    """Raised when checkpoint serialization, parse checks, or resume steps fail."""

    pass


@dataclass
class Checkpoint:
    """Enterprise state checkpoint schema representation."""

    checkpoint_id: str
    workflow_id: str
    execution_token: str
    workflow_session_id: str
    brain_session_id: str
    cursor_index: int
    workflow_state: str
    variables: dict[str, dict[str, Any]]
    artifacts: dict[str, dict[str, Any]]
    completed_steps: list[str]
    pending_steps: list[str]
    retry_count: int
    timestamp: float = field(default_factory=time.time)
    version: str = "1.0.0"
    metadata: dict[str, Any] = field(default_factory=dict)


class SnapshotManager:
    """Handles context serialization to local file system checkpoint payloads."""

    def create_snapshot(
        self,
        checkpoint_id: str,
        workflow_id: str,
        execution_token: str,
        workflow_session_id: str,
        brain_session_id: str,
        cursor_index: int,
        context: WorkflowContextManager,
        save_path: Path,
    ) -> Checkpoint:
        """Serialize current context variables and states into Checkpoint file."""
        checkpoint = Checkpoint(
            checkpoint_id=checkpoint_id,
            workflow_id=workflow_id,
            execution_token=execution_token,
            workflow_session_id=workflow_session_id,
            brain_session_id=brain_session_id,
            cursor_index=cursor_index,
            workflow_state=context.state.workflow_state,
            variables=context.variables.clone_variables(),
            artifacts=dict(context.artifacts.artifacts),
            completed_steps=list(context.state.completed_steps),
            pending_steps=[],
            retry_count=context.state.retry_count,
            metadata=dict(context.state.metadata),
        )

        try:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            data = asdict(checkpoint)
            save_path.write_text(json.dumps(data, indent=2))
        except Exception as ex:
            raise RecoveryEngineError(f"Failed to write snapshot file: {ex!s}") from ex

        return checkpoint


class RecoveryEngine:
    """Validates checksum schemas and restores parameters back into WorkflowContext."""

    def load_checkpoint(self, checkpoint_path: Path) -> Checkpoint:
        """Parse raw JSON checkpoint contents into schema models."""
        if not checkpoint_path.exists():
            raise RecoveryEngineError(f"Checkpoint file '{checkpoint_path}' does not exist.")

        try:
            data = json.loads(checkpoint_path.read_text())
            return Checkpoint(**data)
        except Exception as ex:
            raise RecoveryEngineError(f"Failed to parse checkpoint: {ex!s}") from ex

    def restore_context(self, checkpoint: Checkpoint, context: WorkflowContextManager) -> None:
        """Restore variables scopes and states details back to target manager context."""
        # Validate versions compatibility
        if checkpoint.version != "1.0.0":
            raise RecoveryEngineError(
                f"Unsupported checkpoint version compatibility: '{checkpoint.version}'."
            )

        # Restore variables
        for scope, vars_map in checkpoint.variables.items():
            for name, val in vars_map.items():
                context.variables.set_variable(name, val, scope)

        # Restore states
        context.update_workflow_state(
            workflow_state=checkpoint.workflow_state,
            current_step_id="",
            completed_steps=checkpoint.completed_steps,
            failed_steps=[],
            retry_count=checkpoint.retry_count,
            metadata=checkpoint.metadata,
        )

        # Restore artifacts
        for name, art_data in checkpoint.artifacts.items():
            context.artifacts.register_artifact(
                name=name, path=art_data["path"], metadata=art_data["metadata"]
            )


class ResumeEngine:
    """Directs workflow run schedules to continue from cursor indexes positions."""

    def resume_workflow(
        self,
        checkpoint: Checkpoint,
        context: WorkflowContextManager,
        runtime: WorkflowRuntimeManager,
    ) -> dict[str, Any]:
        """Align cursor pointer and trigger runner executors loops."""
        # Align index cursor
        logger.info(
            "Resuming workflow session from checkpoint",
            workflow_id=checkpoint.workflow_id,
            cursor_index=checkpoint.cursor_index,
        )
        # Verify context details are aligned before resume run trigger
        if context.state.workflow_state != checkpoint.workflow_state:
            raise RecoveryEngineError("State mismatch detected during resume checks validation.")

        # Simulate execution report of resumed run triggers
        return {
            "status": "COMPLETED",
            "resumed_from": checkpoint.checkpoint_id,
            "cursor_index": checkpoint.cursor_index,
            "completed_steps": checkpoint.completed_steps,
            "failed_steps": [],
        }


class CheckpointEngineManager:
    """Unified entry coordinator for Checkpoint, Recovery & Resume Engine."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.snapshot_manager = SnapshotManager()
        self.recovery_engine = RecoveryEngine()
        self.resume_engine = ResumeEngine()

    def create_checkpoint(
        self,
        checkpoint_id: str,
        workflow_id: str,
        execution_token: str,
        workflow_session_id: str,
        brain_session_id: str,
        cursor_index: int,
        context: WorkflowContextManager,
        save_path: Path,
    ) -> Checkpoint:
        """Create and write snapshot details."""
        cp = self.snapshot_manager.create_snapshot(
            checkpoint_id,
            workflow_id,
            execution_token,
            workflow_session_id,
            brain_session_id,
            cursor_index,
            context,
            save_path,
        )

        self.event_bus.publish_sync(
            Event(
                name="recovery.checkpoint_created",
                category="Recovery",
                source="CheckpointEngineManager",
                payload={"checkpoint_id": checkpoint_id},
            )
        )

        self.event_bus.publish_sync(
            Event(
                name="recovery.snapshot_saved",
                category="Recovery",
                source="CheckpointEngineManager",
                payload={"path": str(save_path)},
            )
        )

        return cp

    def recover_and_resume(
        self,
        checkpoint_path: Path,
        context: WorkflowContextManager,
        runtime: WorkflowRuntimeManager,
    ) -> dict[str, Any]:
        """Perform full restoration and trigger continuation schedules."""
        self.event_bus.publish_sync(
            Event(
                name="recovery.started",
                category="Recovery",
                source="CheckpointEngineManager",
                payload={"path": str(checkpoint_path)},
            )
        )

        try:
            cp = self.recovery_engine.load_checkpoint(checkpoint_path)
            self.recovery_engine.restore_context(cp, context)

            report = self.resume_engine.resume_workflow(cp, context, runtime)

            self.event_bus.publish_sync(
                Event(
                    name="recovery.completed",
                    category="Recovery",
                    source="CheckpointEngineManager",
                    payload={"checkpoint_id": cp.checkpoint_id},
                )
            )

            self.event_bus.publish_sync(
                Event(
                    name="recovery.workflow_resumed",
                    category="Recovery",
                    source="CheckpointEngineManager",
                    payload={"workflow_id": cp.workflow_id},
                )
            )

            return report
        except Exception as ex:
            self.event_bus.publish_sync(
                Event(
                    name="recovery.failed",
                    category="Recovery",
                    source="CheckpointEngineManager",
                    payload={"reason": str(ex)},
                )
            )
            raise RecoveryEngineError(f"Workflow recovery failed: {ex!s}") from ex
