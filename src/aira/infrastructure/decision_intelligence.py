"""Enterprise Evaluation, Experimentation & Decision Intelligence Platform for AIRA.

Provides experiment designers, offline replayers, benchmark engines, and regression detectors.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.decision_intelligence")


class DecisionIntelligenceError(Exception):
    """Base exception raised for benchmark failures, regressions blocks, or decision violations."""

    pass


@dataclass
class ExperimentRecord:
    """Record encapsulating hypotheses parameters, baseline configurations, and success metrics."""

    experiment_id: str
    hypothesis: str
    baseline_version: str
    candidate_version: str
    evaluation_dataset: list[str]
    success_metrics: dict[str, float] = field(default_factory=dict)
    failure_metrics: dict[str, float] = field(default_factory=dict)
    confidence_level: float = 0.95
    decision: str = "Needs Review"  # Adopt, Reject, Needs Review, Needs More Evidence, Archived
    version: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)


class ExperimentDesigner:
    """Designs and catalogs controlled offline experiments parameters."""

    def design_experiment(
        self, experiment_id: str, hypothesis: str, baseline: str, candidate: str, dataset: list[str]
    ) -> ExperimentRecord:
        """Create new ExperimentRecord."""
        if not experiment_id or not hypothesis:
            raise DecisionIntelligenceError(
                "Design failed: Experiment ID and hypothesis are required."
            )
        return ExperimentRecord(
            experiment_id=experiment_id,
            hypothesis=hypothesis,
            baseline_version=baseline,
            candidate_version=candidate,
            evaluation_dataset=dataset,
        )


class OfflineEvaluationEngine:
    """Replays historical execution data to gather baseline/candidate performance."""

    def replay_dataset(self, dataset: list[str]) -> float:
        """Simulate replaying datasets and return simulated processing latency duration."""
        # Baseline simulation helper returning total records duration sum
        return len(dataset) * 120.0


class BenchmarkEngine:
    """Computes comparison indexes across latency, success, and resource metrics."""

    def compute_benchmarks(self, baseline_time: float, candidate_time: float) -> dict[str, float]:
        """Compute latency metrics comparison dictionary."""
        diff_time = baseline_time - candidate_time
        reduction = (diff_time / baseline_time) * 100.0 if baseline_time > 0 else 0.0
        return {
            "baseline_latency_ms": baseline_time,
            "candidate_latency_ms": candidate_time,
            "latency_reduction_percentage": reduction,
        }


class RegressionDetector:
    """Compares baseline vs candidate scores to catch performance regressions."""

    def detect_latency_regression(self, baseline_time: float, candidate_time: float) -> str | None:
        """Check if candidate duration exceeds baseline (regression trigger)."""
        if candidate_time > baseline_time:
            diff = candidate_time - baseline_time
            return f"Regression detected: Candidate latency increased by {diff}ms over baseline."
        return None


class DecisionEngine:
    """Manages experiment outcomes decision transitions workflows."""

    def transition_decision(self, record: ExperimentRecord, decision: str) -> None:
        """Change decision state and validate boundaries."""
        allowed = {"Adopt", "Reject", "Needs Review", "Needs More Evidence", "Archived"}
        if decision not in allowed:
            raise DecisionIntelligenceError(
                f"Transition failed: Decision state '{decision}' is not supported."
            )
        record.decision = decision


class DecisionIntelligenceManager:
    """Coordinating manager defining experiments, running benchmarks, and directing outcomes."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.designer = ExperimentDesigner()
        self.evaluation_engine = OfflineEvaluationEngine()
        self.benchmark_engine = BenchmarkEngine()
        self.regression_detector = RegressionDetector()
        self.decision_engine = DecisionEngine()

        self.experiments: dict[str, ExperimentRecord] = {}

    def run_controlled_experiment(
        self,
        experiment_id: str,
        hypothesis: str,
        baseline: str,
        candidate: str,
        dataset: list[str],
        simulated_candidate_time: float,
    ) -> ExperimentRecord:
        """Construct experiment record and check regressions."""
        # 1. Design
        record = self.designer.design_experiment(
            experiment_id, hypothesis, baseline, candidate, dataset
        )
        self.experiments[experiment_id] = record

        self.event_bus.publish_sync(
            Event(
                name="experiment.created",
                category="DecisionIntelligence",
                source="DecisionIntelligenceManager",
                payload={"experiment_id": experiment_id, "hypothesis": hypothesis},
            )
        )

        # 2. Replay baseline
        baseline_time = self.evaluation_engine.replay_dataset(dataset)

        # 3. Compute Benchmarks
        bench = self.benchmark_engine.compute_benchmarks(baseline_time, simulated_candidate_time)
        record.success_metrics = {"improvement_percentage": bench["latency_reduction_percentage"]}

        self.event_bus.publish_sync(
            Event(
                name="evaluation.completed",
                category="DecisionIntelligence",
                source="DecisionIntelligenceManager",
                payload={"experiment_id": experiment_id, "benchmarks": bench},
            )
        )

        # 4. Check Regressions
        regression = self.regression_detector.detect_latency_regression(
            baseline_time, simulated_candidate_time
        )
        if regression:
            record.failure_metrics = {"regression_alert": 1.0}
            self.event_bus.publish_sync(
                Event(
                    name="regression.detected",
                    category="DecisionIntelligence",
                    source="DecisionIntelligenceManager",
                    payload={"experiment_id": experiment_id, "warning": regression},
                )
            )

        return record

    def commit_decision(self, experiment_id: str, decision: str) -> None:
        """Validate and transition experiment decision state."""
        record = self.experiments.get(experiment_id)
        if not record:
            raise DecisionIntelligenceError(
                f"Operation failed: Experiment '{experiment_id}' not found."
            )

        # Enforce rule: cannot adopt if regression fails check
        if decision == "Adopt" and record.failure_metrics.get("regression_alert"):
            raise DecisionIntelligenceError(
                f"Commit decision rejected: Cannot Adopt experiment '{experiment_id}' "
                f"with active performance regression alerts."
            )

        self.decision_engine.transition_decision(record, decision)

        self.event_bus.publish_sync(
            Event(
                name="decision.published",
                category="DecisionIntelligence",
                source="DecisionIntelligenceManager",
                payload={"experiment_id": experiment_id, "decision": decision},
            )
        )

    def archive_experiment(self, experiment_id: str) -> None:
        """Transition experiment status state to Archived."""
        record = self.experiments.get(experiment_id)
        if not record:
            raise DecisionIntelligenceError(
                f"Operation failed: Experiment '{experiment_id}' not found."
            )

        self.decision_engine.transition_decision(record, "Archived")

        self.event_bus.publish_sync(
            Event(
                name="experiment.archived",
                category="DecisionIntelligence",
                source="DecisionIntelligenceManager",
                payload={"experiment_id": experiment_id},
            )
        )
