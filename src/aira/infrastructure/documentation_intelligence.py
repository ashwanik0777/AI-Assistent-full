"""Enterprise Documentation & Engineering Knowledge Intelligence subsystem for AIRA.

Tracks ADR registries, builds documentation graphs, and cross-references implementation drift.
"""

import time
from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.documentation_intelligence")


class DocumentationIntelligenceError(Exception):
    """Raised when documentation indexing, graph connections, or synchronizations fail."""

    pass


@dataclass
class DocMetadata:
    """Metadata metrics associated with an indexed documentation file node."""

    document_id: str
    document_type: str  # README, Architecture, API, CHANGELOG, ADR, etc.
    project_association: str
    version: str = "1.0.0"
    last_modified: float = field(default_factory=time.time)
    owner: str = "Engineering Team"
    coverage: float = 100.0
    health_score: float = 100.0
    related_documents: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ADRRecord:
    """Structured Architecture Decision Record representation."""

    decision_id: str
    decision_summary: str
    alternatives_considered: list[str]
    chosen_solution: str
    reasoning: str
    impact: str
    status: str = "Proposed"  # Proposed, Accepted, Rejected, Superseded
    future_review_date: str = ""


class DocumentationGraph:
    """Maintains connection mappings and traceability links between documented layers."""

    def __init__(self) -> None:
        self.nodes: dict[str, DocMetadata] = {}
        self.edges: dict[str, list[str]] = {}

    def add_document(self, doc: DocMetadata) -> None:
        """Register document node in graph state."""
        self.nodes[doc.document_id] = doc
        if doc.document_id not in self.edges:
            self.edges[doc.document_id] = []

    def link_documents(self, source_id: str, target_id: str) -> None:
        """Create cross-reference linkage edge between documents nodes."""
        if (
            source_id in self.edges
            and target_id in self.nodes
            and target_id not in self.edges[source_id]
        ):
            self.edges[source_id].append(target_id)
            self.nodes[source_id].related_documents.append(target_id)


class DocHealthAnalyzer:
    """Audits documents completeness, freshness, and checks cross-reference link mappings."""

    def evaluate_health(self, doc: DocMetadata) -> float:
        """Compute documentation health score deducting points for missing contents fields."""
        score = 100.0

        # Freshness deduction
        age_days = (time.time() - doc.last_modified) / 86400.0
        if age_days > 180:
            score -= 15.0  # deduction for out-of-date contents
        elif age_days > 90:
            score -= 5.0

        # Completeness checks
        if not doc.metadata.get("has_getting_started", True):
            score -= 10.0
        if not doc.metadata.get("has_api_references", True):
            score -= 15.0
        if not doc.metadata.get("has_troubleshooting", True):
            score -= 10.0

        doc.health_score = max(0.0, score)
        return doc.health_score


class KnowledgeSynchronizer:
    """Scans code-to-docs discrepancies to locate configuration drift warnings."""

    def analyze_drift(self, doc: DocMetadata, digital_twin: dict[str, Any]) -> dict[str, Any]:
        """Cross-reference documented versions to warn when out of sync."""
        inconsistencies = []
        doc_python = doc.metadata.get("python_version", "3.8")
        twin_python = digital_twin.get("python_version", "3.11")

        if doc_python != twin_python:
            inconsistencies.append(
                f"Documented Python version ({doc_python}) "
                f"does not match Digital Twin ({twin_python})"
            )

        doc_deps = doc.metadata.get("dependencies", [])
        twin_deps = digital_twin.get("dependencies", [])
        for dep in twin_deps:
            if dep not in doc_deps:
                inconsistencies.append(f"Missing documentation for dependency: {dep}")

        passed = len(inconsistencies) == 0
        return {
            "passed": passed,
            "document_id": doc.document_id,
            "inconsistencies": inconsistencies,
            "warnings_count": len(inconsistencies),
        }


class ADRManager:
    """Manages index states of Architecture Decision Records files."""

    def __init__(self) -> None:
        self.records: dict[str, ADRRecord] = {}

    def register_adr(self, record: ADRRecord) -> None:
        """Register architectural decisions details node."""
        self.records[record.decision_id] = record


class DocumentationIntelligenceManager:
    """Central coordinator mapping indexed files, health indexes, and code-docs drift audits."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.graph = DocumentationGraph()
        self.health_analyzer = DocHealthAnalyzer()
        self.synchronizer = KnowledgeSynchronizer()
        self.adr_manager = ADRManager()

    def index_document(self, doc: DocMetadata) -> None:
        """Register node in graph and publish index event."""
        if not doc.document_id or not doc.document_type:
            raise DocumentationIntelligenceError("Document ID and type are required.")

        self.graph.add_document(doc)

        self.event_bus.publish_sync(
            Event(
                name="documentation.indexed",
                category="Documentation",
                source="DocumentationIntelligenceManager",
                payload={"document_id": doc.document_id, "type": doc.document_type},
            )
        )

    def evaluate_doc_health(self, doc_id: str) -> float:
        """Run health audit evaluation metrics."""
        if doc_id not in self.graph.nodes:
            raise DocumentationIntelligenceError(f"Document '{doc_id}' not found in graph.")

        doc = self.graph.nodes[doc_id]
        score = self.health_analyzer.evaluate_health(doc)

        self.event_bus.publish_sync(
            Event(
                name="health.updated",
                category="Documentation",
                source="DocumentationIntelligenceManager",
                payload={"document_id": doc_id, "health_score": score},
            )
        )
        return score

    def register_adr(self, adr: ADRRecord) -> None:
        """Register ADR node and publish notification event."""
        self.adr_manager.register_adr(adr)

        self.event_bus.publish_sync(
            Event(
                name="adr.registered",
                category="Documentation",
                source="DocumentationIntelligenceManager",
                payload={"decision_id": adr.decision_id, "status": adr.status},
            )
        )

    def run_synchronization_check(
        self, doc_id: str, digital_twin: dict[str, Any]
    ) -> dict[str, Any]:
        """Cross-reference project state to detect documentation drift warnings."""
        if doc_id not in self.graph.nodes:
            raise DocumentationIntelligenceError(f"Document '{doc_id}' not found in graph.")

        doc = self.graph.nodes[doc_id]
        report = self.synchronizer.analyze_drift(doc, digital_twin)

        self.event_bus.publish_sync(
            Event(
                name="sync.completed",
                category="Documentation",
                source="DocumentationIntelligenceManager",
                payload=report,
            )
        )
        return report
