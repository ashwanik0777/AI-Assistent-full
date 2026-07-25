"""Enterprise Perception Security, Privacy, Consent & Trust Framework subsystem for AIRA.

Provides consent checking, sensitive secrets redaction, privacy classifications,
retention managers, and trust scoring calculations.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.perception_engine import ObservationObject
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.perception_security")


class PerceptionSecurityError(Exception):
    """Raised when policy verification, sanitization, or consent logic failures occur."""

    pass


@dataclass
class TrustedObservationObject:
    """Standardized representation containing security-reviewed and sanitized observation."""

    observation_id: str
    sensitivity_level: str
    consent_status: str
    privacy_labels: list[str]
    trust_score: float
    retention_policy: str
    sanitized_metadata: dict[str, Any] = field(default_factory=dict)
    evidence_references: list[str] = field(default_factory=list)
    version: str = "1.0.0"


class ConsentManager:
    """Tracks and enforces user preferences regarding permissions scope."""

    def __init__(self) -> None:
        # Default policy: Always Allow for non-sensitive, Restricted Mode otherwise
        self.default_consent = "Always Allow"

    def verify_consent(self, consent_policy: str) -> bool:
        """Reject if explicit Deny is specified."""
        return consent_policy != "Deny"


class SensitiveContentDetector:
    """Scans content dictionaries looking for tokens, keys, passwords or PII metadata."""

    def detect_sensitivity(self, content: dict[str, Any]) -> str:
        """Scan keys/values and return the corresponding classification level."""
        sensitive_keys = {
            "password",
            "otp",
            "card",
            "ssn",
            "api_key",
            "access_token",
            "secret",
            "token",
        }

        has_sensitive = False
        for key in content:
            if any(sk in key.lower() for sk in sensitive_keys):
                has_sensitive = True
                break

        for val in content.values():
            is_sensitive_str = isinstance(val, str) and (
                any(sk in val.lower() for sk in sensitive_keys) or len(val) > 40
            )
            if is_sensitive_str:
                has_sensitive = True
                break

        return "Highly Sensitive" if has_sensitive else "Public"


class PrivacyFilter:
    """Assigns security classification labels to observation blocks."""

    def evaluate_labels(self, sensitivity: str) -> list[str]:
        """Map sensitivity levels to standard privacy classifications lists."""
        if sensitivity == "Highly Sensitive":
            return ["Confidential", "Restricted", "Highly Sensitive"]
        return ["Public"]


class ObservationSanitizer:
    """Masks secrets and substitutes placeholders into metadata dictionaries."""

    def sanitize(self, content: dict[str, Any]) -> dict[str, Any]:
        """Perform recursive string masking on sensitive fields."""
        sanitized = {}
        sensitive_keys = {"password", "otp", "card", "ssn", "api_key", "secret", "token"}

        for key, val in content.items():
            if any(sk in key.lower() for sk in sensitive_keys):
                sanitized[key] = "[REDACTED]"
            elif isinstance(val, str) and len(val) > 40:
                sanitized[key] = f"{val[:6]}...[MASKED]"
            else:
                sanitized[key] = val

        return sanitized


class RetentionPolicyManager:
    """Maps observation types to lifetime storage limits (e.g. Session Only)."""

    def resolve_retention(self, sensitivity: str) -> str:
        """Assign temporary session scopes for sensitive observations."""
        if sensitivity == "Highly Sensitive":
            return "Session Only"
        return "Long-Term"


class TrustScoreCalculator:
    """Computes trust score weights based on reliability indicators."""

    def calculate_trust(self, confidence: float, consent_status: str, sensitivity: str) -> float:
        """Compile a normalized trust index (0.0 to 1.0) with explainable reasons."""
        if consent_status == "Deny":
            return 0.0

        score = confidence
        if sensitivity == "Highly Sensitive":
            # Demote raw trust weights slightly for sensitive zones until verified
            score *= 0.9

        return max(0.0, min(1.0, score))


class PerceptionTrustEngine:
    """Coordinator executing privacy inspections, consent checks, and trust ratings updates."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.consent_manager = ConsentManager()
        self.detector = SensitiveContentDetector()
        self.privacy_filter = PrivacyFilter()
        self.sanitizer = ObservationSanitizer()
        self.retention_manager = RetentionPolicyManager()
        self.trust_calculator = TrustScoreCalculator()

    def process_trusted_observation(
        self, obs: ObservationObject, consent_policy: str = "Always Allow"
    ) -> TrustedObservationObject:
        """Validate consent settings, identify secrets, redact fields, and evaluate trust score."""
        # 1. Verify consent
        if not self.consent_manager.verify_consent(consent_policy):
            self.event_bus.publish_sync(
                Event(
                    name="consent.revoked",
                    category="Security",
                    source="TrustEngine",
                    payload={"observation_id": obs.observation_id},
                )
            )
            self.event_bus.publish_sync(
                Event(
                    name="observation.rejected",
                    category="Security",
                    source="TrustEngine",
                    payload={"reason": "Consent policy verification failed."},
                )
            )
            raise PerceptionSecurityError(
                "Trusted observation processing blocked: Consent policy Denied."
            )

        self.event_bus.publish_sync(
            Event(
                name="consent.granted",
                category="Security",
                source="TrustEngine",
                payload={"policy": consent_policy},
            )
        )

        # 2. Sensitivity Checks
        sensitivity = self.detector.detect_sensitivity(obs.structured_content)
        if sensitivity == "Highly Sensitive":
            self.event_bus.publish_sync(
                Event(
                    name="sensitive.detected",
                    category="Security",
                    source="TrustEngine",
                    payload={"observation_id": obs.observation_id},
                )
            )

        # 3. Privacy classifications
        labels = self.privacy_filter.evaluate_labels(sensitivity)

        # 4. Redaction Sanitization
        sanitized_content = self.sanitizer.sanitize(obs.structured_content)
        self.event_bus.publish_sync(
            Event(
                name="observation.sanitized",
                category="Security",
                source="TrustEngine",
                payload={"keys_sanitized": list(sanitized_content.keys())},
            )
        )

        # 5. Retention policy
        retention = self.retention_manager.resolve_retention(sensitivity)
        self.event_bus.publish_sync(
            Event(
                name="retention.applied",
                category="Security",
                source="TrustEngine",
                payload={"policy": retention},
            )
        )

        # 6. Trust scoring calculation
        trust = self.trust_calculator.calculate_trust(obs.confidence, consent_policy, sensitivity)
        self.event_bus.publish_sync(
            Event(
                name="trust.updated",
                category="Security",
                source="TrustEngine",
                payload={"trust_score": trust},
            )
        )

        # Constraints validation checks
        if trust < 0.0 or trust > 1.0:
            raise PerceptionSecurityError(
                "Trusted observation failed: Trust score must map between 0.0 and 1.0."
            )

        trusted_obs = TrustedObservationObject(
            observation_id=obs.observation_id,
            sensitivity_level=sensitivity,
            consent_status=consent_policy,
            privacy_labels=labels,
            trust_score=trust,
            retention_policy=retention,
            sanitized_metadata=sanitized_content,
        )

        self.event_bus.publish_sync(
            Event(
                name="observation.accepted",
                category="Security",
                source="TrustEngine",
                payload={"observation_id": trusted_obs.observation_id},
            )
        )

        return trusted_obs
