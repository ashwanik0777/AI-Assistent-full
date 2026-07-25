"""Enterprise Workflow Analytics, Optimization & Evaluation Framework for AIRA.

Provides workflow execution profiling, bottlenecks and variables optimization scanning,
benchmarking, and read-only replay engines.
"""

from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.workflow_analytics")


class WorkflowAnalyticsError(Exception):
    """Raised when profile parses, benchmarking calculations, or replay runs fail."""

    pass


class WorkflowProfiler:
    """Measures execution duration metrics, retry ratios, and checkpoints usage."""

    def profile_execution(self, execution_data: dict[str, Any]) -> dict[str, Any]:
        """Compile execution metrics profiles details."""
        steps_durations = execution_data.get("step_durations", {})
        total_duration = sum(steps_durations.values()) if steps_durations else 0.0

        return {
            "total_duration": total_duration,
            "step_durations": dict(steps_durations),
            "waiting_time": execution_data.get("waiting_time", 0.0),
            "idle_time": execution_data.get("idle_time", 0.0),
            "retry_count": execution_data.get("retry_count", 0),
            "recovery_count": execution_data.get("recovery_count", 0),
            "checkpoint_usage": execution_data.get("checkpoint_usage", 0),
            "success_rate": execution_data.get("success_rate", 1.0),
        }


class PerformanceAnalyzer:
    """Identifies critical paths and parallel execution efficiency ratios."""

    def analyze_efficiency(
        self, duration: float, step_count: int, worker_count: int
    ) -> dict[str, Any]:
        """Calculate processing efficiency and bottlenecks parameters."""
        parallel_ratio = 1.0 if worker_count > 1 else 0.0
        return {
            "parallel_efficiency": parallel_ratio,
            "critical_path_seconds": duration * 0.8,
            "avg_step_duration": (duration / step_count) if step_count > 0 else 0.0,
        }


class WorkflowOptimizer:
    """Identifies redundancies and compiles performance improvement recommendations."""

    def scan_optimizations(
        self, profile: dict[str, Any], variables_list: list[str], resolved_variables: list[str]
    ) -> list[dict[str, Any]]:
        """Scan states profiles and compiled variables sets to suggest improvements."""
        recommendations = []

        # Check for unused variables
        unused = [v for v in variables_list if v not in resolved_variables]
        if unused:
            recommendations.append(
                {
                    "category": "Variables",
                    "issue": "Unused variables detected",
                    "details": f"Variables {unused} are set but never resolved.",
                    "remedy": "Remove unused variables references from context setup.",
                }
            )

        # Check for long step duration
        step_durations = profile.get("step_durations", {})
        for step, dur in step_durations.items():
            if dur > 10.0:  # Threshold of 10 seconds
                recommendations.append(
                    {
                        "category": "Performance",
                        "issue": f"Long-running step '{step}'",
                        "details": f"Step '{step}' took {dur} seconds to complete.",
                        "remedy": "Optimize step configurations or run in parallel.",
                    }
                )

        # Check parallel opportunities
        if profile.get("total_duration", 0.0) > 15.0 and len(step_durations) > 2:
            recommendations.append(
                {
                    "category": "Parallelization",
                    "issue": "Sequential execution bottleneck",
                    "details": "Workflow duration is high and executes tasks sequentially.",
                    "remedy": "Identify independent tasks and execute them concurrently.",
                }
            )

        return recommendations


class WorkflowBenchmarkRunner:
    """Benchmarks runs and computes overall performance indices scores."""

    def run_benchmark(self, profile: dict[str, Any]) -> dict[str, Any]:
        """Compute performance index score based on execution parameters."""
        duration = profile.get("total_duration", 0.0)
        failure_rate = 1.0 - profile.get("success_rate", 1.0)

        # Baseline score calculation: starts at 100
        score = 100.0
        score -= duration * 0.5  # Deduct 0.5 points per second
        score -= failure_rate * 50.0  # Deduct 50 points per failure rate increment

        final_score = max(0.0, min(100.0, score))

        return {
            "performance_score": final_score,
            "rating": "EXCELLENT" if final_score >= 85 else "FAIR" if final_score >= 60 else "POOR",
        }


class WorkflowReplayEngine:
    """Reconstructs past session executions timeline traces."""

    def replay_timeline(self, event_logs: list[dict[str, Any]]) -> dict[str, Any]:
        """Reconstruct trace history from recorded events lists."""
        steps_history = []
        variables_trail = []

        for log in event_logs:
            event_name = log.get("name", "")
            payload = log.get("payload", {})

            if event_name == "workflow.step_started":
                steps_history.append(
                    {
                        "step_id": payload.get("step_id"),
                        "action": "START",
                        "timestamp": log.get("timestamp"),
                    }
                )
            elif event_name == "workflow.step_completed":
                steps_history.append(
                    {
                        "step_id": payload.get("step_id"),
                        "action": "COMPLETE",
                        "timestamp": log.get("timestamp"),
                    }
                )
            elif event_name == "workflow.variable_created":
                variables_trail.append(
                    {"name": payload.get("name"), "action": "CREATE", "scope": payload.get("scope")}
                )

        return {"replayed_steps": steps_history, "replayed_variables": variables_trail}


class WorkflowAnalyticsManager:
    """Unified entry coordinator for Workflow Analytics & Evaluation Framework."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.profiler = WorkflowProfiler()
        self.analyzer = PerformanceAnalyzer()
        self.optimizer = WorkflowOptimizer()
        self.benchmarker = WorkflowBenchmarkRunner()
        self.replay_engine = WorkflowReplayEngine()

    def profile_workflow_run(
        self,
        execution_data: dict[str, Any],
        variables_list: list[str],
        resolved_variables: list[str],
    ) -> dict[str, Any]:
        """Generate profile metrics and suggestions read-only."""
        profile = self.profiler.profile_execution(execution_data)
        efficiency = self.analyzer.analyze_efficiency(
            profile["total_duration"],
            len(profile["step_durations"]),
            execution_data.get("worker_count", 1),
        )
        recommendations = self.optimizer.scan_optimizations(
            profile, variables_list, resolved_variables
        )
        benchmark = self.benchmarker.run_benchmark(profile)

        # Trigger event bus updates
        self.event_bus.publish_sync(
            Event(
                name="analytics.workflow_profiled",
                category="Analytics",
                source="WorkflowAnalyticsManager",
                payload={"total_duration": profile["total_duration"]},
            )
        )

        self.event_bus.publish_sync(
            Event(
                name="analytics.benchmark_completed",
                category="Analytics",
                source="WorkflowAnalyticsManager",
                payload={"performance_score": benchmark["performance_score"]},
            )
        )

        if recommendations:
            self.event_bus.publish_sync(
                Event(
                    name="analytics.optimization_suggested",
                    category="Analytics",
                    source="WorkflowAnalyticsManager",
                    payload={"count": len(recommendations)},
                )
            )

        self.event_bus.publish_sync(
            Event(
                name="analytics.evaluation_completed",
                category="Analytics",
                source="WorkflowAnalyticsManager",
                payload={},
            )
        )

        return {
            "profile": profile,
            "efficiency": efficiency,
            "recommendations": recommendations,
            "benchmark": benchmark,
        }

    def generate_replay_trace(self, event_logs: list[dict[str, Any]]) -> dict[str, Any]:
        """Generate trace replay metadata logs."""
        trace = self.replay_engine.replay_timeline(event_logs)

        self.event_bus.publish_sync(
            Event(
                name="analytics.replay_generated",
                category="Analytics",
                source="WorkflowAnalyticsManager",
                payload={"steps_count": len(trace["replayed_steps"])},
            )
        )

        return trace
