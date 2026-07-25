"""Developer Experience, Documentation, and Interactive Guidance Platform for AIRA.

Provides registries, explorers, learning tools, and analyzers.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.developer_dx")


class DocumentationPlatformError(Exception):
    """Base exception raised for doc validation drifts or outdated content versions."""

    pass


@dataclass
class DocPackage:
    """Document package metadata containing tutorials, guides, and migration steps."""

    package_id: str
    version: str
    api_references: dict[str, Any]
    sdk_references: list[str]
    tutorials: list[str]
    architecture_guides: list[str]
    examples: list[str]
    migration_guides: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)


class DocumentationRegistry:
    """Manages versioned knowledge assets portfolios database."""

    def __init__(self) -> None:
        self.packages: dict[str, DocPackage] = {}

    def register_package(self, doc: DocPackage) -> None:
        """Register documented package assets parameters."""
        self.packages[doc.package_id] = doc

    def validate_package(self, doc: DocPackage) -> None:
        """Verify API documentation coverage parameters."""
        # Reject if example mappings or api references mapping schemas are empty
        if not doc.api_references:
            raise DocumentationPlatformError(
                f"Validation failed: Package '{doc.package_id}' has empty api_references."
            )
        if not doc.examples:
            raise DocumentationPlatformError(
                f"Validation failed: Package '{doc.package_id}' has no examples templates."
            )


class InteractiveApiExplorer:
    """Queries current API Gateway contract definitions maps details."""

    def get_contract_endpoints(self, doc: DocPackage) -> list[str]:
        """Expose list of matching registered endpoints keys."""
        return list(doc.api_references.keys())


class LearningPlatform:
    """Stores structured learning paths and exercises."""

    def __init__(self) -> None:
        self.paths: dict[str, list[str]] = {}

    def publish_learning_path(self, path_id: str, modules: list[str]) -> None:
        """Save lesson roadmap structure."""
        self.paths[path_id] = modules


class AiDocAssistant:
    """Queries documentation registries using keyword parameters."""

    def search_guidance(self, registry: DocumentationRegistry, query: str) -> list[str]:
        """Find matching examples or guides terms."""
        results = []
        for pkg in registry.packages.values():
            for tut in pkg.tutorials:
                if query.lower() in tut.lower():
                    results.append(tut)
        return results


class BestPracticeAnalyzer:
    """Scans developer codebase targets and checks deprecations patterns."""

    def analyze_sdk_usage(self, sdk_version: str) -> list[str]:
        """Return warning suggestions list if SDK version drifts."""
        # Simple test mock triggers
        if sdk_version < "1.3.0":
            return ["Migration warning: SDK version is deprecated. Upgrade to 1.3.0."]
        return []


class DeveloperDxPlatform:
    """Coordinating manager resolving docs publication, explorers, and guidance updates."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.doc_registry = DocumentationRegistry()
        self.explorer = InteractiveApiExplorer()
        self.learning_platform = LearningPlatform()
        self.assistant = AiDocAssistant()
        self.analyzer = BestPracticeAnalyzer()

    def publish_documentation_package(
        self,
        package_id: str,
        version: str,
        api_references: dict[str, Any],
        sdk_references: list[str],
        tutorials: list[str],
        architecture_guides: list[str],
        examples: list[str],
        migration_guides: list[str],
    ) -> DocPackage:
        """Validate package assets coverage synchronization and publish events."""
        doc = DocPackage(
            package_id=package_id,
            version=version,
            api_references=api_references,
            sdk_references=sdk_references,
            tutorials=tutorials,
            architecture_guides=architecture_guides,
            examples=examples,
            migration_guides=migration_guides,
        )

        # 1. Run Registry Validations Checks
        self.doc_registry.validate_package(doc)

        # 2. Register package details
        self.doc_registry.register_package(doc)

        self.event_bus.publish_sync(
            Event(
                name="dx.documentation.validated",
                category="DeveloperExperience",
                source="DeveloperDxPlatform",
                payload={"package_id": package_id},
            )
        )

        self.event_bus.publish_sync(
            Event(
                name="dx.documentation.published",
                category="DeveloperExperience",
                source="DeveloperDxPlatform",
                payload={"package_id": package_id},
            )
        )

        return doc

    def update_explorer_reference(self, package_id: str) -> None:
        """Trigger API Explorer indexes update events."""
        self.event_bus.publish_sync(
            Event(
                name="dx.explorer.updated",
                category="DeveloperExperience",
                source="DeveloperDxPlatform",
                payload={"package_id": package_id},
            )
        )

    def release_learning_path(self, path_id: str, modules: list[str]) -> None:
        """Publish structured learning path tracks."""
        self.learning_platform.publish_learning_path(path_id, modules)

        self.event_bus.publish_sync(
            Event(
                name="dx.learning.path.released",
                category="DeveloperExperience",
                source="DeveloperDxPlatform",
                payload={"path_id": path_id},
            )
        )

    def check_sdk_compliance(self, sdk_version: str) -> dict[str, Any]:
        """Scan SDK tags compliance and format migration recommendations."""
        warnings = self.analyzer.analyze_sdk_usage(sdk_version)
        if warnings:
            self.event_bus.publish_sync(
                Event(
                    name="dx.migration.guide.generated",
                    category="DeveloperExperience",
                    source="DeveloperDxPlatform",
                    payload={"target_version": sdk_version},
                )
            )

        return {"version": sdk_version, "compliant": len(warnings) == 0, "warnings": warnings}
