"""Enterprise OCR & Document Intelligence Platform subsystem for AIRA.

Defines OCR contracts, parses document structure geometries, and builds queryable layout graphs.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.perception_engine import ObservationBuilder, PerceptionEngine
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.document_ocr_intelligence")


class DocumentIntelligenceError(Exception):
    """Raised when document layout parsing or OCR provider operations fail."""

    pass


@dataclass
class RegionMetadata:
    """Geometrical bounding box representing parsed word or paragraph clusters."""

    region_id: str
    x: int
    y: int
    width: int
    height: int
    confidence: float
    language: str = "en"
    reading_order: int = 0
    # Map of target_id -> relationship type (e.g. child_of, inside_table)
    relationships: dict[str, str] = field(default_factory=dict)


@dataclass
class DocumentObject:
    """Structured representation of layout, pages, regions, tables, and form fields."""

    document_id: str
    pages: int = 1
    regions: list[RegionMetadata] = field(default_factory=list)
    blocks: list[dict[str, Any]] = field(default_factory=list)
    lines: list[dict[str, Any]] = field(default_factory=list)
    words: list[dict[str, Any]] = field(default_factory=list)
    tables: list[dict[str, Any]] = field(default_factory=list)
    forms: list[dict[str, Any]] = field(default_factory=list)
    language: str = "en"
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)
    version: str = "1.0.0"


class BaseOCRProvider(ABC):
    """Abstract interface defining interchangeable local and cloud OCR provider engines."""

    @abstractmethod
    def parse_document(self, image_path: str) -> DocumentObject:
        """Parse structured document layouts and extract geometry attributes."""
        pass


class MockOCRProvider(BaseOCRProvider):
    """Simulated OCR engine parsing documents with forms and table coordinates."""

    def parse_document(self, image_path: str) -> DocumentObject:
        region_title = RegionMetadata(
            region_id="reg_title",
            x=50,
            y=20,
            width=500,
            height=60,
            confidence=0.99,
            reading_order=1,
        )
        region_form = RegionMetadata(
            region_id="reg_form_name",
            x=50,
            y=120,
            width=400,
            height=40,
            confidence=0.97,
            reading_order=2,
        )

        return DocumentObject(
            document_id="doc_mock_01",
            pages=1,
            regions=[region_title, region_form],
            blocks=[
                {"block_id": "blk_01", "type": "Heading", "text": "Invoice Summary"},
                {"block_id": "blk_02", "type": "Form", "text": "Client Name: John Doe"},
            ],
            lines=[
                {"line_id": "line_01", "text": "Invoice Summary"},
                {"line_id": "line_02", "text": "Client Name: John Doe"},
            ],
            words=[
                {"word_id": "word_01", "text": "Invoice"},
                {"word_id": "word_02", "text": "Client"},
            ],
            tables=[{"table_id": "tbl_items", "columns": ["Item", "Cost"]}],
            forms=[{"field_name": "client_name", "field_value": "John Doe"}],
            language="en",
            confidence=0.98,
            metadata={"source_file": image_path},
        )


class LayoutAnalyzer:
    """Infers heading levels, lists, paragraphs, and reading order mappings."""

    def analyze_layout(self, doc: DocumentObject) -> list[dict[str, Any]]:
        """Group blocks into headings and paragraphs categories."""
        sections = []
        for blk in doc.blocks:
            blk_type = blk.get("type", "Paragraph")
            text = blk.get("text", "")
            sections.append(
                {
                    "section_id": f"sec_{blk.get('block_id', 'unknown')}",
                    "role": "Header" if blk_type == "Heading" else "Body",
                    "text": text,
                }
            )
        return sections


class DocumentStructureBuilder:
    """Assembles layout analysis payloads into finalized DocumentObjects."""

    def assemble(
        self, doc_id: str, regions: list[RegionMetadata], blocks: list[dict[str, Any]]
    ) -> DocumentObject:
        """Combine elements into a queryable DocumentObject."""
        return DocumentObject(
            document_id=doc_id,
            regions=regions,
            blocks=blocks,
        )


class DocumentGraph:
    """Tracks hierarchy boundaries linking pages, sections, forms, and word nodes."""

    def __init__(self) -> None:
        self.nodes: dict[str, Any] = {}
        # Map of source_id -> list of target_ids
        self.edges: dict[str, list[str]] = {}

    def build_graph(self, doc: DocumentObject) -> None:
        """Register pages, forms, and sections in the queryable graph."""
        # Add regions as nodes
        for reg in doc.regions:
            self.nodes[reg.region_id] = reg
            if reg.region_id not in self.edges:
                self.edges[reg.region_id] = []

            # Link pre-defined relationships
            for target, _ in reg.relationships.items():
                self.link(reg.region_id, target)

        # Add forms/tables nodes
        for f in doc.forms:
            fid = f.get("field_name", "unknown")
            self.nodes[fid] = f
            if fid not in self.edges:
                self.edges[fid] = []

    def link(self, source_id: str, target_id: str) -> None:
        """Create reference edge between nodes."""
        if source_id in self.edges and target_id not in self.edges[source_id]:
            self.edges[source_id].append(target_id)

    def query_relationships(self, node_id: str) -> list[str]:
        """Return IDs of nodes pointing to the target coordinate node."""
        return self.edges.get(node_id, [])


class DocumentOCRIntelligenceManager:
    """Unified manager coordinates OCR capture runs, validates graphs, and publishes Observations.

    This ensures provider logic remains interchangeable.
    """

    def __init__(
        self,
        config: AppConfig,
        registry: ServiceRegistry,
        event_bus: EventBus,
        perception_engine: PerceptionEngine,
    ) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus
        self.perception_engine = perception_engine

        # Default to simulated Mock OCR Provider
        self.provider: BaseOCRProvider = MockOCRProvider()
        self.layout_analyzer = LayoutAnalyzer()
        self.structure_builder = DocumentStructureBuilder()
        self.graph = DocumentGraph()

    def process_document_image(
        self, image_path: str, session_id: str | None = None
    ) -> DocumentObject:
        """Trigger OCR parsing, analyze layouts, build graphs, and publish standard observations."""
        self.event_bus.publish_sync(
            Event(
                name="ocr.completed",
                category="Perception",
                source="DocumentOCR",
                payload={"image_path": image_path},
            )
        )

        # 1. OCR Extract
        doc = self.provider.parse_document(image_path)
        self.event_bus.publish_sync(
            Event(
                name="document.parsed",
                category="Perception",
                source="DocumentOCR",
                payload={"document_id": doc.document_id, "confidence": doc.confidence},
            )
        )

        # 2. Layout Analysis
        sections = self.layout_analyzer.analyze_layout(doc)
        self.event_bus.publish_sync(
            Event(
                name="layout.built",
                category="Perception",
                source="DocumentOCR",
                payload={"sections_count": len(sections)},
            )
        )

        # 3. Graph Mappings
        self.graph.build_graph(doc)
        self.event_bus.publish_sync(
            Event(
                name="document.indexed",
                category="Perception",
                source="DocumentOCR",
                payload={"document_id": doc.document_id},
            )
        )

        # 4. Validate integrity constraints
        if doc.confidence < 0.0 or doc.confidence > 1.0:
            raise DocumentIntelligenceError(
                f"Document validation failed: Invalid confidence level {doc.confidence}."
            )

        # 5. Build Observation Object and publish to Perception Engine
        obs_builder = ObservationBuilder(
            f"obs_{doc.document_id}", "Documents", "StructuredDocument"
        )
        obs_builder.set_confidence(doc.confidence)
        obs_builder.set_content(
            {
                "document_id": doc.document_id,
                "language": doc.language,
                "regions_count": len(doc.regions),
                "tables_count": len(doc.tables),
                "forms_count": len(doc.forms),
            }
        )
        obs_builder.set_metadata("source_path", image_path)

        obs = obs_builder.build()
        self.perception_engine.process_observation(obs, session_id=session_id)

        self.event_bus.publish_sync(
            Event(
                name="observation.published",
                category="Perception",
                source="DocumentOCR",
                payload={"observation_id": obs.observation_id},
            )
        )

        return doc
