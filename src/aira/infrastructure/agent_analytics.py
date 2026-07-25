"""Enterprise Agent Analytics & Observability for AIRA.

Provides telemetry collection, calculators, quality indicators, and dashboard generators.
"""

import time
from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.agent_analytics")


class AgentAnalyticsError(Exception):
    """Raised when analytics aggregates calculation, validations, or reporting fails."""

    pass


@dataclass
class AgentMetric:
    """Core telemetry stats evaluating agent performance and latency rates."""

    execution_count: int = 0
    success_rate: float = 0.0
    failure_rate: float = 0.0
    average_latency: float = 0.0
    policy_compliance: float = 100.0


@dataclass
class CollaborationMetric:
    """Telemetry tracking dynamic coordination efficiencies and sync delay metrics."""

    team_formation_time: float = 0.0
    conflict_frequency: int = 0
    resolution_time: float = 0.0
    approval_delay: float = 0.0


@dataclass
class CapabilityMetric:
    """Telemetry tracking platform capabilities selection parameters."""

    selection_frequency: int = 0
    failure_rate: float = 0.0
    average_latency: float = 0.0


@dataclass
class GovernanceMetric:
    """Compliance audit telemetries reporting block rates and policy violation counts."""

    approval_requests: int = 0
    denials: int = 0
    policy_violations: int = 0
    risk_distribution: dict[str, int] = field(default_factory=dict)


class AnalyticsCollector:
    """Central repository storing raw telemetry logs."""

    def __init__(self) -> None:
        self.events_log: list[Event] = []

    def record_event(self, event: Event) -> None:
        """Append runtime notifications log entry."""
        self.events_log.append(event)


class PerformanceEngine:
    """Computes latencies, failure rates, and success rates."""

    def calculate_agent_metrics(self, collector: AnalyticsCollector, agent_id: str) -> AgentMetric:
        """Scan collected logs to compute counts and ratios."""
        starts = {}
        latencies = []
        successes = 0
        failures = 0

        for event in collector.events_log:
            payload = event.payload or {}
            if payload.get("agent_id") != agent_id:
                continue
            if event.name == "agent.started":
                starts[payload.get("task_id")] = event.timestamp
            elif event.name in ("agent.completed", "agent.failed"):
                task_id = payload.get("task_id")
                start_t = starts.get(task_id)
                if start_t:
                    latencies.append((event.timestamp - start_t).total_seconds())
                if event.name == "agent.completed":
                    successes += 1
                else:
                    failures += 1

        total = successes + failures
        success_rate = (successes / total * 100.0) if total > 0 else 100.0
        failure_rate = (failures / total * 100.0) if total > 0 else 0.0
        avg_latency = (sum(latencies) / len(latencies)) if latencies else 0.0

        return AgentMetric(
            execution_count=total,
            success_rate=success_rate,
            failure_rate=failure_rate,
            average_latency=avg_latency,
        )


class QualityAnalyzer:
    """Analyzes error frequencies and validates accuracy compliance scores."""

    def analyze_quality(self, metrics: AgentMetric) -> float:
        """Compute basic compliance score out of 100 based on failure ratios."""
        return max(0.0, 100.0 - metrics.failure_rate)


class CollaborationAnalyzer:
    """Measures dynamic team coordination and conflicts resolution latency logs."""

    def analyze_collaboration(self, collector: AnalyticsCollector) -> CollaborationMetric:
        """Query task blockers frequency rates."""
        conflicts = 0
        resolutions = []

        detects = {}
        for event in collector.events_log:
            payload = event.payload or {}
            if event.name == "conflict.detected":
                conflicts += 1
                detects[payload.get("conflict_id")] = event.timestamp
            elif event.name == "conflict.resolved":
                conf_id = payload.get("conflict_id")
                det_t = detects.get(conf_id)
                if det_t:
                    resolutions.append((event.timestamp - det_t).total_seconds())

        avg_res = (sum(resolutions) / len(resolutions)) if resolutions else 0.0
        return CollaborationMetric(conflict_frequency=conflicts, resolution_time=avg_res)


class GovernanceAnalyzer:
    """Monitors policy violations, count block rates, and tracks risk allocations."""

    def analyze_governance(self, collector: AnalyticsCollector) -> GovernanceMetric:
        """Query policy evaluations logs."""
        reqs = 0
        denials = 0
        violations = 0
        risk_dist = {"Low": 0, "Medium": 0, "High": 0}

        for event in collector.events_log:
            payload = event.payload or {}
            if event.name == "approval.requested":
                reqs += 1
            elif event.name == "execution.denied":
                denials += 1
            elif event.name == "risk.evaluated":
                score = payload.get("score", 0.0)
                if score >= 8.0:
                    risk_dist["High"] += 1
                elif score >= 5.0:
                    risk_dist["Medium"] += 1
                else:
                    risk_dist["Low"] += 1

        return GovernanceMetric(
            approval_requests=reqs,
            denials=denials,
            policy_violations=violations,
            risk_distribution=risk_dist,
        )


class CapabilityAnalytics:
    """Tracks capability usage and failure rates."""

    def analyze_capabilities(self, collector: AnalyticsCollector) -> dict[str, CapabilityMetric]:
        """Aggregate capability selection logs."""
        usages: dict[str, int] = {}
        for event in collector.events_log:
            payload = event.payload or {}
            if event.name == "capability.selected":
                cap = payload.get("capability", "unknown")
                usages[cap] = usages.get(cap, 0) + 1

        metrics = {}
        for cap, count in usages.items():
            metrics[cap] = CapabilityMetric(selection_frequency=count)
        return metrics


class DashboardGenerator:
    """Consolidates metrics values into structured dashboard layout reports."""

    def generate_report(
        self,
        agent_metrics: dict[str, AgentMetric],
        collab: CollaborationMetric,
        gov: GovernanceMetric,
    ) -> dict[str, Any]:
        """Synthesize final audit telemetry metrics reports."""
        return {
            "timestamp": time.time(),
            "status": "Healthy",
            "agents_count": len(agent_metrics),
            "total_execution_count": sum(m.execution_count for m in agent_metrics.values()),
            "conflict_frequency": collab.conflict_frequency,
            "governance_approval_requests": gov.approval_requests,
            "governance_denials": gov.denials,
        }


class AnalyticsOrchestrator:
    """Core platform coordinator wire collectors event notifications and updates metrics records."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.collector = AnalyticsCollector()
        self.performance_engine = PerformanceEngine()
        self.quality_analyzer = QualityAnalyzer()
        self.collab_analyzer = CollaborationAnalyzer()
        self.gov_analyzer = GovernanceAnalyzer()
        self.cap_analytics = CapabilityAnalytics()
        self.dashboard_generator = DashboardGenerator()

    def process_event(self, event: Event) -> None:
        """Ingest event telemetry logic."""
        self.collector.record_event(event)

    def generate_analytics_dashboard(self, active_agents: list[str]) -> dict[str, Any]:
        """Compile and evaluate dashboard, publishing events."""
        # 1. Performance
        agent_mets = {}
        for aid in active_agents:
            agent_mets[aid] = self.performance_engine.calculate_agent_metrics(self.collector, aid)
            self.event_bus.publish_sync(
                Event(
                    name="performance.measured",
                    category="Analytics",
                    source="AnalyticsOrchestrator",
                    payload={"agent_id": aid},
                )
            )

        # 2. Collaboration
        collab = self.collab_analyzer.analyze_collaboration(self.collector)

        # 3. Governance
        gov = self.gov_analyzer.analyze_governance(self.collector)
        self.event_bus.publish_sync(
            Event(
                name="governance.measured",
                category="Analytics",
                source="AnalyticsOrchestrator",
                payload={"denials": gov.denials},
            )
        )

        # 4. Capabilities
        self.cap_analytics.analyze_capabilities(self.collector)
        self.event_bus.publish_sync(
            Event(
                name="capability.measured",
                category="Analytics",
                source="AnalyticsOrchestrator",
                payload={},
            )
        )

        # 5. Dashboard Compile
        report = self.dashboard_generator.generate_report(agent_mets, collab, gov)
        self.event_bus.publish_sync(
            Event(
                name="dashboard.updated",
                category="Analytics",
                source="AnalyticsOrchestrator",
                payload={"status": report["status"]},
            )
        )

        self.event_bus.publish_sync(
            Event(
                name="analytics.updated",
                category="Analytics",
                source="AnalyticsOrchestrator",
                payload={},
            )
        )

        return report
