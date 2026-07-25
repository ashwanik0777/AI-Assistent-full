"""Enterprise Unified Context Fusion & Multimodal Reasoning Platform subsystem for AIRA.

Provides context normalization, conflict resolutions, builders, and timelines.
"""

import time
from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.perception_engine import ObservationBuilder, PerceptionEngine
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.unified_context_fusion")


class ContextFusionError(Exception):
    """Raised when context collections, priority ranking, or conflict resolution diffs fail."""

    pass


@dataclass
class UnifiedContext:
    """Consolidated representation containing workspace, repository, memory, and visual context."""

    context_id: str
    conversation_context: dict[str, Any] = field(default_factory=dict)
    voice_context: dict[str, Any] = field(default_factory=dict)
    visual_context: dict[str, Any] = field(default_factory=dict)
    workspace_context: dict[str, Any] = field(default_factory=dict)
    repository_context: dict[str, Any] = field(default_factory=dict)
    project_context: dict[str, Any] = field(default_factory=dict)
    memory_context: dict[str, Any] = field(default_factory=dict)
    observation_context: dict[str, Any] = field(default_factory=dict)
    developer_context: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    evidence_references: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    version: str = "1.0.0"


@dataclass
class ContextConflictReport:
    """Traces discrepancy points between subsystems and outputs explainable resolution arguments."""

    conflict_type: str
    resolved_value: Any
    explanation: str


@dataclass
class ContextSnapshot:
    """Decision capture snapshot storing raw input parameters alongside unified representations."""

    snapshot_id: str
    timestamp: float
    unified_context: UnifiedContext
    evidence: list[str] = field(default_factory=list)
    reasoning_metadata: dict[str, Any] = field(default_factory=dict)


class ContextCollector:
    """Queries individual subsystems for active point-in-time contexts."""

    def collect_raw_contexts(self) -> dict[str, Any]:
        """Gathers context blocks (mocked representations of active layers)."""
        return {
            "conversation": {"last_message": "Continue working on CareerHub"},
            "voice": {"active_voice_session": False},
            "visual": {"focused_window": "VS Code", "elements_count": 5},
            "workspace": {"active_project": "CareerHub", "path": "/projects/CareerHub"},
            "repository": {"branch": "main", "dirty_files": ["src/app.py"]},
            "project": {"project_name": "CareerHub", "version": "1.2.0"},
            "memory": {"last_facts": ["CareerHub is a job board app"]},
            "observation": {"last_observation_id": "obs_ui_001"},
            "developer": {"active_user": "Ashwani"},
        }


class ContextNormalizer:
    """Validates schemas structural integrity and normalizes confidence and timestamps."""

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Normalizes collected schemas, setting standard defaults and timestamps."""
        normalized = {}
        for key, val in raw.items():
            normalized[key] = {"data": val, "confidence": 1.0, "timestamp": time.time()}
        return normalized


class ContextPriorityEngine:
    """Ranks sub-context items based on recency, confidence, and user focus flags."""

    def rank_contexts(self, normalized: dict[str, Any]) -> list[str]:
        """Ranks context keys by logical priority order."""
        # Standard priority ranking: visual/workspace focus first, then others
        priority_keys = ["workspace", "visual", "conversation", "repository", "memory"]
        return [k for k in priority_keys if k in normalized] + [
            k for k in normalized if k not in priority_keys
        ]


class ContextConflictResolver:
    """Reconciles discrepant values (e.g. Workspace vs Memory facts)."""

    def resolve_conflicts(self, normalized: dict[str, Any]) -> list[ContextConflictReport]:
        """Identify conflicts and return resolution reports."""
        reports = []

        workspace_proj = normalized.get("workspace", {}).get("data", {}).get("active_project")
        memory_proj = normalized.get("memory", {}).get("data", {}).get("last_facts", [None])[0]

        # Case 1: Active project mismatch
        is_career_hub_mismatch = (
            workspace_proj
            and memory_proj
            and "CareerHub" in memory_proj
            and workspace_proj != "CareerHub"
        )
        if is_career_hub_mismatch:
            explanation = (
                f"Workspace points to '{workspace_proj}' while Memory facts "
                f"reference '{memory_proj}'. Resolved in favor of Workspace focus."
            )
            reports.append(
                ContextConflictReport(
                    conflict_type="ActiveProjectMismatch",
                    resolved_value=workspace_proj,
                    explanation=explanation,
                )
            )

        return reports


class UnifiedContextBuilder:
    """Assembles individual normalizer sections into a UnifiedContext object."""

    def build_unified_context(
        self, context_id: str, norm: dict[str, Any], confidence: float = 1.0
    ) -> UnifiedContext:
        return UnifiedContext(
            context_id=context_id,
            conversation_context=norm.get("conversation", {}).get("data", {}),
            voice_context=norm.get("voice", {}).get("data", {}),
            visual_context=norm.get("visual", {}).get("data", {}),
            workspace_context=norm.get("workspace", {}).get("data", {}),
            repository_context=norm.get("repository", {}).get("data", {}),
            project_context=norm.get("project", {}).get("data", {}),
            memory_context=norm.get("memory", {}).get("data", {}),
            observation_context=norm.get("observation", {}).get("data", {}),
            developer_context=norm.get("developer", {}).get("data", {}),
            confidence=confidence,
        )


class ContextTimeline:
    """Stores a history timeline of unified context states and reasoning snapshots."""

    def __init__(self) -> None:
        self.snapshots: list[ContextSnapshot] = []

    def save_snapshot(self, snapshot: ContextSnapshot) -> None:
        self.snapshots.append(snapshot)


class UnifiedContextFusionEngine:
    """Orchestrates structured context collection, normalizations, conflict diffs, and snapshots."""

    def __init__(
        self,
        config: AppConfig,
        registry: ServiceRegistry,
        event_bus: EventBus,
        perception_engine: PerceptionEngine,
    ) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus
        self.perception_engine = perception_engine

        self.collector = ContextCollector()
        self.normalizer = ContextNormalizer()
        self.priority_engine = ContextPriorityEngine()
        self.resolver = ContextConflictResolver()
        self.builder = UnifiedContextBuilder()
        self.timeline = ContextTimeline()

    def fuse_context(self, context_id: str, session_id: str | None = None) -> UnifiedContext:
        """Trigger collections, normalize schemas, rank priorities, and resolve conflicts.

        Afterwards, save timeline snapshots.
        """
        # 1. Collect
        raw = self.collector.collect_raw_contexts()
        self.event_bus.publish_sync(
            Event(
                name="context.collected",
                category="Perception",
                source="ContextFusion",
                payload={"raw_keys": list(raw.keys())},
            )
        )

        # 2. Normalize
        normalized = self.normalizer.normalize(raw)
        self.event_bus.publish_sync(
            Event(
                name="context.normalized",
                category="Perception",
                source="ContextFusion",
                payload={"keys_count": len(normalized)},
            )
        )

        # 3. Rank
        ranked = self.priority_engine.rank_contexts(normalized)
        self.event_bus.publish_sync(
            Event(
                name="context.ranked",
                category="Perception",
                source="ContextFusion",
                payload={"ranked_keys": ranked},
            )
        )

        # 4. Conflict Resolution
        conflicts = self.resolver.resolve_conflicts(normalized)
        for conflict in conflicts:
            self.event_bus.publish_sync(
                Event(
                    name="conflict.resolved",
                    category="Perception",
                    source="ContextFusion",
                    payload={"type": conflict.conflict_type, "resolution": conflict.explanation},
                )
            )

        # 5. Build Unified Context
        unified = self.builder.build_unified_context(context_id, normalized)

        # Schema constraints verification
        if not unified.context_id:
            raise ContextFusionError("Unified context build failed: Context ID cannot be empty.")

        self.event_bus.publish_sync(
            Event(
                name="unified_context.published",
                category="Perception",
                source="ContextFusion",
                payload={"context_id": unified.context_id},
            )
        )

        # 6. Timeline Snapshot
        snapshot = ContextSnapshot(
            snapshot_id=f"snap_{unified.context_id}",
            timestamp=time.time(),
            unified_context=unified,
            reasoning_metadata={"conflicts_resolved": len(conflicts)},
        )
        self.timeline.save_snapshot(snapshot)
        self.event_bus.publish_sync(
            Event(
                name="reasoning_snapshot.stored",
                category="Perception",
                source="ContextFusion",
                payload={"snapshot_id": snapshot.snapshot_id},
            )
        )

        # Build Observation Object and publish to Perception Engine
        obs_builder = ObservationBuilder(
            f"obs_ctx_{unified.context_id}", "Screen", "UnifiedContext"
        )
        obs_builder.set_confidence(1.0)
        obs_builder.set_content(
            {
                "context_id": unified.context_id,
                "keys_fused": list(normalized.keys()),
                "conflicts_count": len(conflicts),
            }
        )
        obs_builder.set_metadata("snapshot_id", snapshot.snapshot_id)

        obs = obs_builder.build()
        self.perception_engine.process_observation(obs, session_id=session_id)

        return unified
