"""Enterprise Extension Security, Supply Chain Trust & Software Integrity Platform for AIRA.

Provides integrity validators, publisher trust engines, and risk analyzers.
"""

from dataclasses import dataclass, field
from typing import Any, ClassVar

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.extension_security")


class ExtensionSecurityError(Exception):
    """Base exception raised for integrity violations or quarantine issues."""

    pass


@dataclass
class SecurityManifest:
    """Extension security credentials detailing hash bounds and license declarations."""

    extension_id: str
    publisher_id: str
    checksum: str
    dependencies: list[str]
    license: str = "MIT"
    trust_status: str = "Unverified"  # Verified, Revoked, Unverified
    version: str = "1.0.0"
    metadata: dict[str, Any] = field(default_factory=dict)


class IntegrityValidator:
    """Enforces manifest structural checks and mock checksum matches checks."""

    def validate_integrity(self, manifest: SecurityManifest) -> None:
        """Reject packages missing target manifest items or containing empty checksum hashes."""
        if not manifest.checksum or not manifest.extension_id:
            raise ExtensionSecurityError(
                "Integrity validation failed: Extension ID and Checksum hash must be provided."
            )


class PublisherTrustEngine:
    """Verifies publisher levels from local configuration registers."""

    def __init__(self) -> None:
        self.verified_publishers: set[str] = {"pub_verified_corp", "pub_trusted_org"}

    def is_publisher_trusted(self, publisher_id: str) -> bool:
        """Return True if the publisher key maps to trusted databases."""
        return publisher_id in self.verified_publishers


class DependencyRiskAnalyzer:
    """Analyzes transitive dependencies to report risk profiles indicators."""

    DEPRECATED_COMPONENTS: ClassVar[set[str]] = {"pycrypto", "urllib3<1.26.0", "requests<2.20.0"}

    def analyze_risk(self, dependencies: list[str]) -> list[str]:
        """Identify deprecated packages in use, return warnings report list."""
        warnings = []
        for dep in dependencies:
            if dep in self.DEPRECATED_COMPONENTS:
                warnings.append(f"Risk detected: Dependency '{dep}' is deprecated or insecure.")
        return warnings


class SBOMGenerator:
    """Creates standard inventories detailing licenses and dependencies targets."""

    def generate_sbom(self, manifest: SecurityManifest) -> dict[str, Any]:
        """Compile dictionary matching inventory rules."""
        return {
            "extension_id": manifest.extension_id,
            "version": manifest.version,
            "license": manifest.license,
            "inventory": manifest.dependencies.copy(),
            "metadata": manifest.metadata.copy(),
        }


class QuarantineManager:
    """Isolates high-risk packages to safeguard platform execution."""

    def __init__(self) -> None:
        self.quarantine_store: dict[str, dict[str, Any]] = {}

    def quarantine_package(self, extension_id: str, reason: str) -> None:
        """Add entry mapping extension id to quarantine registry."""
        self.quarantine_store[extension_id] = {
            "extension_id": extension_id,
            "reason": reason,
            "status": "Quarantined",
        }

    def remove_from_quarantine(self, extension_id: str) -> None:
        """Remove entry from quarantine store."""
        self.quarantine_store.pop(extension_id, None)

    def is_quarantined(self, extension_id: str) -> bool:
        """Return True if target extension is currently blocked."""
        return extension_id in self.quarantine_store


class RevocationRegistry:
    """Manages explicit revocations lists of malicious keys."""

    def __init__(self) -> None:
        self.revoked_publishers: set[str] = set()
        self.revoked_extensions: set[str] = set()

    def revoke_publisher(self, publisher_id: str) -> None:
        """Revoke publisher."""
        self.revoked_publishers.add(publisher_id)

    def revoke_extension(self, extension_id: str) -> None:
        """Revoke extension."""
        self.revoked_extensions.add(extension_id)

    def is_revoked(self, extension_id: str, publisher_id: str) -> bool:
        """Return True if extension or publisher ID is blacklisted."""
        is_ext = extension_id in self.revoked_extensions
        is_pub = publisher_id in self.revoked_publishers
        return is_ext or is_pub


class ExtensionSecurityManager:
    """Coordinating manager verifying integrity, auditing risk, and quarantining."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.integrity_validator = IntegrityValidator()
        self.trust_engine = PublisherTrustEngine()
        self.risk_analyzer = DependencyRiskAnalyzer()
        self.sbom_generator = SBOMGenerator()
        self.quarantine_manager = QuarantineManager()
        self.revocation_registry = RevocationRegistry()

    def process_security_review(self, manifest: SecurityManifest) -> bool:
        """Process checks, quarantine on failures, generate SBOM, and publish event reports."""
        # 1. Revocation checks
        if self.revocation_registry.is_revoked(manifest.extension_id, manifest.publisher_id):
            self.event_bus.publish_sync(
                Event(
                    name="publisher.revoked",
                    category="Security",
                    source="ExtensionSecurityManager",
                    payload={
                        "publisher_id": manifest.publisher_id,
                        "extension_id": manifest.extension_id,
                    },
                )
            )
            raise ExtensionSecurityError(
                f"Security check failed: Extension '{manifest.extension_id}' or "
                f"Publisher '{manifest.publisher_id}' is revoked."
            )

        # 2. Integrity checks
        self.integrity_validator.validate_integrity(manifest)
        self.event_bus.publish_sync(
            Event(
                name="integrity.verified",
                category="Security",
                source="ExtensionSecurityManager",
                payload={"extension_id": manifest.extension_id},
            )
        )

        # 3. Dependency Risk checks
        risks = self.risk_analyzer.analyze_risk(manifest.dependencies)
        if risks:
            self.event_bus.publish_sync(
                Event(
                    name="risk.detected",
                    category="Security",
                    source="ExtensionSecurityManager",
                    payload={"extension_id": manifest.extension_id, "risks_count": len(risks)},
                )
            )

            # Quarantine package
            reason = "; ".join(risks)
            self.quarantine_manager.quarantine_package(manifest.extension_id, reason)
            self.event_bus.publish_sync(
                Event(
                    name="package.quarantined",
                    category="Security",
                    source="ExtensionSecurityManager",
                    payload={"extension_id": manifest.extension_id, "reason": reason},
                )
            )
            return False

        # 4. Generate SBOM
        self.sbom_generator.generate_sbom(manifest)
        self.event_bus.publish_sync(
            Event(
                name="sbom.generated",
                category="Security",
                source="ExtensionSecurityManager",
                payload={"extension_id": manifest.extension_id},
            )
        )

        self.event_bus.publish_sync(
            Event(
                name="security.audit_updated",
                category="Security",
                source="ExtensionSecurityManager",
                payload={"extension_id": manifest.extension_id, "status": "Approved"},
            )
        )

        return True
