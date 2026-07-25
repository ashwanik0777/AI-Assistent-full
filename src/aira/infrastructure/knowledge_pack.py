"""Enterprise Knowledge Pack Platform, Domain Intelligence & Knowledge Lifecycle Framework for AIRA.

Provides pack manifests, registries databases, validators, resolver logic routers, and indices.
"""

from dataclasses import dataclass, field
from typing import Any, ClassVar

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.knowledge_pack")


class KnowledgePackError(Exception):
    """Base exception raised for knowledge validation, indexing, or resolution failures."""

    pass


@dataclass
class KnowledgePackManifest:
    """Metadata detailing domain target profiles, languages supported, and compatibility bounds."""

    pack_id: str
    name: str
    version: str
    domains: list[str]
    supported_languages: list[str]
    compatibility: str = ">=0.9.0"
    license: str = "MIT"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class KnowledgePackRecord:
    """Active catalog tracking active state transitions."""

    manifest: KnowledgePackManifest
    lifecycle_state: str = "Draft"


class KnowledgeValidator:
    """Validates structural completeness and checks version bounds rules."""

    def __init__(self, platform_version: str = "0.9.0") -> None:
        self.platform_version = platform_version

    def validate_manifest(self, manifest: KnowledgePackManifest) -> None:
        """Check compatibility matrix and fields completeness."""
        # 1. Structural check
        if not manifest.domains or not manifest.supported_languages:
            raise KnowledgePackError(
                "Validation failed: Knowledge Pack must declare domains and supported languages."
            )

        # 2. Compatibility check
        req = manifest.compatibility.replace(">=", "").strip()
        p_parts = [int(x) for x in self.platform_version.split(".")]
        r_parts = [int(x) for x in req.split(".")]
        if p_parts < r_parts:
            raise KnowledgePackError(
                f"Validation failed: Incompatible version bounds. "
                f"Platform: '{self.platform_version}' vs Pack requires '{manifest.compatibility}'."
            )


class KnowledgeRegistry:
    """Keeps database entries tracking installed packages status."""

    VALID_TRANSITIONS: ClassVar[dict[str, set[str]]] = {
        "Draft": {"Verified", "Archived"},
        "Verified": {"Installed", "Archived"},
        "Installed": {"Enabled", "Archived", "Updated"},
        "Enabled": {"Disabled", "Deprecated", "Archived"},
        "Disabled": {"Enabled", "Archived"},
        "Deprecated": {"Archived"},
        "Archived": {"Draft"},
    }

    def __init__(self) -> None:
        self.records: dict[str, KnowledgePackRecord] = {}

    def register(self, record: KnowledgePackRecord) -> None:
        """Register entry."""
        self.records[record.manifest.pack_id] = record

    def get(self, pack_id: str) -> KnowledgePackRecord | None:
        """Fetch pack record."""
        return self.records.get(pack_id)

    def transition_state(self, record: KnowledgePackRecord, target_state: str) -> None:
        """Apply state transition or raise error."""
        current = record.lifecycle_state
        allowed = self.VALID_TRANSITIONS.get(current, set())
        if target_state not in allowed:
            raise KnowledgePackError(
                f"Lifecycle transition failed: Cannot move from '{current}' to '{target_state}'."
            )
        record.lifecycle_state = target_state


class KnowledgeIndex:
    """Maintains text content index mappings matching domains queries keys."""

    def __init__(self) -> None:
        # Maps domain -> list of textual content segments/facts
        self.index_store: dict[str, list[str]] = {}

    def index_pack_content(self, pack_id: str, domains: list[str], content: list[str]) -> None:
        """Save text elements in the indexing store."""
        for dom in domains:
            if dom not in self.index_store:
                self.index_store[dom] = []
            self.index_store[dom].extend(content)

    def query_index(self, domain: str) -> list[str]:
        """Retrieve indexed content segments."""
        return self.index_store.get(domain, [])


class KnowledgeResolver:
    """Selects and filters active packs based on domain matches and language requests."""

    def resolve_packs(
        self, domain: str, language: str, registry: KnowledgeRegistry
    ) -> list[KnowledgePackRecord]:
        """Find matching enabled packs."""
        matched = []
        for record in registry.records.values():
            if record.lifecycle_state != "Enabled":
                continue
            has_domain = domain in record.manifest.domains
            has_lang = language in record.manifest.supported_languages
            if has_domain and has_lang:
                matched.append(record)
        return matched


class KnowledgeRuntime:
    """Coordinating manager verifying packs, loading registries, indexing, and resolving queries."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.validator = KnowledgeValidator()
        self.knowledge_registry = KnowledgeRegistry()
        self.index = KnowledgeIndex()
        self.resolver = KnowledgeResolver()

    def install_knowledge_pack(
        self, manifest: KnowledgePackManifest, content: list[str]
    ) -> KnowledgePackRecord:
        """Validate, register record, transition states, and index contents facts."""
        # 1. Validate
        self.validator.validate_manifest(manifest)

        # 2. Register Record
        record = KnowledgePackRecord(manifest=manifest)
        self.knowledge_registry.register(record)

        self.knowledge_registry.transition_state(record, "Verified")
        self.knowledge_registry.transition_state(record, "Installed")

        self.event_bus.publish_sync(
            Event(
                name="knowledge_pack.installed",
                category="KnowledgePack",
                source="KnowledgeRuntime",
                payload={"pack_id": manifest.pack_id},
            )
        )

        # 3. Index Content
        self.index.index_pack_content(manifest.pack_id, manifest.domains, content)
        self.event_bus.publish_sync(
            Event(
                name="knowledge.indexed",
                category="KnowledgePack",
                source="KnowledgeRuntime",
                payload={"pack_id": manifest.pack_id, "indexed_domains": manifest.domains},
            )
        )

        return record

    def enable_knowledge_pack(self, pack_id: str) -> None:
        """Transition pack lifecycle status to Enabled."""
        record = self.knowledge_registry.get(pack_id)
        if not record:
            raise KnowledgePackError(f"Operation failed: Knowledge Pack '{pack_id}' not found.")

        self.knowledge_registry.transition_state(record, "Enabled")

        self.event_bus.publish_sync(
            Event(
                name="knowledge_pack.enabled",
                category="KnowledgePack",
                source="KnowledgeRuntime",
                payload={"pack_id": pack_id},
            )
        )

    def resolve_domain_knowledge(self, domain: str, language: str = "en") -> list[str]:
        """Filter matches and extract index content facts segments."""
        matched = self.resolver.resolve_packs(domain, language, self.knowledge_registry)
        results = []
        for _ in matched:
            results.extend(self.index.query_index(domain))

        self.event_bus.publish_sync(
            Event(
                name="knowledge.resolved",
                category="KnowledgePack",
                source="KnowledgeRuntime",
                payload={"domain": domain, "resolved_packs_count": len(matched)},
            )
        )

        return results
