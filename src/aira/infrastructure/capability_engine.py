"""Capability Engine and Registry subsystem for AIRA.

Manages capabilities metadata, matching resolver logic, and platform validations.
"""

import sys
import threading
from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.capability_engine")


class CapabilityError(Exception):
    """Raised when capability registry lookup, validations checks, or resolution fails."""

    pass


@dataclass
class CapabilityObject:
    """Dataclass holding complete capability configuration attributes."""

    capability_id: str
    name: str
    description: str
    supported_platforms: list[str] = field(default_factory=list)
    required_skills: list[str] = field(default_factory=list)
    required_permissions: list[str] = field(default_factory=list)
    required_workspace_context: bool = False
    required_memory_context: bool = False
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    version: str = "1.0.0"


class CapabilityRegistry:
    """In-memory registry tracking available capabilities definitions."""

    def __init__(self) -> None:
        self._capabilities: dict[str, CapabilityObject] = {}
        self.lock = threading.Lock()

    def register(self, cap: CapabilityObject) -> None:
        """Register a new capability config."""
        with self.lock:
            if cap.capability_id in self._capabilities:
                raise CapabilityError(f"Capability '{cap.capability_id}' already registered.")
            self._capabilities[cap.capability_id] = cap

    def get(self, capability_id: str) -> CapabilityObject | None:
        """Retrieve capability details by ID."""
        with self.lock:
            return self._capabilities.get(capability_id)

    def list_all(self) -> list[CapabilityObject]:
        """List all registered capabilities."""
        with self.lock:
            return list(self._capabilities.values())


class CapabilityValidator:
    """Validates capability invariants and platform constraints."""

    def validate_capability(self, cap: CapabilityObject, current_platform: str) -> None:
        """Assert capability platform support compatibility."""
        if cap.supported_platforms and current_platform not in cap.supported_platforms:
            msg = f"Platform '{current_platform}' not supported by capability '{cap.capability_id}'"
            raise CapabilityError(msg)


class CapabilityResolver:
    """Matches requested query patterns to target capability candidates."""

    def resolve_capability(
        self, query: str, registry: CapabilityRegistry
    ) -> CapabilityObject | None:
        """Fuzzy match query text to registered capability names/descriptions."""
        candidates = registry.list_all()
        # Basic matching heuristic checks
        for cap in candidates:
            if cap.name.lower() in query.lower() or cap.description.lower() in query.lower():
                return cap
        return None


class CapabilityEngine:
    """Unified coordinator managing registries, validators, and events."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.cap_registry = CapabilityRegistry()
        self.validator = CapabilityValidator()
        self.resolver = CapabilityResolver()
        self.lock = threading.Lock()

    def register_capability(self, cap: CapabilityObject) -> None:
        """Publish and register a new capability to the registry."""
        with self.lock:
            self.cap_registry.register(cap)
            self.event_bus.publish_sync(
                Event(
                    name="capability.registered",
                    category="Capability",
                    source="CapabilityEngine",
                    payload={"capability_id": cap.capability_id},
                )
            )

    def resolve_and_validate(self, query: str, platform: str = sys.platform) -> CapabilityObject:
        """Resolve a query to a capability and validate platform invariants."""
        with self.lock:
            cap = self.resolver.resolve_capability(query, self.cap_registry)
            if not cap:
                raise CapabilityError(f"No suitable capability found matching query: '{query}'")

            self.event_bus.publish_sync(
                Event(
                    name="capability.resolved",
                    category="Capability",
                    source="CapabilityEngine",
                    payload={"capability_id": cap.capability_id},
                )
            )

            self.validator.validate_capability(cap, platform)

            self.event_bus.publish_sync(
                Event(
                    name="capability.validated",
                    category="Capability",
                    source="CapabilityEngine",
                    payload={"capability_id": cap.capability_id},
                )
            )

            return cap
