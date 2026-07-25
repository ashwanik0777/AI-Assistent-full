"""Enterprise Platform Operations, Telemetry & Ecosystem Intelligence Platform for AIRA.

Provides telemetry collectors, metrics pipelines, health analyzers, and dashboards generators.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.platform_telemetry")


class PlatformOperationsTelemetryError(Exception):
    """Base exception raised for telemetry failures, privacy violations, or dashboard errors."""

    pass


@dataclass
class TelemetryRecord:
    """Record parameters detailing operational outputs and compliance scopes."""

    timestamp: float
    component: str
    environment: str
    event_type: str
    metrics: dict[str, Any]
    severity: str = "INFO"  # INFO, WARNING, ERROR
    privacy_classification: str = "Public"  # Public, Protected, PII
    metadata: dict[str, Any] = field(default_factory=dict)
    version: str = "1.0.0"


class PrivacyManager:
    """Filters records based on consent constraints, stripping protected indicators."""

    def __init__(self, is_opt_in: bool = True) -> None:
        self.is_opt_in = is_opt_in

    def process_record(self, record: TelemetryRecord) -> TelemetryRecord | None:
        """Filter out protected data if opt-in is false; anonymize PII keys."""
        if not self.is_opt_in and record.privacy_classification != "Public":
            return None

        # Anonymize PII fields
        if record.privacy_classification == "PII":
            record.metadata = {"anonymized": True}
            record.metrics = {k: "ANONYMIZED" for k in record.metrics}

        return record


class TelemetryCollector:
    """Buffers records from multiple runtimes sources."""

    def __init__(self) -> None:
        self.buffer: list[TelemetryRecord] = []

    def collect(self, record: TelemetryRecord) -> None:
        """Append to local store buffer."""
        self.buffer.append(record)


class MetricsPipeline:
    """Aggregates metrics counts, errors, and calculating averages."""

    def __init__(self) -> None:
        self.total_requests = 0
        self.total_errors = 0
        self.availability = 100.0

    def aggregate(self, record: TelemetryRecord) -> None:
        """Update request and errors states."""
        self.total_requests += 1
        if record.severity == "ERROR":
            self.total_errors += 1

        if self.total_requests > 0:
            self.availability = (
                (self.total_requests - self.total_errors) / self.total_requests
            ) * 100.0


class HealthAnalyzer:
    """Calculates general health index scores."""

    def compute_health_index(self, pipeline: MetricsPipeline) -> float:
        """Formulate float index value."""
        return pipeline.availability


class DashboardGenerator:
    """Generates summarized dashboard markdown reports."""

    def generate_report(
        self, health_index: float, pipeline: MetricsPipeline, collector: TelemetryCollector
    ) -> str:
        """Format report stubs."""
        return (
            "# AIRA Operational Dashboard Compliance Report\n\n"
            f"* **Platform Health Score:** {health_index:.1f}%\n"
            f"* **Total Logged Requests:** {pipeline.total_requests}\n"
            f"* **Errors Count:** {pipeline.total_errors}\n"
            f"* **Buffered Telemetry Count:** {len(collector.buffer)}\n"
        )


class TelemetryManager:
    """Coordinating manager verifying constraints, indexing logs, and running analysis pipelines."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.privacy_manager = PrivacyManager()
        self.collector = TelemetryCollector()
        self.pipeline = MetricsPipeline()
        self.health_analyzer = HealthAnalyzer()
        self.dashboard_generator = DashboardGenerator()

    def set_privacy_consent(self, is_opt_in: bool) -> None:
        """Toggle privacy opt-in consent flag settings."""
        self.privacy_manager.is_opt_in = is_opt_in
        self.event_bus.publish_sync(
            Event(
                name="privacy_policy_applied",
                category="Telemetry",
                source="TelemetryManager",
                payload={"is_opt_in": is_opt_in},
            )
        )

    def submit_telemetry(self, record: TelemetryRecord) -> None:
        """Verify privacy restrictions, submit logs to collector, run pipeline, and notify bus."""
        processed = self.privacy_manager.process_record(record)
        if not processed:
            return

        self.collector.collect(processed)
        self.pipeline.aggregate(processed)

        self.event_bus.publish_sync(
            Event(
                name="telemetry.collected",
                category="Telemetry",
                source="TelemetryManager",
                payload={"component": record.component, "event_type": record.event_type},
            )
        )

        self.event_bus.publish_sync(
            Event(
                name="metrics.updated",
                category="Telemetry",
                source="TelemetryManager",
                payload={"availability": self.pipeline.availability},
            )
        )

        # Check and update health
        health = self.health_analyzer.compute_health_index(self.pipeline)
        self.event_bus.publish_sync(
            Event(
                name="health.updated",
                category="Telemetry",
                source="TelemetryManager",
                payload={"health_score": health},
            )
        )

    def generate_operations_dashboard(self) -> str:
        """Generate markdown operations report and notify events."""
        health = self.health_analyzer.compute_health_index(self.pipeline)
        report = self.dashboard_generator.generate_report(health, self.pipeline, self.collector)

        self.event_bus.publish_sync(
            Event(
                name="dashboard.updated",
                category="Telemetry",
                source="TelemetryManager",
                payload={"records_count": len(self.collector.buffer)},
            )
        )
        return report
