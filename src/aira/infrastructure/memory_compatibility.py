"""Schema Versioning and Migrations Compatibility Framework for AIRA Memory.

Handles schemas transformations and backward compatibility rules between versions.
"""

from collections.abc import Callable
from typing import Any


class CompatibilityError(Exception):
    """Raised when schema version migrations or format compatibility checks fail."""

    pass


class MemorySchemaMigrationRegistry:
    """Registry holding migration procedures between schema version numbers."""

    def __init__(self) -> None:
        self.migrations: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {}

    def register_migration(
        self,
        from_version: str,
        to_version: str,
        migration_fn: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> None:
        """Register a transformation mapping between version keys."""
        self.migrations[f"{from_version}->{to_version}"] = migration_fn

    def migrate(
        self, payload: dict[str, Any], from_version: str, to_version: str
    ) -> dict[str, Any]:
        """Apply sequential migrations to align payload formats."""
        if from_version == to_version:
            return payload

        # Direct migration path lookup
        key = f"{from_version}->{to_version}"
        if key in self.migrations:
            return self.migrations[key](payload)

        # Basic multi-step pathfinder fallback (mock/framework support)
        msg = f"No direct migration path found from {from_version} to {to_version}"
        raise CompatibilityError(msg)


class MigrationEngine:
    """Evaluates payload headers and executes migration transitions."""

    def __init__(self) -> None:
        self.registry = MemorySchemaMigrationRegistry()
        self._setup_defaults()

    def _setup_defaults(self) -> None:
        """Register default alpha-1 format migrations rules."""

        def migration_1_to_2(payload: dict[str, Any]) -> dict[str, Any]:
            # Convert facts having deprecated formats to the confirmed Alpha-2 structure
            for fact in payload.get("facts", []):
                if "confidence" in fact and "confidence_score" not in fact:
                    fact["confidence_score"] = fact.pop("confidence")
            payload["schema_version"] = "2.0.0"
            return payload

        self.registry.register_migration("1.0.0", "2.0.0", migration_1_to_2)

    def validate_and_migrate(
        self, payload: dict[str, Any], current_system_version: str = "2.0.0"
    ) -> dict[str, Any]:
        """Verify headers and elevate incoming structures to match local system schemas."""
        payload_version = payload.get("schema_version", "1.0.0")
        return self.registry.migrate(payload, payload_version, current_system_version)
