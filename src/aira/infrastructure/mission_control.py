"""Enterprise Global Mission Control, Observability & Operations Center Platform for AIRA.

Provides telemetry collectors, dashboards, coordinators, and operational evidence managers.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.mission_control")


class MissionControlError(Exception):
    """Exception raised for telemetry drifts, correlation drifts, or evidence errors."""

    pass


@dataclass
class GlobalOperationsSnapshot:
    """Operations snapshot mapping regional health status, capacity indices, and active alerts."""

    snapshot_id: str
    timestamp: str
    regions: list[str] = field(default_factory=list)
    runtime_health: dict[str, str] = field(default_factory=dict)
    active_missions: list[str] = field(default_factory=list)
    alerts: list[dict[str, Any]] = field(default_factory=list)
    capacity: dict[str, float] = field(default_factory=dict)
    trust_status: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    version: str = "1.0.0"


class GlobalTelemetryCollector:
    """Aggregates and filters raw regional performance health details."""

    def __init__(self) -> None:
        self.collected_metrics: list[dict[str, Any]] = []

    def collect_metric(self, region: str, metric_key: str, value: float) -> None:
        """Store collected metric values."""
        if value < 0:
            raise MissionControlError(
                f"Validation failed: Metric '{metric_key}' has negative value {value}."
            )
        self.collected_metrics.append(
            {
                "region": region,
                "metric": metric_key,
                "value": value,
                "time": datetime.utcnow().isoformat(),
            }
        )


class ObservabilityPlatform:
    """Correlates logs, metrics, and traces across federated runtimes."""

    def __init__(self) -> None:
        self.correlated_incidents: list[dict[str, Any]] = []

    def correlate_alerts(self, alerts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Group related alerts into correlated incidents."""
        if not alerts:
            return []

        # Simple grouping by target key category prefix
        groups: dict[str, list[dict[str, Any]]] = {}
        for alert in alerts:
            cat = alert.get("category", "General")
            groups.setdefault(cat, []).append(alert)

        incidents = []
        for cat, list_al in groups.items():
            if len(list_al) > 1:
                incidents.append(
                    {
                        "incident_id": f"inc_{cat.lower()}",
                        "category": cat,
                        "correlated_alerts": list_al,
                        "severity": "High",
                    }
                )
        return incidents


class MissionControlDashboard:
    """Presents a query interface for unified snapshot awareness."""

    def __init__(self) -> None:
        self.snapshots: dict[str, GlobalOperationsSnapshot] = {}

    def save_snapshot(self, snapshot: GlobalOperationsSnapshot) -> None:
        """Register snapshot in dashboard logs."""
        self.snapshots[snapshot.snapshot_id] = snapshot


class OperationsCoordinator:
    """Coordinates incident workflows suggesting operational playbooks."""

    def suggest_playbook(self, category: str) -> str:
        """Suggest matching recovery guidelines."""
        if category == "Capacity":
            return "Playbook-Scale-Nodes"
        if category == "Network":
            return "Playbook-Reroute-Traffic"
        return "Playbook-Standard-Diagnostics"


class OperationsEvidenceManager:
    """Archives evidence history trails and tracks operational actions."""

    def __init__(self) -> None:
        self.archives: list[dict[str, Any]] = []

    def archive_action(self, snapshot_id: str, action: str, result: str) -> None:
        """Append operational event detail to archive list."""
        self.archives.append(
            {
                "snapshot_id": snapshot_id,
                "action": action,
                "result": result,
                "archived_at": datetime.utcnow().isoformat(),
            }
        )


class MissionControlPlatform:
    """Coordinating manager resolving collectors, dashboards, and correlation playbooks."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.collector = GlobalTelemetryCollector()
        self.observability = ObservabilityPlatform()
        self.dashboard = MissionControlDashboard()
        self.coordinator = OperationsCoordinator()
        self.evidence_manager = OperationsEvidenceManager()

    def generate_operations_snapshot(
        self,
        snapshot_id: str,
        regions: list[str],
        runtime_health: dict[str, str],
        active_missions: list[str],
        alerts: list[dict[str, Any]],
        capacity: dict[str, float],
    ) -> GlobalOperationsSnapshot:
        """Assemble snapshot, register with dashboard, and publish events."""
        if not snapshot_id or not regions:
            raise MissionControlError("Generation failed: Snapshots require ID and regional tags.")

        snap = GlobalOperationsSnapshot(
            snapshot_id=snapshot_id,
            timestamp=datetime.utcnow().isoformat(),
            regions=regions,
            runtime_health=runtime_health,
            active_missions=active_missions,
            alerts=alerts,
            capacity=capacity,
        )

        self.dashboard.save_snapshot(snap)

        self.event_bus.publish_sync(
            Event(
                name="obs.snapshot.created",
                category="MissionControl",
                source="MissionControlPlatform",
                payload={"snapshot_id": snapshot_id},
            )
        )

        return snap

    def process_telemetry_event(self, region: str, metric_key: str, value: float) -> None:
        """Collect metrics and trigger alerts if thresholds are exceeded."""
        self.collector.collect_metric(region, metric_key, value)

        # Basic alert threshold validation
        if value > 90.0 or value < 0.1:
            self.event_bus.publish_sync(
                Event(
                    name="obs.alert.generated",
                    category="MissionControl",
                    source="MissionControlPlatform",
                    payload={"region": region, "metric": metric_key, "value": value},
                )
            )

    def evaluate_correlated_incidents(
        self, snapshot_id: str, alerts: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Correlate related alerts and record incidents."""
        incidents = self.observability.correlate_alerts(alerts)

        for inc in incidents:
            self.event_bus.publish_sync(
                Event(
                    name="obs.incident.recorded",
                    category="MissionControl",
                    source="MissionControlPlatform",
                    payload={"incident_id": inc["incident_id"], "category": inc["category"]},
                )
            )

        return incidents

    def publish_operations_report(self, snapshot_id: str, reporter: str) -> None:
        """Publish report logs and update dashboards details."""
        snap = self.dashboard.snapshots.get(snapshot_id)
        if not snap:
            raise MissionControlError(f"Snapshot not found: '{snapshot_id}'")

        self.event_bus.publish_sync(
            Event(
                name="obs.report.published",
                category="MissionControl",
                source="MissionControlPlatform",
                payload={"snapshot_id": snapshot_id, "reporter": reporter},
            )
        )


class MissionControlManager:
    """Legacy manager class mapping configuration, registry, and event bus."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus
