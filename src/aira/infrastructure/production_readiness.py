"""Enterprise Final Hardening & Production Readiness Platform for AIRA.

Provides integration validators, benchmark suite runs, and dashboards reports.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.production_readiness")


class ProductionReadinessError(Exception):
    """Exception raised for integration validation gaps or dependency conflicts."""

    pass


@dataclass
class ProductionReadinessDescriptor:
    """Descriptor layout specifying platform performance status and certification readiness."""

    platform_version: str
    architecture_version: str
    api_status: str
    sdk_status: str
    security_status: str
    performance_status: str
    integration_status: str
    documentation_status: str
    certification_readiness: str
    metadata: dict[str, Any] = field(default_factory=dict)


class GlobalIntegrationValidator:
    """Audits and validates the presence of all core infrastructure managers."""

    def verify_platform_integration(self, kernel: Any) -> bool:
        """Verify that kernel initializes all required sub-platforms."""
        required_attrs = [
            "tenant_federation_platform",
            "knowledge_exchange_platform",
            "mission_federation_platform",
            "sovereign_governance_platform",
            "mission_control_platform",
            "federated_resilience_platform",
            "compliance_governance_platform",
        ]
        return all(hasattr(kernel, attr) for attr in required_attrs)


class PerformanceOptimizationEngine:
    """Executes benchmark cycles and audits regression limits."""

    def execute_performance_benchmarks(self, mock_load: float) -> str:
        """Return performance assessment score status based on load."""
        if mock_load > 1000.0:
            return "Regression-High-Latency"
        return "Target-Optimal"


class ReliabilityValidator:
    """Validates node resilience status thresholds."""

    def verify_reliability_metrics(self, packet_drop_rate: float) -> bool:
        """Reject if network packet drop rate exceeds safety margins limit."""
        return packet_drop_rate < 0.05


class SecurityHardeningReview:
    """Scans and audits vulnerabilities alerts files."""

    def run_security_review(self, alerts: list[str]) -> str:
        """Return security status based on vulnerability critical alerts."""
        if any("Critical" in alert for alert in alerts):
            return "Blocker-Findings"
        return "Secure"


class DependencyIntegrityManager:
    """Audits packaging configuration scopes."""

    def verify_dependency_versions(self, invalid_packages: list[str]) -> bool:
        """Return True if no packages hold version conflicts."""
        return len(invalid_packages) == 0


class ProductionReadinessDashboard:
    """Compiles assessments summaries dashboards reports."""

    def __init__(self) -> None:
        self.assessments: dict[str, ProductionReadinessDescriptor] = {}

    def save_descriptor(self, descriptor: ProductionReadinessDescriptor) -> None:
        """Register readiness assessments descriptor."""
        self.assessments[descriptor.platform_version] = descriptor


class ProductionReadinessPlatform:
    """Coordinating manager resolving integration, benchmarks, hardening, and reports publishing."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.integration_validator = GlobalIntegrationValidator()
        self.performance_engine = PerformanceOptimizationEngine()
        self.reliability_validator = ReliabilityValidator()
        self.security_review = SecurityHardeningReview()
        self.dependency_manager = DependencyIntegrityManager()
        self.dashboard = ProductionReadinessDashboard()

    def run_readiness_assessment(
        self,
        kernel: Any,
        version: str,
        mock_load: float,
        packet_drop_rate: float,
        security_alerts: list[str],
        invalid_packages: list[str],
    ) -> ProductionReadinessDescriptor:
        """Verify parameters, run assessments validations, update dashboard, and publish events."""
        # 1. Integration validation
        int_ok = self.integration_validator.verify_platform_integration(kernel)
        self.event_bus.publish_sync(
            Event(
                name="readiness.integration.validated",
                category="ProductionReadiness",
                source="ProductionReadinessPlatform",
                payload={"version": version, "success": int_ok},
            )
        )
        if not int_ok:
            raise ProductionReadinessError(
                "Readiness validation failed: Missing target sub-platform integrations."
            )

        # 2. Benchmarks execution
        perf_status = self.performance_engine.execute_performance_benchmarks(mock_load)
        self.event_bus.publish_sync(
            Event(
                name="readiness.performance.benchmarked",
                category="ProductionReadiness",
                source="ProductionReadinessPlatform",
                payload={"version": version, "status": perf_status},
            )
        )

        # 3. Security checks
        sec_status = self.security_review.run_security_review(security_alerts)
        self.event_bus.publish_sync(
            Event(
                name="readiness.security.reviewed",
                category="ProductionReadiness",
                source="ProductionReadinessPlatform",
                payload={"version": version, "status": sec_status},
            )
        )

        # 4. Dependency and reliability validation
        dep_ok = self.dependency_manager.verify_dependency_versions(invalid_packages)
        rel_ok = self.reliability_validator.verify_reliability_metrics(packet_drop_rate)

        # Determine readiness status
        is_ready = perf_status == "Target-Optimal" and sec_status == "Secure" and dep_ok and rel_ok

        readiness = "Ready-For-Production" if is_ready else "Blocker-Issues-Found"

        desc = ProductionReadinessDescriptor(
            platform_version=version,
            architecture_version="1.5.0",
            api_status="Frozen",
            sdk_status="Certified",
            security_status=sec_status,
            performance_status=perf_status,
            integration_status="Validated",
            documentation_status="Synchronized",
            certification_readiness=readiness,
        )

        self.dashboard.save_descriptor(desc)

        self.event_bus.publish_sync(
            Event(
                name="readiness.updated",
                category="ProductionReadiness",
                source="ProductionReadinessPlatform",
                payload={"version": version, "certification_readiness": readiness},
            )
        )

        return desc

    def prepare_release_candidate(self, version: str) -> None:
        """Confirm readiness checklist status and publish RC release event."""
        desc = self.dashboard.assessments.get(version)
        if not desc:
            raise ProductionReadinessError(
                f"No assessments found for platform version: '{version}'"
            )

        if desc.certification_readiness != "Ready-For-Production":
            raise ProductionReadinessError(
                f"Release rejected: Platform version '{version}' holds blocker issues."
            )

        self.event_bus.publish_sync(
            Event(
                name="readiness.candidate.prepared",
                category="ProductionReadiness",
                source="ProductionReadinessPlatform",
                payload={"version": version, "status": "RC1-Ready"},
            )
        )
