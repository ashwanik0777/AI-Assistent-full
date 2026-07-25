"""Enterprise Project Intelligence & Digital Twin Engine subsystem for AIRA.

Analyzes workspace structures to generate architectural profiles, risks, and health scores.
"""

import os
import threading
from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry
from aira.infrastructure.workspace_engine import WorkspaceObject

logger = structlog.get_logger("aira.project_intelligence")


class ProjectIntelligenceError(Exception):
    """Raised when project analysis constraints are violated or project metadata is incomplete."""

    pass


@dataclass
class DigitalTwinObject:
    """Structured knowledge representation profile (Digital Twin) of a workspace project."""

    project_id: str
    project_name: str
    project_type: str
    languages: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    libraries: list[str] = field(default_factory=list)
    database: str = "Unknown"
    orm: str = "Unknown"
    build_system: str = "Unknown"
    package_manager: str = "Unknown"
    environment_summary: str = ""
    scripts: list[str] = field(default_factory=list)
    ports: list[int] = field(default_factory=list)
    testing_framework: str = "Unknown"
    deployment_strategy: str = "Unknown"
    repository_information: dict[str, Any] = field(default_factory=dict)
    architecture_summary: str = ""
    dependency_summary: str = ""
    risk_summary: list[str] = field(default_factory=list)
    health_score: float = 100.0
    metadata: dict[str, Any] = field(default_factory=dict)
    version: str = "1.0.0"


class DependencyAnalyzer:
    """Analyzes workspace configuration files to list libraries and external packages."""

    def analyze_dependencies(self, root: str) -> dict[str, Any]:
        """Parse requirements and configs to list libraries."""
        libraries = []
        package_json = os.path.join(root, "package.json")
        requirements_txt = os.path.join(root, "requirements.txt")
        pyproject_toml = os.path.join(root, "pyproject.toml")

        # Parse package.json
        if os.path.exists(package_json):
            try:
                with open(package_json, encoding="utf-8") as f:
                    content = f.read()
                    # Crude parsing of deps
                    for word in ["prisma", "react", "next", "express", "lodash"]:
                        if f'"{word}"' in content:
                            libraries.append(word)
            except Exception:
                pass

        # Parse requirements.txt
        if os.path.exists(requirements_txt):
            try:
                with open(requirements_txt, encoding="utf-8") as f:
                    for line in f:
                        clean = line.strip().split("==")[0].split(">=")[0]
                        if clean and not clean.startswith("#"):
                            libraries.append(clean)
            except Exception:
                pass

        # Parse pyproject.toml
        if os.path.exists(pyproject_toml):
            try:
                with open(pyproject_toml, encoding="utf-8") as f:
                    content = f.read()
                    for word in ["fastapi", "sqlalchemy", "pydantic", "uvicorn"]:
                        if word in content.lower():
                            libraries.append(word)
            except Exception:
                pass

        return {
            "libraries": libraries,
            "dependency_summary": f"Found {len(libraries)} primary packages dependencies.",
        }


class ArchitectureAnalyzer:
    """Scans project directory structures to resolve entrypoints and layer configurations."""

    def analyze_architecture(self, root: str) -> dict[str, Any]:
        """Detect entrypoints, route files, and structural conventions."""
        entry_points = []
        routing_strategy = "Unknown"
        database_layer = "None"
        auth_layer = "None"

        # Detect entry files
        entry_list = ["main.py", "app.py", "src/index.js", "src/main.ts", "index.js", "src/App.tsx"]
        for entry in entry_list:
            if os.path.exists(os.path.join(root, entry)):
                entry_points.append(entry)

        # Detect routing conventions
        has_src_app = os.path.exists(os.path.join(root, "src/app"))
        has_app_dir = os.path.exists(os.path.join(root, "app"))
        has_routes_dir = os.path.exists(os.path.join(root, "routes"))
        has_src_routes = os.path.exists(os.path.join(root, "src/routes"))

        if has_src_app or has_app_dir:
            routing_strategy = "File-system Routing (Next.js layout)"
        elif has_routes_dir or has_src_routes:
            routing_strategy = "Explicit routes directory mapping"

        # Detect Auth files
        for auth_marker in ["auth", "login", "jwt", "session"]:
            found = False
            for r, _d, f_names in os.walk(root):
                # Only check top-level and src/ folders to keep fast
                if "node_modules" in r or ".venv" in r or ".git" in r:
                    continue
                for f in f_names:
                    if auth_marker in f.lower():
                        auth_layer = "JWT / Session Auth module detected"
                        found = True
                        break
                if found:
                    break

        # Database layer detection
        if os.path.exists(os.path.join(root, "prisma")):
            database_layer = "Prisma Schema DB adapter"
        has_db_dir = os.path.exists(os.path.join(root, "database"))
        has_db_alias = os.path.exists(os.path.join(root, "db"))
        if has_db_dir or has_db_alias:
            database_layer = "Custom database adapters files"

        return {
            "entry_points": entry_points,
            "routing_strategy": routing_strategy,
            "database_layer": database_layer,
            "authentication_layer": auth_layer,
            "architecture_summary": f"Layout contains entry points: {entry_points}",
        }


class RiskAnalyzer:
    """Audits configurations to flag security gaps, version conflicts, or missing tests."""

    def analyze_risks(self, root: str) -> list[str]:
        """Assess risk points across settings files."""
        risks = []

        # 1. Missing environment configuration check
        if (
            not os.path.exists(os.path.join(root, ".env"))
            and not os.path.exists(os.path.join(root, ".env.example"))
            and not os.path.exists(os.path.join(root, ".env.local"))
        ):
            risks.append("Missing environment settings configs (.env files)")

        # 2. Missing test suites folder check
        has_tests = False
        for folder in ["tests", "test", "src/tests", "src/__tests__"]:
            if os.path.isdir(os.path.join(root, folder)):
                has_tests = True
                break
        if not has_tests:
            risks.append("Missing test suites coverage folders")

        # 3. Missing README file check
        has_readme = False
        for readme in ["README.md", "README.txt", "readme.md"]:
            if os.path.exists(os.path.join(root, readme)):
                has_readme = True
                break
        if not has_readme:
            risks.append("Missing readme project documentation files")

        return risks


class ProjectHealthAnalyzer:
    """Calculates standardized code health index metric score cards."""

    def calculate_health(self, risks: list[str], repo_info: dict[str, Any]) -> float:
        """Score project index out of 100 based on warnings count."""
        score = 100.0
        # Deduct per risk warning
        score -= len(risks) * 15.0

        # Bonus for repository tracking
        if repo_info.get("is_git"):
            score += 10.0
        else:
            score -= 15.0

        # Cap score limits
        return max(0.0, min(100.0, score))


class ProjectIntelligenceManager:
    """Unified manager generating Digital Twin objects and publishing intelligence events."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.dep_analyzer = DependencyAnalyzer()
        self.arch_analyzer = ArchitectureAnalyzer()
        self.risk_analyzer = RiskAnalyzer()
        self.health_analyzer = ProjectHealthAnalyzer()
        self.twins: dict[str, DigitalTwinObject] = {}
        self.lock = threading.Lock()

    def get_twin(self, project_id: str) -> DigitalTwinObject | None:
        """Retrieve Digital Twin details by ID."""
        with self.lock:
            return self.twins.get(project_id)

    def analyze_project(self, ws: WorkspaceObject) -> DigitalTwinObject:
        """Scan, build, and register the target workspace's Digital Twin."""
        root = ws.workspace_root
        if not os.path.isdir(root):
            raise ProjectIntelligenceError(f"Workspace path '{root}' is not a directory.")

        # 1. Run sub-analyzers
        deps = self.dep_analyzer.analyze_dependencies(root)
        arch = self.arch_analyzer.analyze_architecture(root)
        risks = self.risk_analyzer.analyze_risks(root)
        repo_status = ws.metadata.get("repository_status", {})
        health = self.health_analyzer.calculate_health(risks, repo_status)

        self.event_bus.publish_sync(
            Event(
                name="dependency_analysis.completed",
                category="Project",
                source="ProjectIntelligenceManager",
                payload={"project_id": ws.workspace_id},
            )
        )

        self.event_bus.publish_sync(
            Event(
                name="architecture_analysis.completed",
                category="Project",
                source="ProjectIntelligenceManager",
                payload={"project_id": ws.workspace_id},
            )
        )

        # 2. Build Twin
        twin = DigitalTwinObject(
            project_id=ws.workspace_id,
            project_name=ws.name,
            project_type=ws.project_type,
            languages=ws.language_stack,
            frameworks=ws.metadata.get("frameworks", []),
            libraries=deps["libraries"],
            database=ws.metadata.get("database", "Unknown"),
            orm=ws.metadata.get("orm", "Unknown"),
            build_system=ws.build_system,
            package_manager=ws.package_manager,
            environment_summary="Local env values references",
            repository_information=ws.metadata.get("repository_status", {}),
            architecture_summary=arch["architecture_summary"],
            dependency_summary=deps["dependency_summary"],
            risk_summary=risks,
            health_score=health,
            metadata=ws.metadata,
        )

        with self.lock:
            self.twins[ws.workspace_id] = twin

        self.event_bus.publish_sync(
            Event(
                name="project.analyzed",
                category="Project",
                source="ProjectIntelligenceManager",
                payload={"project_id": ws.workspace_id},
            )
        )

        self.event_bus.publish_sync(
            Event(
                name="digital_twin.created",
                category="Project",
                source="ProjectIntelligenceManager",
                payload={"project_id": ws.workspace_id},
            )
        )

        self.event_bus.publish_sync(
            Event(
                name="project_health.updated",
                category="Project",
                source="ProjectIntelligenceManager",
                payload={"project_id": ws.workspace_id, "score": health},
            )
        )

        return twin
