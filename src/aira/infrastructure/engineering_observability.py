"""Enterprise Engineering Evaluation, Observability & Productivity Analytics.

Aggregates execution telemetry, benchmarks model capabilities, and dashboards.
"""

import time
from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.engineering_observability")


class EngineeringObservabilityError(Exception):
    """Raised when telemetry collection, capability benchmarks, or dashboard aggregates fail."""

    pass


@dataclass
class TelemetryRecord:
    """Dataclass capturing telemetry metric nodes metadata."""

    record_id: str
    source_module: str
    operation: str
    duration_ms: float
    exit_code: int = 0
    timestamp: float = field(default_factory=time.time)


@dataclass
class CapabilityBenchmark:
    """Dataclass encapsulating capability evaluation benchmarks scores."""

    capability_id: str
    accuracy: float  # 0.0 to 1.0
    latency_ms: float
    reliability: float  # 0.0 to 1.0
    coverage: float  # 0.0 to 1.0


class TelemetryCollector:
    """Collects operation records logs from application executors."""

    def __init__(self) -> None:
        self.records: list[TelemetryRecord] = []

    def record_operation(self, record: TelemetryRecord) -> None:
        """Register telemetry node in collection cache."""
        if not record.record_id or not record.source_module:
            raise EngineeringObservabilityError("Record ID and source module are required.")
        self.records.append(record)


class MetricsEngine:
    """Processes telemetry collection to calculate success/failure statistics."""

    def calculate_metrics(self, records: list[TelemetryRecord]) -> dict[str, Any]:
        """Aggregate latencies and rates percentages."""
        if not records:
            return {
                "success_rate": 100.0,
                "failure_rate": 0.0,
                "avg_latency_ms": 0.0,
                "records_count": 0,
            }

        successes = sum(1 for r in records if r.exit_code == 0)
        total = len(records)
        success_rate = (successes / total) * 100.0
        avg_latency = sum(r.duration_ms for r in records) / total

        return {
            "success_rate": success_rate,
            "failure_rate": 100.0 - success_rate,
            "avg_latency_ms": avg_latency,
            "records_count": total,
        }


class EvaluationEngine:
    """Measures recommendation acceptance scores and capability benchmark alignments."""

    def __init__(self) -> None:
        # Map of recommendation_id -> status (Accepted, Ignored, Successful, Failed)
        self.recommendations: dict[str, str] = {}
        self.benchmarks: dict[str, CapabilityBenchmark] = {}

    def track_recommendation(self, rec_id: str, status: str) -> None:
        """Register recommendation status."""
        self.recommendations[rec_id] = status

    def benchmark_capability(self, benchmark: CapabilityBenchmark) -> None:
        """Link capability benchmark results."""
        self.benchmarks[benchmark.capability_id] = benchmark

    def get_effectiveness_ratio(self) -> float:
        """Evaluate recommendation accepted success rates."""
        if not self.recommendations:
            return 100.0

        successes = sum(1 for status in self.recommendations.values() if status == "Successful")
        total = len(self.recommendations)
        return (successes / total) * 100.0


class EngineeringDashboard:
    """Renders high-level developer productivity statistics and metrics logs summary."""

    def render_dashboard(
        self, metrics: dict[str, Any], effectiveness: float, benchmarks: list[CapabilityBenchmark]
    ) -> dict[str, Any]:
        """Compile aggregates engineering dashboard report."""
        overall_health = 100.0
        success_weight = metrics.get("success_rate", 100.0)

        # Base health calculated as success_rate + recommendations effectiveness averages
        overall_health = (success_weight * 0.6) + (effectiveness * 0.4)

        return {
            "overall_engineering_health": max(0.0, overall_health),
            "success_rate": success_weight,
            "avg_latency_ms": metrics.get("avg_latency_ms", 0.0),
            "effectiveness_ratio": effectiveness,
            "benchmarks_count": len(benchmarks),
        }


class EngineeringObservabilityManager:
    """Primary manager orchestrating telemetry dashboards, metrics, and reports."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.collector = TelemetryCollector()
        self.metrics_engine = MetricsEngine()
        self.evaluator = EvaluationEngine()
        self.dashboard = EngineeringDashboard()

    def collect_telemetry(self, record: TelemetryRecord) -> None:
        """Cache record telemetry and notify Event Bus."""
        self.collector.record_operation(record)

        self.event_bus.publish_sync(
            Event(
                name="telemetry.collected",
                category="Observability",
                source="EngineeringObservabilityManager",
                payload={"record_id": record.record_id, "operation": record.operation},
            )
        )

    def evaluate_recommendation(self, rec_id: str, status: str) -> None:
        """Track user updates status on recommendations and publish results."""
        self.evaluator.track_recommendation(rec_id, status)

        self.event_bus.publish_sync(
            Event(
                name="evaluation.completed",
                category="Observability",
                source="EngineeringObservabilityManager",
                payload={"rec_id": rec_id, "status": status},
            )
        )

    def run_benchmark(self, benchmark: CapabilityBenchmark) -> None:
        """Register benchmarks updates score stats."""
        self.evaluator.benchmark_capability(benchmark)

        self.event_bus.publish_sync(
            Event(
                name="capability.benchmarked",
                category="Observability",
                source="EngineeringObservabilityManager",
                payload={"capability_id": benchmark.capability_id, "accuracy": benchmark.accuracy},
            )
        )

    def compile_dashboard_report(self) -> dict[str, Any]:
        """Aggregate telemetry statistics and effectiveness ratios to generate full report."""
        records = self.collector.records
        metrics = self.metrics_engine.calculate_metrics(records)
        effectiveness = self.evaluator.get_effectiveness_ratio()
        benchmarks_list = list(self.evaluator.benchmarks.values())

        self.event_bus.publish_sync(
            Event(
                name="metrics.updated",
                category="Observability",
                source="EngineeringObservabilityManager",
                payload={"success_rate": metrics["success_rate"]},
            )
        )

        report = self.dashboard.render_dashboard(metrics, effectiveness, benchmarks_list)

        self.event_bus.publish_sync(
            Event(
                name="dashboard.updated",
                category="Observability",
                source="EngineeringObservabilityManager",
                payload={"overall_health": report["overall_engineering_health"]},
            )
        )

        self.event_bus.publish_sync(
            Event(
                name="report.generated",
                category="Observability",
                source="EngineeringObservabilityManager",
                payload={"benchmarks_count": report["benchmarks_count"]},
            )
        )

        return report
