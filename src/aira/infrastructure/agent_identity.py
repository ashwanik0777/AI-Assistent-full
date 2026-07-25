"""Enterprise Agent Identity, Reputation, Trust & Performance Platform for AIRA.

Provides identity managers, trust engines, reputation engines, and performance engines.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.agent_identity")


class AgentIdentityError(Exception):
    """Base exception raised for profile integrity failures or eligibility validation drifts."""

    pass


@dataclass
class AgentProfile:
    """Persistent agent profile specifying metadata, reputation, trust, and eligibility."""

    agent_id: str
    identity: dict[str, Any]  # Persistent ID, Agent Type, Owner, Domain
    capabilities: list[str]
    trust_level: float
    reputation_score: float
    performance_metrics: dict[str, Any]
    certifications: list[str]
    assignment_eligibility: bool
    lifecycle_state: str  # Registered, Active, Suspended
    metadata: dict[str, Any] = field(default_factory=dict)
    version: int = 1


class IdentityManager:
    """Maintains persistent registration records and histories of agent keys."""

    def __init__(self) -> None:
        self.profiles: dict[str, AgentProfile] = {}

    def register_profile(self, profile: AgentProfile) -> None:
        """Register profile and verify unique identifiers."""
        if profile.agent_id in self.profiles:
            raise AgentIdentityError(
                f"Registration failed: Profile '{profile.agent_id}' already exists."
            )
        self.profiles[profile.agent_id] = profile


class TrustEngine:
    """Evaluates compliance history, policy status, and certification credentials validity."""

    def evaluate_trust(self, violations_count: int, has_valid_cert: bool) -> float:
        """Calculate trust level value based on violations and certification validity."""
        base_trust = 0.95 if has_valid_cert else 0.75
        # Penalty for violations
        penalty = violations_count * 0.25
        return round(max(0.0, base_trust - penalty), 3)


class ReputationEngine:
    """Tracks historical outcome metrics, success trends, and task completions."""

    def calculate_reputation(self, success_count: int, fail_count: int) -> float:
        """Compute average success scores ratio."""
        total = success_count + fail_count
        if total == 0:
            return 0.5
        return float(success_count) / float(total)


class PerformanceEngine:
    """Measures completion durations, success rates, and evidence quality metrics."""

    def calculate_metrics(
        self, success_rate: float, avg_completion_time_sec: float, error_rate: float
    ) -> dict[str, Any]:
        """Verify ranges and format operational summary map."""
        if success_rate < 0.0 or success_rate > 100.0:
            raise AgentIdentityError("Invalid performance range for success rate.")
        return {
            "success_rate_pct": success_rate,
            "avg_time_sec": avg_completion_time_sec,
            "error_rate_pct": error_rate,
        }


class EligibilityManager:
    """Determines task suitability matching capabilities against trust level thresholds."""

    def verify_eligibility(
        self, profile: AgentProfile, required_caps: list[str], trust_threshold: float
    ) -> bool:
        """Verify that agent satisfies capability list and trust threshold."""
        if profile.lifecycle_state == "Suspended":
            return False

        # Match capabilities
        for cap in required_caps:
            if cap not in profile.capabilities:
                return False

        # Match trust threshold
        return not profile.trust_level < trust_threshold


class AgentIdentityPlatform:
    """Coordinating manager resolving agent identity lifecycle, trust, and eligibility."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.identity_manager = IdentityManager()
        self.trust_engine = TrustEngine()
        self.reputation_engine = ReputationEngine()
        self.performance_engine = PerformanceEngine()
        self.eligibility_manager = EligibilityManager()

    def register_agent_profile(
        self,
        agent_id: str,
        owner: str,
        domain: str,
        agent_type: str,
        capabilities: list[str],
        certifications: list[str],
    ) -> AgentProfile:
        """Create new profile record with initial default metrics."""
        ident = {
            "persistent_id": agent_id,
            "owner": owner,
            "domain": domain,
            "agent_type": agent_type,
        }
        profile = AgentProfile(
            agent_id=agent_id,
            identity=ident,
            capabilities=capabilities,
            trust_level=0.9,
            reputation_score=0.8,
            performance_metrics={
                "success_rate_pct": 100.0,
                "avg_time_sec": 0.0,
                "error_rate_pct": 0.0,
            },
            certifications=certifications,
            assignment_eligibility=True,
            lifecycle_state="Registered",
        )

        self.identity_manager.register_profile(profile)

        self.event_bus.publish_sync(
            Event(
                name="agent.profile.registered",
                category="AgentIdentity",
                source="AgentIdentityPlatform",
                payload={"agent_id": agent_id},
            )
        )

        return profile

    def update_agent_governance_state(
        self, agent_id: str, violations: int, has_cert: bool
    ) -> float:
        """Compute trust level, update profile, update eligibility, and dispatch event."""
        profile = self.identity_manager.profiles.get(agent_id)
        if not profile:
            raise AgentIdentityError(f"Profile not found: '{agent_id}'")

        # 1. Update Trust
        new_trust = self.trust_engine.evaluate_trust(violations, has_cert)
        profile.trust_level = new_trust

        self.event_bus.publish_sync(
            Event(
                name="agent.trust.updated",
                category="AgentIdentity",
                source="AgentIdentityPlatform",
                payload={"agent_id": agent_id, "trust": new_trust},
            )
        )

        # 2. Restrict eligibility if trust drops below critical limit (0.5)
        if new_trust < 0.5:
            profile.assignment_eligibility = False
            profile.lifecycle_state = "Suspended"

            self.event_bus.publish_sync(
                Event(
                    name="agent.eligibility.evaluated",
                    category="AgentIdentity",
                    source="AgentIdentityPlatform",
                    payload={"agent_id": agent_id, "eligible": False},
                )
            )

        return new_trust

    def record_agent_performance_run(
        self, agent_id: str, successes: int, failures: int, avg_time: float
    ) -> None:
        """Compute reputation, update performance stats, and dispatch events."""
        profile = self.identity_manager.profiles.get(agent_id)
        if not profile:
            raise AgentIdentityError(f"Profile not found: '{agent_id}'")

        # Update Reputation
        new_rep = self.reputation_engine.calculate_reputation(successes, failures)
        profile.reputation_score = new_rep

        self.event_bus.publish_sync(
            Event(
                name="agent.reputation.changed",
                category="AgentIdentity",
                source="AgentIdentityPlatform",
                payload={"agent_id": agent_id, "reputation": new_rep},
            )
        )

        # Update Performance
        total = successes + failures
        rate = (float(successes) / float(total)) * 100.0 if total > 0 else 100.0
        err = (float(failures) / float(total)) * 100.0 if total > 0 else 0.0

        perf = self.performance_engine.calculate_metrics(rate, avg_time, err)
        profile.performance_metrics = perf

        self.event_bus.publish_sync(
            Event(
                name="agent.performance.recorded",
                category="AgentIdentity",
                source="AgentIdentityPlatform",
                payload={"agent_id": agent_id},
            )
        )
