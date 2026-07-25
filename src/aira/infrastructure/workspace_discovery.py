"""Enterprise Workspace Discovery & Project Detection Engine subsystem for AIRA.

Scans workspace directories to identify language stacks, frameworks, databases, and git branches.
"""

import contextlib
import os
import time
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry
from aira.infrastructure.workspace_engine import WorkspaceObject, WorkspaceRegistry

logger = structlog.get_logger("aira.workspace_discovery")


class WorkspaceDiscoveryError(Exception):
    """Raised when scan validations fail or conflicts are detected in workspace structures."""

    pass


class ProjectDetector:
    """Detects languages and framework layouts (Next.js, Spring Boot, FastAPI, etc.)."""

    def detect_projects(self, root: str) -> dict[str, Any]:
        """Detect languages and frameworks based on directory structure configurations."""
        frameworks = []
        languages = []
        project_type = "Unknown"

        # Node.js / React / Next.js
        if os.path.exists(os.path.join(root, "package.json")):
            languages.append("JavaScript/TypeScript")
            project_type = "Node.js Project"
            frameworks.append("Node.js")

            # Check Next.js
            has_next_js = os.path.exists(os.path.join(root, "next.config.js"))
            has_next_mjs = os.path.exists(os.path.join(root, "next.config.mjs"))
            if has_next_js or has_next_mjs:
                frameworks.append("Next.js")
                project_type = "Next.js Project"
            # Check React in package.json
            try:
                with open(os.path.join(root, "package.json"), encoding="utf-8") as f:
                    content = f.read()
                    if '"react"' in content:
                        frameworks.append("React")
            except Exception:
                pass

        # Python / FastAPI / Django / Flask
        elif (
            os.path.exists(os.path.join(root, "pyproject.toml"))
            or os.path.exists(os.path.join(root, "requirements.txt"))
            or os.path.exists(os.path.join(root, "setup.py"))
        ):
            languages.append("Python")
            project_type = "Python Project"

            # Check FastAPI, Django, Flask imports
            requirements_files = ["requirements.txt", "pyproject.toml"]
            for req_file in requirements_files:
                path = os.path.join(root, req_file)
                if os.path.exists(path):
                    try:
                        with open(path, encoding="utf-8") as f:
                            text = f.read().lower()
                            if "fastapi" in text:
                                frameworks.append("FastAPI")
                                project_type = "FastAPI Project"
                            if "django" in text:
                                frameworks.append("Django")
                                project_type = "Django Project"
                            if "flask" in text:
                                frameworks.append("Flask")
                                project_type = "Flask Project"
                    except Exception:
                        pass

        # Java / Spring Boot
        elif os.path.exists(os.path.join(root, "pom.xml")) or os.path.exists(
            os.path.join(root, "build.gradle")
        ):
            languages.append("Java")
            project_type = "Java Project"
            has_pom = os.path.exists(os.path.join(root, "pom.xml"))
            path = os.path.join(root, "pom.xml") if has_pom else os.path.join(root, "build.gradle")
            try:
                with open(path, encoding="utf-8") as f:
                    text = f.read().lower()
                    if "spring-boot" in text or "springboot" in text:
                        frameworks.append("Spring Boot")
                        project_type = "Spring Boot Project"
            except Exception:
                pass

        # Go
        elif os.path.exists(os.path.join(root, "go.mod")):
            languages.append("Go")
            project_type = "Go Project"

        # Rust
        elif os.path.exists(os.path.join(root, "Cargo.toml")):
            languages.append("Rust")
            project_type = "Rust Project"

        return {"project_type": project_type, "languages": languages, "frameworks": frameworks}


class TechnologyDetector:
    """Identifies package managers, ORMs, DB configs, testing tools, and Docker setups."""

    def detect_technologies(self, root: str) -> dict[str, Any]:
        """Detect supporting infrastructure databases, package managers, and Docker setups."""
        tech_stack = []
        package_manager = "Unknown"
        build_tool = "Unknown"
        orm = "Unknown"
        database = "Unknown"
        containerization = "None"
        testing_framework = "Unknown"
        linting_tool = "Unknown"

        # Package managers & build tools
        if os.path.exists(os.path.join(root, "package-lock.json")):
            package_manager = "npm"
            build_tool = "npm run build"
        elif os.path.exists(os.path.join(root, "yarn.lock")):
            package_manager = "yarn"
            build_tool = "yarn build"
        elif os.path.exists(os.path.join(root, "poetry.lock")):
            package_manager = "Poetry"
            build_tool = "poetry build"
        elif os.path.exists(os.path.join(root, "requirements.txt")):
            package_manager = "pip"
        elif os.path.exists(os.path.join(root, "Cargo.toml")):
            package_manager = "cargo"
            build_tool = "cargo build"
        elif os.path.exists(os.path.join(root, "pom.xml")):
            package_manager = "Maven"
            build_tool = "mvn clean package"
        elif os.path.exists(os.path.join(root, "build.gradle")):
            package_manager = "Gradle"
            build_tool = "gradle build"

        # ORM & Database configuration scans
        # Prisma detection
        if os.path.exists(os.path.join(root, "prisma/schema.prisma")):
            orm = "Prisma"
            tech_stack.append("Prisma ORM")
            try:
                with open(os.path.join(root, "prisma/schema.prisma"), encoding="utf-8") as f:
                    text = f.read()
                    if 'provider = "postgresql"' in text:
                        database = "PostgreSQL"
                    elif 'provider = "sqlite"' in text:
                        database = "SQLite"
            except Exception:
                pass

        # SQLAlchemy / Alembic
        elif os.path.exists(os.path.join(root, "alembic.ini")):
            orm = "SQLAlchemy/Alembic"
            tech_stack.append("SQLAlchemy")

        # Docker detection
        if os.path.exists(os.path.join(root, "Dockerfile")):
            containerization = "Docker"
            tech_stack.append("Docker")

        # Testing & Linting
        has_pytest = os.path.exists(os.path.join(root, "pytest.ini"))
        has_tests_dir = os.path.exists(os.path.join(root, "tests/"))
        if has_pytest or has_tests_dir:
            testing_framework = "pytest"
        if os.path.exists(os.path.join(root, "pyproject.toml")):
            try:
                with open(os.path.join(root, "pyproject.toml"), encoding="utf-8") as f:
                    text = f.read().lower()
                    if "ruff" in text:
                        linting_tool = "Ruff"
            except Exception:
                pass

        return {
            "tech_stack": tech_stack,
            "package_manager": package_manager,
            "build_tool": build_tool,
            "orm": orm,
            "database": database,
            "containerization": containerization,
            "testing_framework": testing_framework,
            "linting_tool": linting_tool,
        }


class RepositoryDetector:
    """Extracts git default branch, current branch, and remote URL metadata cleanly from disk."""

    def detect_repository(self, root: str) -> dict[str, Any]:
        """Parse local Git configuration files safely without CLI command execution."""
        git_dir = os.path.join(root, ".git")
        if not os.path.isdir(git_dir):
            return {"is_git": False, "current_branch": "None", "remote_url": "None"}

        current_branch = "Unknown"
        remote_url = "None"

        # 1. Parse current branch from HEAD
        head_path = os.path.join(git_dir, "HEAD")
        if os.path.exists(head_path):
            try:
                with open(head_path, encoding="utf-8") as f:
                    line = f.read().strip()
                    if line.startswith("ref:"):
                        ref = line.replace("ref:", "").strip()
                        if ref.startswith("refs/heads/"):
                            current_branch = ref.replace("refs/heads/", "").strip()
                        else:
                            current_branch = ref
                    else:
                        # Detached head (short hash)
                        current_branch = line[:7]
            except Exception:
                pass

        # 2. Parse remote url from config file
        config_path = os.path.join(git_dir, "config")
        if os.path.exists(config_path):
            try:
                with open(config_path, encoding="utf-8") as f:
                    content = f.read()
                    for line in content.splitlines():
                        if "url =" in line:
                            remote_url = line.split("=")[-1].strip()
                            break
            except Exception:
                pass

        return {"is_git": True, "current_branch": current_branch, "remote_url": remote_url}


class WorkspaceDiscoveryValidator:
    """Asserts scanned path exists and technology configurations are consistent."""

    def validate_discovery(self, path: str) -> None:
        """Reject paths that are not valid directories."""
        if not os.path.isdir(path):
            msg = f"Scanned path '{path}' does not exist or is not a directory."
            raise WorkspaceDiscoveryError(msg)


class WorkspaceMetadataBuilder:
    """Builds structured technology profiles dictionaries."""

    def build_metadata(
        self, path: str, proj: dict[str, Any], tech: dict[str, Any], repo: dict[str, Any]
    ) -> dict[str, Any]:
        """Compile a single unified metadata dictionary representation."""
        # Simple directory summary snippet helper
        files = []
        with contextlib.suppress(Exception):
            files = [f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))][:10]

        return {
            "workspace_id": f"ws_{os.path.basename(path).lower()}",
            "project_name": os.path.basename(path),
            "project_type": proj["project_type"],
            "languages": proj["languages"],
            "frameworks": proj["frameworks"],
            "package_manager": tech["package_manager"],
            "build_tool": tech["build_tool"],
            "repository_status": {
                "is_git": repo["is_git"],
                "current_branch": repo["current_branch"],
                "remote_url": repo["remote_url"],
            },
            "detected_configuration_files": files,
            "directory_structure_summary": f"Contains {len(files)} top-level files.",
            "technology_stack": tech["tech_stack"],
            "database": tech["database"],
            "orm": tech["orm"],
            "confidence_score": 1.0 if proj["languages"] else 0.5,
            "discovery_timestamp": time.time(),
        }


class WorkspaceDiscoveryManager:
    """Unified manager scanning workspace folder paths and emitting discovery events."""

    def __init__(
        self,
        config: AppConfig,
        registry: ServiceRegistry,
        event_bus: EventBus,
        workspace_registry: WorkspaceRegistry,
    ) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus
        self.workspace_registry = workspace_registry

        self.project_detector = ProjectDetector()
        self.tech_detector = TechnologyDetector()
        self.repo_detector = RepositoryDetector()
        self.validator = WorkspaceDiscoveryValidator()
        self.metadata_builder = WorkspaceMetadataBuilder()

    def discover_workspace(self, path: str) -> WorkspaceObject:
        """Scan, build, and register the target workspace path metadata."""
        self.validator.validate_discovery(path)

        # 1. Detect subcomponents
        proj = self.project_detector.detect_projects(path)
        tech = self.tech_detector.detect_technologies(path)
        repo = self.repo_detector.detect_repository(path)

        # Publish discovery status stages
        self.event_bus.publish_sync(
            Event(
                name="workspace.discovered",
                category="Workspace",
                source="WorkspaceDiscoveryManager",
                payload={"path": path},
            )
        )

        self.event_bus.publish_sync(
            Event(
                name="project.detected",
                category="Workspace",
                source="WorkspaceDiscoveryManager",
                payload={"project_type": proj["project_type"]},
            )
        )

        self.event_bus.publish_sync(
            Event(
                name="technology.identified",
                category="Workspace",
                source="WorkspaceDiscoveryManager",
                payload={"languages": proj["languages"], "tech_stack": tech["tech_stack"]},
            )
        )

        if repo["is_git"]:
            self.event_bus.publish_sync(
                Event(
                    name="repository.registered",
                    category="Workspace",
                    source="WorkspaceDiscoveryManager",
                    payload={"branch": repo["current_branch"]},
                )
            )

        # 2. Build structured metadata
        meta = self.metadata_builder.build_metadata(path, proj, tech, repo)

        ws = WorkspaceObject(
            workspace_id=meta["workspace_id"],
            name=meta["project_name"],
            workspace_root=path,
            project_type=meta["project_type"],
            technology_stack=meta["technology_stack"],
            language_stack=meta["languages"],
            build_system=meta["build_tool"],
            package_manager=meta["package_manager"],
            repository_info=meta["repository_status"]["remote_url"],
            metadata=meta,
        )

        # 3. Register or update Workspace Registry
        self.workspace_registry.register(ws)

        self.event_bus.publish_sync(
            Event(
                name="workspace.metadata_updated",
                category="Workspace",
                source="WorkspaceDiscoveryManager",
                payload={"workspace_id": ws.workspace_id},
            )
        )

        return ws
