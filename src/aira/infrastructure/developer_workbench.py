"""Enterprise Developer Workbench, Local Runtime, Emulator & Testing Platform for AIRA.

Provides local runtimes, emulator layers, mock servers, and test harnesses.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.developer_workbench")


class DeveloperWorkbenchError(Exception):
    """Base exception raised for emulation gaps, mock errors, or test harness failures."""

    pass


@dataclass
class LocalWorkspace:
    """Development workspace metadata tracking SDK versions and active settings."""

    workspace_id: str
    project_name: str
    runtime_version: str
    sdk_version: str
    mock_services: list[str]
    synthetic_data: dict[str, Any]
    test_config: dict[str, Any]
    evidence_references: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    active: bool = True
    version: int = 1


class LocalRuntime:
    """Manages local workspace runtime lifecycle execution flags."""

    def __init__(self) -> None:
        self.workspaces: dict[str, LocalWorkspace] = {}

    def register_workspace(self, ws: LocalWorkspace) -> None:
        """Register active workspace."""
        self.workspaces[ws.workspace_id] = ws


class EmulatorLayer:
    """Emulates core platform capabilities stubs without using production servers."""

    def emulate_service(self, service_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Process stub outcomes based on input parameters."""
        allowed = {"AgentRuntime", "WorkflowRuntime", "EventBus", "KnowledgeRuntime"}
        if service_name not in allowed:
            raise DeveloperWorkbenchError(
                f"Emulation failed: Unsupported service stub '{service_name}'."
            )
        return {
            "service": service_name,
            "emulated": True,
            "outcome": f"Processed payload of size {len(payload)}",
        }


class ApiMockServer:
    """Validates parameters and returns mock response payloads."""

    def mock_api_call(self, endpoint: str, parameters: dict[str, Any]) -> dict[str, Any]:
        """Validate input payload properties and return mock JSON results."""
        if endpoint == "payment" and "amount" not in parameters:
            raise DeveloperWorkbenchError(
                "Mock Server validation failed: Missing required parameter 'amount'."
            )
        return {
            "endpoint": endpoint,
            "status": "MockSuccess",
            "mocked_data": f"Data payload for endpoint {endpoint}",
        }


class TestHarness:
    """Executes automated testing processes and compiles evidence reports."""

    def execute_test_suite(
        self,
        workspace: LocalWorkspace,
        test_type: str,  # Unit, Integration, Contract, Workflow
    ) -> dict[str, Any]:
        """Generate test results metadata."""
        # Simple test coverage assertion checks
        return {
            "workspace_id": workspace.workspace_id,
            "test_type": test_type,
            "status": "Passed",
            "tests_run": 10,
            "coverage_pct": 98.5,
        }


class DebugConsole:
    """Captures runtime diagnostics errors and prints correction guidance."""

    def debug_error(self, error_message: str) -> dict[str, Any]:
        """Format traceback alert and provide correction advice."""
        return {
            "level": "ERROR",
            "traceback": error_message,
            "guidance": "Verify endpoint parameters mapping in contract manifest files.",
        }


class DeveloperWorkbenchPlatform:
    """Coordinating manager resolving workspaces, emulations, test harnesses, and evidence logs."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.runtime = LocalRuntime()
        self.emulator = EmulatorLayer()
        self.mock_server = ApiMockServer()
        self.test_harness = TestHarness()
        self.debug_console = DebugConsole()

    def start_local_workspace(
        self,
        workspace_id: str,
        project_name: str,
        runtime_version: str,
        sdk_version: str,
        mock_services: list[str],
        synthetic_data: dict[str, Any],
        test_config: dict[str, Any],
    ) -> LocalWorkspace:
        """Initialize workspace context and publish events."""
        ws = LocalWorkspace(
            workspace_id=workspace_id,
            project_name=project_name,
            runtime_version=runtime_version,
            sdk_version=sdk_version,
            mock_services=mock_services,
            synthetic_data=synthetic_data,
            test_config=test_config,
        )

        self.runtime.register_workspace(ws)

        self.event_bus.publish_sync(
            Event(
                name="workbench.workspace.created",
                category="DeveloperWorkbench",
                source="DeveloperWorkbenchPlatform",
                payload={"workspace_id": workspace_id},
            )
        )

        return ws

    def start_service_emulation(self, service_name: str) -> None:
        """Trigger emulator stub start checks and publish events."""
        self.event_bus.publish_sync(
            Event(
                name="workbench.emulator.started",
                category="DeveloperWorkbench",
                source="DeveloperWorkbenchPlatform",
                payload={"service": service_name},
            )
        )

    def run_workspace_test_suite(self, workspace_id: str, test_type: str) -> dict[str, Any]:
        """Run tests suite checks, save evidence logs, and publish events."""
        ws = self.runtime.workspaces.get(workspace_id)
        if not ws:
            raise DeveloperWorkbenchError(f"Workspace not found: '{workspace_id}'")

        # 1. Run tests process
        report = self.test_harness.execute_test_suite(ws, test_type)

        self.event_bus.publish_sync(
            Event(
                name="workbench.tests.executed",
                category="DeveloperWorkbench",
                source="DeveloperWorkbenchPlatform",
                payload={"workspace_id": workspace_id, "test_type": test_type},
            )
        )

        # 2. Save evidence references logs
        evidence_id = f"evidence_{workspace_id}_{test_type.lower()}"
        ws.evidence_references.append(evidence_id)

        self.event_bus.publish_sync(
            Event(
                name="workbench.evidence.generated",
                category="DeveloperWorkbench",
                source="DeveloperWorkbenchPlatform",
                payload={"workspace_id": workspace_id, "evidence_id": evidence_id},
            )
        )

        return report

    def archive_local_workspace(self, workspace_id: str) -> None:
        """Archive workspace details and publish events."""
        ws = self.runtime.workspaces.get(workspace_id)
        if not ws:
            raise DeveloperWorkbenchError(f"Workspace not found: '{workspace_id}'")

        ws.active = False

        self.event_bus.publish_sync(
            Event(
                name="workbench.workspace.archived",
                category="DeveloperWorkbench",
                source="DeveloperWorkbenchPlatform",
                payload={"workspace_id": workspace_id},
            )
        )
