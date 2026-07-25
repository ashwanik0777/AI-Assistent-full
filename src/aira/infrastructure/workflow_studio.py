"""Enterprise Visual Workflow Studio, Flow Composer & Process Modeling Platform for AIRA.

Provides visual canvases, compilers, validation engines, and simulation previews.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.workflow_studio")


class WorkflowStudioError(Exception):
    """Base exception raised for compiler failures, validation loops, or simulation errors."""

    pass


@dataclass
class WorkflowNode:
    """Node block details specifying operational types and parameters properties."""

    node_id: str
    node_type: str  # Agent, Workflow, Decision, Parallel, Event, Approval, Timer, Integration
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowEdge:
    """Transitions link connecting source to target nodes."""

    source: str
    target: str
    condition: str | None = None


@dataclass
class WorkflowModel:
    """Design container representing visual modeling structures."""

    workflow_id: str
    nodes: list[WorkflowNode]
    edges: list[WorkflowEdge]
    version: str = "1.0.0"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowDefinition:
    """Compiled schema configuration representing output templates ready for runtime execution."""

    workflow_id: str
    compiled_nodes: dict[str, Any]
    compiled_edges: list[dict[str, Any]]
    version: str


class VisualCanvas:
    """Manages visual model canvas representations state maps."""

    def __init__(self) -> None:
        self.models: dict[str, WorkflowModel] = {}

    def save_model(self, model: WorkflowModel) -> None:
        """Register canvas structure."""
        self.models[model.workflow_id] = model


class ValidationEngine:
    """Checks visual layouts for structural errors and circular loops."""

    def validate_model(self, model: WorkflowModel) -> None:
        """Validate edge linkages and run cyclic dependency audits."""
        # 1. Check for dangling nodes
        node_ids = {n.node_id for n in model.nodes}
        for edge in model.edges:
            if edge.source not in node_ids or edge.target not in node_ids:
                raise WorkflowStudioError(
                    f"Validation failed: Edge maps to missing node ID reference "
                    f"('{edge.source}' -> '{edge.target}')."
                )

        # 2. Check for circular loops using standard DFS
        adj: dict[str, list[str]] = {nid: [] for nid in node_ids}
        for edge in model.edges:
            adj[edge.source].append(edge.target)

        # States: 0 = Unvisited, 1 = Visiting, 2 = Visited
        visited: dict[str, int] = {nid: 0 for nid in node_ids}

        def dfs(u: str) -> bool:
            visited[u] = 1
            for v in adj[u]:
                if visited[v] == 1:
                    return True
                if visited[v] == 0 and dfs(v):
                    return True
            visited[u] = 2
            return False

        for nid in node_ids:
            if visited[nid] == 0 and dfs(nid):
                raise WorkflowStudioError(
                    f"Validation failed: Circular dependency loop detected "
                    f"in workflow model '{model.workflow_id}'."
                )


class WorkflowCompiler:
    """Compiles visual models into deterministic definitions ready for runtime."""

    def compile_model(self, model: WorkflowModel) -> WorkflowDefinition:
        """Process nodes dictionary and edges mapping configurations."""
        compiled_nodes = {
            n.node_id: {"type": n.node_type, "properties": n.properties} for n in model.nodes
        }

        compiled_edges = [
            {"from": e.source, "to": e.target, "condition": e.condition} for e in model.edges
        ]

        return WorkflowDefinition(
            workflow_id=model.workflow_id,
            compiled_nodes=compiled_nodes,
            compiled_edges=compiled_edges,
            version=model.version,
        )


class SimulationPreview:
    """Simulates flow traversal paths and latency estimates."""

    def generate_preview(self, model: WorkflowModel) -> dict[str, Any]:
        """Verify mock latencies timing averages across compiled nodes."""
        latency = len(model.nodes) * 1.5  # mock timing latency scaling factor
        return {
            "workflow_id": model.workflow_id,
            "simulated_latency_sec": latency,
            "nodes_count": len(model.nodes),
            "edges_count": len(model.edges),
        }


class WorkflowVersionManager:
    """Manages revisions history metadata maps."""

    def __init__(self) -> None:
        self.versions: dict[str, list[str]] = {}

    def register_version(self, workflow_id: str, ver: str) -> None:
        """Register active release version mapping."""
        self.versions.setdefault(workflow_id, []).append(ver)


class WorkflowStudioPlatform:
    """Coordinating manager resolving visual models validation, compilation, and previews."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.canvas = VisualCanvas()
        self.validation_engine = ValidationEngine()
        self.compiler = WorkflowCompiler()
        self.simulator = SimulationPreview()
        self.version_manager = WorkflowVersionManager()

    def create_workflow_model(
        self, workflow_id: str, nodes: list[WorkflowNode], edges: list[WorkflowEdge]
    ) -> WorkflowModel:
        """Initialize canvas representation and publish events."""
        model = WorkflowModel(workflow_id=workflow_id, nodes=nodes, edges=edges)
        self.canvas.save_model(model)

        self.event_bus.publish_sync(
            Event(
                name="studio.workflow.created",
                category="WorkflowStudio",
                source="WorkflowStudioPlatform",
                payload={"workflow_id": workflow_id},
            )
        )

        return model

    def validate_workflow_model(self, workflow_id: str) -> None:
        """Trigger structural connectivity checking validations and publish events."""
        model = self.canvas.models.get(workflow_id)
        if not model:
            raise WorkflowStudioError(f"Workflow model not found on canvas: '{workflow_id}'")

        self.validation_engine.validate_model(model)

        self.event_bus.publish_sync(
            Event(
                name="studio.workflow.validated",
                category="WorkflowStudio",
                source="WorkflowStudioPlatform",
                payload={"workflow_id": workflow_id},
            )
        )

    def compile_workflow_model(self, workflow_id: str) -> WorkflowDefinition:
        """Invoke compiler parser transformations and publish events."""
        model = self.canvas.models.get(workflow_id)
        if not model:
            raise WorkflowStudioError(f"Workflow model not found on canvas: '{workflow_id}'")

        definition = self.compiler.compile_model(model)

        self.event_bus.publish_sync(
            Event(
                name="studio.workflow.compiled",
                category="WorkflowStudio",
                source="WorkflowStudioPlatform",
                payload={"workflow_id": workflow_id},
            )
        )

        return definition

    def generate_simulation_preview(self, workflow_id: str) -> dict[str, Any]:
        """Mock travel timing configurations and publish events."""
        model = self.canvas.models.get(workflow_id)
        if not model:
            raise WorkflowStudioError(f"Workflow model not found on canvas: '{workflow_id}'")

        preview = self.simulator.generate_preview(model)

        self.event_bus.publish_sync(
            Event(
                name="studio.simulation.generated",
                category="WorkflowStudio",
                source="WorkflowStudioPlatform",
                payload={"workflow_id": workflow_id},
            )
        )

        return preview

    def publish_workflow(self, workflow_id: str, version: str) -> None:
        """Commit version tags and publish events."""
        model = self.canvas.models.get(workflow_id)
        if not model:
            raise WorkflowStudioError(f"Workflow model not found on canvas: '{workflow_id}'")

        self.version_manager.register_version(workflow_id, version)

        self.event_bus.publish_sync(
            Event(
                name="studio.workflow.published",
                category="WorkflowStudio",
                source="WorkflowStudioPlatform",
                payload={"workflow_id": workflow_id, "version": version},
            )
        )
