"""Enterprise Workspace & Multi-Project Orchestrator subsystem for AIRA.

Manages workspace project registry nodes, shared dependencies trees, and cross-project searches.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.workspace_intelligence")


class WorkspaceIntelligenceError(Exception):
    """Raised when workspace registrations, graph updates, or search indexes fail."""

    pass


@dataclass
class WorkspaceProject:
    """Represents an engineering project node inside a workspace ecosystem."""

    project_id: str
    name: str
    tech_stack: list[str] = field(default_factory=list)
    dependencies: dict[str, str] = field(default_factory=dict)  # package: version
    health_score: float = 100.0
    metadata: dict[str, Any] = field(default_factory=dict)


class WorkspaceGraph:
    """Workspace graph representing multi-project connection nodes and relations edges."""

    def __init__(self) -> None:
        self.projects: dict[str, WorkspaceProject] = {}
        self.relationships: dict[str, list[str]] = {}  # source_project -> target_projects

    def add_project(self, project: WorkspaceProject) -> None:
        """Register project node in graph state."""
        self.projects[project.project_id] = project
        if project.project_id not in self.relationships:
            self.relationships[project.project_id] = []

    def link_projects(self, source_id: str, target_id: str) -> None:
        """Link relationship edge between two projects nodes."""
        if (
            source_id in self.relationships
            and target_id in self.projects
            and target_id not in self.relationships[source_id]
        ):
            self.relationships[source_id].append(target_id)


class SharedDependencyAnalyzer:
    """Cross-references shared package versions to report version misalignment drift warnings."""

    def analyze_dependencies(self, projects: list[WorkspaceProject]) -> dict[str, Any]:
        """Aggregate shared dependencies across project nodes to verify alignment."""
        dependency_map: dict[str, dict[str, list[str]]] = {}  # package -> version -> projects
        for p in projects:
            for dep, ver in p.dependencies.items():
                if dep not in dependency_map:
                    dependency_map[dep] = {}
                if ver not in dependency_map[dep]:
                    dependency_map[dep][ver] = []
                dependency_map[dep][ver].append(p.name)

        # Detect mismatches (same package used with different versions)
        mismatches = {}
        for dep, versions in dependency_map.items():
            if len(versions) > 1:
                mismatches[dep] = versions

        consistency_score = 100.0
        if len(dependency_map) > 0:
            mismatch_ratio = len(mismatches) / len(dependency_map)
            consistency_score -= mismatch_ratio * 100.0

        return {
            "consistency_score": max(0.0, consistency_score),
            "mismatches": mismatches,
            "shared_packages_count": len(dependency_map),
        }


class WorkspaceHealthAnalyzer:
    """Evaluates multi-project portfolios averages, rankings, and dependency scores."""

    def evaluate_workspace(
        self, projects: list[WorkspaceProject], dep_report: dict[str, Any]
    ) -> dict[str, Any]:
        """Compile aggregates workspace metrics reports."""
        if not projects:
            return {"overall_health": 100.0, "project_rankings": [], "consistency_score": 100.0}

        avg_health = sum(p.health_score for p in projects) / len(projects)
        consistency = dep_report.get("consistency_score", 100.0)

        # Combine average project health and dependency consistency into one overall metric
        overall_health = (avg_health * 0.7) + (consistency * 0.3)

        # Rank projects by health descending
        rankings = sorted(projects, key=lambda p: p.health_score, reverse=True)
        rankings_report = [
            {"project_id": p.project_id, "name": p.name, "health": p.health_score} for p in rankings
        ]

        return {
            "overall_health": max(0.0, overall_health),
            "project_rankings": rankings_report,
            "consistency_score": consistency,
        }


class CrossProjectSearch:
    """Performs metadata lookups scanning technology keys and names across workspace registry."""

    def search(self, query: str, projects: list[WorkspaceProject]) -> list[dict[str, Any]]:
        """Filter projects list matching query tags."""
        matches = []
        q = query.lower()

        for p in projects:
            match_found = False
            # Match project name or ID
            if (
                q in p.name.lower()
                or q in p.project_id.lower()
                or any(q in tech.lower() for tech in p.tech_stack)
                or any(q in dep.lower() for dep in p.dependencies)
            ):
                match_found = True

            if match_found:
                matches.append(
                    {
                        "project_id": p.project_id,
                        "name": p.name,
                        "matched_dependencies": [dep for dep in p.dependencies if q in dep.lower()],
                    }
                )

        return matches


class WorkspaceIntelligenceManager:
    """Primary Workspace manager maintaining portfolio registries, search nodes, and audits."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.graph = WorkspaceGraph()
        self.dep_analyzer = SharedDependencyAnalyzer()
        self.health_analyzer = WorkspaceHealthAnalyzer()
        self.search_engine = CrossProjectSearch()

    def register_project(self, project: WorkspaceProject) -> None:
        """Register project node in graph database and dispatch update events."""
        if not project.project_id or not project.name:
            raise WorkspaceIntelligenceError("Project ID and Name are required.")

        self.graph.add_project(project)

        self.event_bus.publish_sync(
            Event(
                name="project.linked",
                category="Workspace",
                source="WorkspaceIntelligenceManager",
                payload={"project_id": project.project_id},
            )
        )

        self.event_bus.publish_sync(
            Event(
                name="workspace.updated",
                category="Workspace",
                source="WorkspaceIntelligenceManager",
                payload={"action": "add_project", "project_id": project.project_id},
            )
        )

    def run_workspace_health_audit(self) -> dict[str, Any]:
        """Inspect dependencies consistency and output overall Workspace Health details."""
        projects_list = list(self.graph.projects.values())
        dep_report = self.dep_analyzer.analyze_dependencies(projects_list)

        self.event_bus.publish_sync(
            Event(
                name="shared_dependency.updated",
                category="Workspace",
                source="WorkspaceIntelligenceManager",
                payload={"consistency_score": dep_report["consistency_score"]},
            )
        )

        health_report = self.health_analyzer.evaluate_workspace(projects_list, dep_report)

        self.event_bus.publish_sync(
            Event(
                name="workspace_health.updated",
                category="Workspace",
                source="WorkspaceIntelligenceManager",
                payload={"overall_health": health_report["overall_health"]},
            )
        )

        return health_report

    def search_workspace(self, query: str) -> list[dict[str, Any]]:
        """Filter portfolio projects registry matching target queries."""
        projects_list = list(self.graph.projects.values())
        matches = self.search_engine.search(query, projects_list)

        self.event_bus.publish_sync(
            Event(
                name="cross_project_search.completed",
                category="Workspace",
                source="WorkspaceIntelligenceManager",
                payload={"query": query, "matches_count": len(matches)},
            )
        )

        return matches
