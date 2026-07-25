"""Enterprise Preference Intelligence, Personalization Engine & Adaptive Profile Framework for AIRA.

Provides preference profiles, validators, history trackers, and resolvers.
"""

import time
from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.preference_intelligence")


class PreferenceIntelligenceError(Exception):
    """Base exception raised for preference validation, policy conflicts, or rollback failures."""

    pass


@dataclass
class PreferenceProfile:
    """Explicit, versioned preference settings record."""

    preference_id: str
    scope: str  # Session, User, Team, Organization, System Default
    source: str
    confidence: float
    priority: int
    last_updated: float
    expiration: float
    override_rules: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    version: int = 1


class PreferenceValidator:
    """Validates preference compliance values and formatting parameters."""

    def validate(self, profile: PreferenceProfile) -> None:
        """Validate integrity and confidence bounds."""
        if not profile.preference_id or not profile.scope:
            raise PreferenceIntelligenceError(
                "Validation failed: Preference ID and Scope must be defined."
            )
        if profile.confidence < 0.0 or profile.confidence > 1.0:
            raise PreferenceIntelligenceError(
                f"Validation failed: Confidence '{profile.confidence}' is out of bounds."
            )


class PolicyResolver:
    """Resolves hierarchical overrides conflicts across Session, User, and Organization policies."""

    def resolve_conflict(
        self, user_pref: PreferenceProfile, org_pref: PreferenceProfile
    ) -> tuple[PreferenceProfile, str]:
        """Prioritize Organization settings unless User scope overrides are explicitly allowed."""
        # If Organization prohibits overrides completely, Organization wins
        allow_user_override = org_pref.override_rules.get("allow_user_override", True)
        if not allow_user_override:
            explanation = "Conflict resolved: Organization policy overrides User preference."
            return org_pref, explanation

        # Otherwise, compare priority score values
        if user_pref.priority >= org_pref.priority:
            explanation = "Conflict resolved: User override applied based on higher priority score."
            return user_pref, explanation
        else:
            explanation = "Conflict resolved: Organization policy applied based on higher priority."
            return org_pref, explanation


class PersonalizationEngine:
    """Applies active preferences overrides to personalize platform settings."""

    def apply_personalization(
        self, context: dict[str, Any], profile: PreferenceProfile
    ) -> dict[str, Any]:
        """Apply active properties (e.g. style output overrides) to the target context."""
        updated = context.copy()
        for key, val in profile.override_rules.items():
            updated[key] = val
        return updated


class PreferenceHistory:
    """Maintains snapshot updates enabling rollback checkpoints."""

    def __init__(self) -> None:
        # Maps preference_id -> list of profile snapshots
        self.history: dict[str, list[PreferenceProfile]] = {}

    def record_snapshot(self, profile: PreferenceProfile) -> None:
        """Append copy to ID history list."""
        self.history.setdefault(profile.preference_id, []).append(
            PreferenceProfile(
                preference_id=profile.preference_id,
                scope=profile.scope,
                source=profile.source,
                confidence=profile.confidence,
                priority=profile.priority,
                last_updated=profile.last_updated,
                expiration=profile.expiration,
                override_rules=profile.override_rules.copy(),
                metadata=profile.metadata.copy(),
                version=profile.version,
            )
        )

    def rollback(self, preference_id: str) -> PreferenceProfile:
        """Restore previous configuration snapshot or raise error if none exists."""
        snapshots = self.history.get(preference_id, [])
        if len(snapshots) < 2:
            raise PreferenceIntelligenceError(
                f"Rollback failed: No previous version snapshot exists for '{preference_id}'."
            )
        # Pop current, return previous
        snapshots.pop()
        return snapshots[-1]


class PreferenceManager:
    """Coordinating manager extracting settings and applying personalization."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.validator = PreferenceValidator()
        self.resolver = PolicyResolver()
        self.personalization_engine = PersonalizationEngine()
        self.history = PreferenceHistory()

        self.active_profiles: dict[str, PreferenceProfile] = {}

    def learn_preference(
        self,
        preference_id: str,
        scope: str,
        source: str,
        confidence: float,
        priority: int,
        override_rules: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> PreferenceProfile:
        """Validate preference, snapshot to history registry, and activate profile."""
        profile = PreferenceProfile(
            preference_id=preference_id,
            scope=scope,
            source=source,
            confidence=confidence,
            priority=priority,
            last_updated=time.time(),
            expiration=time.time() + 86400.0,
            override_rules=override_rules,
            metadata=metadata or {},
        )

        self.validator.validate(profile)

        # Handle version bump on update
        if preference_id in self.active_profiles:
            profile.version = self.active_profiles[preference_id].version + 1

        self.history.record_snapshot(profile)
        self.active_profiles[preference_id] = profile

        self.event_bus.publish_sync(
            Event(
                name="preference.learned",
                category="Preference",
                source="PreferenceManager",
                payload={"preference_id": preference_id, "version": profile.version},
            )
        )

        self.event_bus.publish_sync(
            Event(
                name="preference.updated",
                category="Preference",
                source="PreferenceManager",
                payload={"preference_id": preference_id, "scope": scope},
            )
        )

        self.event_bus.publish_sync(
            Event(
                name="profile.activated",
                category="Preference",
                source="PreferenceManager",
                payload={"preference_id": preference_id},
            )
        )

        return profile

    def resolve_and_activate(
        self, user_pref: PreferenceProfile, org_pref: PreferenceProfile
    ) -> PreferenceProfile:
        """Resolve conflict, activate matching profile, and notify event logs."""
        winner, explanation = self.resolver.resolve_conflict(user_pref, org_pref)

        self.active_profiles[winner.preference_id] = winner

        self.event_bus.publish_sync(
            Event(
                name="conflict.resolved",
                category="Preference",
                source="PreferenceManager",
                payload={
                    "preference_id": winner.preference_id,
                    "winner_scope": winner.scope,
                    "explanation": explanation,
                },
            )
        )

        return winner

    def rollback_preference(self, preference_id: str) -> PreferenceProfile:
        """Rollback profile configuration to previous snapshot checkpoint."""
        restored = self.history.rollback(preference_id)
        self.active_profiles[preference_id] = restored

        self.event_bus.publish_sync(
            Event(
                name="profile.archived",
                category="Preference",
                source="PreferenceManager",
                payload={"preference_id": preference_id, "restored_version": restored.version},
            )
        )

        return restored
