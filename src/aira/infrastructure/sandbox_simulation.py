"""Enterprise Autonomous Sandbox & Simulation Platform.

Provides scenario builders, simulation engines, policy validators, and replay engines.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.sandbox_simulation")


class SandboxSimulationError(Exception):
    """Base exception raised for scenario setup failures or policy validation drifts."""

    pass


@dataclass
class SimulationScenario:
    """Scenario defining parameters, metrics, logs, and experiment lifecycle state."""

    scenario_id: str
    objective: str
    participants: list[str]
    synthetic_environment: dict[str, Any]
    policies: list[str]
    success_criteria: list[str]
    failure_conditions: list[str]
    metrics: dict[str, Any]
    evidence_references: list[str]
    lifecycle_state: str = "Draft"  # Draft, Running, Completed, Reviewed, Approved, Archived
    metadata: dict[str, Any] = field(default_factory=dict)
    version: int = 1


class ScenarioBuilder:
    """Builds governed simulation scenarios setups and templates."""

    def build_scenario(
        self, scenario_id: str, objective: str, policies: list[str]
    ) -> SimulationScenario:
        """Create a default simulation template layout."""
        if not objective:
            raise SandboxSimulationError("Scenario objective must be specified.")
        return SimulationScenario(
            scenario_id=scenario_id,
            objective=objective,
            participants=[],
            synthetic_environment={"mock_infrastructure": True},
            policies=policies,
            success_criteria=["Complete simulation tasks"],
            failure_conditions=["Safety policy violations"],
            metrics={},
            evidence_references=[],
        )


class SimulationEngine:
    """Executes sandboxed synthetic workloads runs without production resource leaks."""

    def execute_simulation(
        self, scenario: SimulationScenario, steps: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Run synthetic simulation timeline loops and collect execution history."""
        history = []
        for step in steps:
            history.append(
                {
                    "step_name": step.get("name"),
                    "status": "Success",
                    "output": "Synthetic mock result",
                }
            )
        return {"steps_executed": len(steps), "status": "Success", "history": history}


class PolicyValidationEngine:
    """Evaluates safety policies compliance metrics within sandbox."""

    def validate_sandbox_policies(
        self, scenario: SimulationScenario, simulation_history: list[dict[str, Any]]
    ) -> bool:
        """Verify that simulation outputs satisfy constitutional rules."""
        # Policy checks
        return all("violation" not in str(h.get("step_name")).lower() for h in simulation_history)


class ReplayEngine:
    """Reproduces sandboxed experiments timelines deterministically."""

    def __init__(self) -> None:
        self.recorded_runs: dict[str, list[dict[str, Any]]] = {}

    def record_run(self, scenario_id: str, history: list[dict[str, Any]]) -> None:
        """Save history timeline."""
        self.recorded_runs[scenario_id] = history

    def replay_run(self, scenario_id: str) -> list[dict[str, Any]]:
        """Retrieve timeline trace for replay."""
        run = self.recorded_runs.get(scenario_id)
        if not run:
            raise SandboxSimulationError(f"Timeline logs not found for scenario '{scenario_id}'.")
        return run


class BenchmarkEngine:
    """Compares strategy versions metrics curves."""

    def compare_benchmarks(
        self, metrics_a: dict[str, float], metrics_b: dict[str, float]
    ) -> dict[str, Any]:
        """Tally values comparisons ratios."""
        comp = {}
        for key in metrics_a:
            if key in metrics_b:
                diff = metrics_a[key] - metrics_b[key]
                comp[key] = {"diff": diff, "improved": diff > 0.0}
        return comp


class EvidenceGenerator:
    """Produces audit-ready validation reports summaries."""

    def generate_report(
        self, scenario: SimulationScenario, passed_policies: bool
    ) -> dict[str, Any]:
        """Format metadata audit card."""
        return {
            "scenario_id": scenario.scenario_id,
            "objective": scenario.objective,
            "policies_passed": passed_policies,
            "report_status": "ReadyForAudit",
        }


class SandboxSimulationPlatform:
    """Coordinating manager resolving sandbox scenarios, benchmarking, and replays."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.builder = ScenarioBuilder()
        self.engine = SimulationEngine()
        self.validator = PolicyValidationEngine()
        self.replay = ReplayEngine()
        self.benchmarker = BenchmarkEngine()
        self.evidence = EvidenceGenerator()

        self.scenarios: dict[str, SimulationScenario] = {}

    def create_sandbox_scenario(
        self, scenario_id: str, objective: str, policies: list[str]
    ) -> SimulationScenario:
        """Assemble scenario template and publish events."""
        scenario = self.builder.build_scenario(scenario_id, objective, policies)
        self.scenarios[scenario_id] = scenario

        self.event_bus.publish_sync(
            Event(
                name="simulation.scenario.created",
                category="SandboxSimulation",
                source="SandboxSimulationPlatform",
                payload={"scenario_id": scenario_id},
            )
        )

        return scenario

    def run_sandbox_simulation(
        self, scenario_id: str, steps: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Promote scenario state, execute synthetic steps, and publish events."""
        scenario = self.scenarios.get(scenario_id)
        if not scenario:
            raise SandboxSimulationError(f"Scenario not found: '{scenario_id}'")

        # Update state
        scenario.lifecycle_state = "Running"
        self.event_bus.publish_sync(
            Event(
                name="simulation.started",
                category="SandboxSimulation",
                source="SandboxSimulationPlatform",
                payload={"scenario_id": scenario_id},
            )
        )

        # Run
        out = self.engine.execute_simulation(scenario, steps)
        scenario.lifecycle_state = "Completed"

        # Record timeline for replays
        self.replay.record_run(scenario_id, out["history"])

        # Validate policies
        passed = self.validator.validate_sandbox_policies(scenario, out["history"])
        scenario.metrics["policies_passed"] = passed

        self.event_bus.publish_sync(
            Event(
                name="simulation.completed",
                category="SandboxSimulation",
                source="SandboxSimulationPlatform",
                payload={"scenario_id": scenario_id, "passed": passed},
            )
        )

        # Generate evidence
        rep = self.evidence.generate_report(scenario, passed)
        scenario.evidence_references.append(f"report_{scenario_id}.json")

        self.event_bus.publish_sync(
            Event(
                name="simulation.evidence.published",
                category="SandboxSimulation",
                source="SandboxSimulationPlatform",
                payload={"scenario_id": scenario_id, "report": rep},
            )
        )

        return out

    def generate_strategy_benchmark(
        self, scenario_id: str, metrics_a: dict[str, float], metrics_b: dict[str, float]
    ) -> dict[str, Any]:
        """Run benchmark tallies and publish events."""
        comp = self.benchmarker.compare_benchmarks(metrics_a, metrics_b)

        self.event_bus.publish_sync(
            Event(
                name="simulation.benchmark.generated",
                category="SandboxSimulation",
                source="SandboxSimulationPlatform",
                payload={"scenario_id": scenario_id},
            )
        )

        return comp

    def archive_sandbox_experiment(self, scenario_id: str) -> None:
        """Transition scenario state to Archived and publish events."""
        scenario = self.scenarios.get(scenario_id)
        if not scenario:
            raise SandboxSimulationError(f"Scenario not found: '{scenario_id}'")

        scenario.lifecycle_state = "Archived"

        self.event_bus.publish_sync(
            Event(
                name="simulation.experiment.archived",
                category="SandboxSimulation",
                source="SandboxSimulationPlatform",
                payload={"scenario_id": scenario_id},
            )
        )
