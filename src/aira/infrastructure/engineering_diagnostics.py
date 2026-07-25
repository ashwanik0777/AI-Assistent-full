"""Enterprise Engineering Diagnostics & Refactoring Intelligence subsystem for AIRA.

Diagnoses compiler/runtime issues and generates structured refactoring plans.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.engineering_diagnostics")


class EngineeringDiagnosticsError(Exception):
    """Raised when diagnostics engines, root cause analyzers, or refactoring plans fail."""

    pass


@dataclass
class ProblemObject:
    """Represents a compile error, test failure, dependency warning, or code smell."""

    problem_id: str
    problem_type: str  # CompilerError, BuildFailure, DependencyWarning, CodeSmell
    description: str
    target_file: str
    line_number: int = 0
    severity: str = "Error"  # Error, Warning, Info
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Hypothesis:
    """A proposed cause for a problem, backed by structured evidence logs."""

    cause: str
    confidence: float  # Value between 0.0 and 1.0
    evidence: list[str] = field(default_factory=list)
    suggested_action: str = ""


@dataclass
class RefactoringPlan:
    """Structure outlining recommended file edits and associated risk mappings."""

    plan_id: str
    target_module: str
    refactoring_type: str  # SplitFile, ExtractAbstractions, NamingCleanup, NpDependencies
    description: str
    files_affected: list[str] = field(default_factory=list)
    estimated_risk: str = "Low"  # Low, Medium, High
    dependencies: list[str] = field(default_factory=list)


class DiagnosticsGraph:
    """Graph structure representing problems, hypotheses, and evidence nodes relationships."""

    def __init__(self) -> None:
        self.problems: dict[str, ProblemObject] = {}
        self.hypotheses: dict[str, list[Hypothesis]] = {}

    def add_problem(self, problem: ProblemObject) -> None:
        """Register bug node in graph."""
        self.problems[problem.problem_id] = problem
        if problem.problem_id not in self.hypotheses:
            self.hypotheses[problem.problem_id] = []

    def associate_hypothesis(self, problem_id: str, hypothesis: Hypothesis) -> None:
        """Map hypothesis node to target problem."""
        if problem_id in self.hypotheses:
            self.hypotheses[problem_id].append(hypothesis)


class RootCauseAnalyzer:
    """Analyzes IDE and repo metadata to rank hypotheses with confidence metrics."""

    def analyze_problem(
        self, problem: ProblemObject, repo_history: list[dict[str, Any]]
    ) -> list[Hypothesis]:
        """Examine details to output sorted cause hypotheses list."""
        hypotheses = []

        if problem.problem_type == "BuildFailure":
            # Check if recent commits touch configuration settings
            recent_config_touches = False
            for commit in repo_history:
                for f in commit.get("changed_files", []):
                    if "schema.prisma" in f or "package.json" in f or "prisma" in f:
                        recent_config_touches = True
                        break

            if recent_config_touches:
                hypotheses.append(
                    Hypothesis(
                        cause="Outdated Database Migrations config schemas",
                        confidence=0.85,
                        evidence=[
                            "Recent commit touch prisma configuration schema files",
                            "IDE metadata indicates prisma client initialization errors",
                        ],
                        suggested_action=(
                            "Run npx prisma migrate dev to sync local schema configurations"
                        ),
                    )
                )
            else:
                hypotheses.append(
                    Hypothesis(
                        cause="Corrupted local dependencies or node_modules",
                        confidence=0.50,
                        evidence=["Prisma client cannot resolve standard imports"],
                        suggested_action="Run npm install to rebuild local configurations",
                    )
                )

        elif problem.problem_type == "CodeSmell":
            size = problem.metadata.get("file_size_lines", 0)
            if size > 1000:
                hypotheses.append(
                    Hypothesis(
                        cause="Violates Single Responsibility Principle due to excessive size",
                        confidence=0.90,
                        evidence=[f"Module file size exceeds 1000 lines ({size} lines detected)"],
                        suggested_action="Extract sub-components into separate files structures",
                    )
                )

        # Ensure hypotheses are sorted by confidence descending
        hypotheses.sort(key=lambda h: h.confidence, reverse=True)
        return hypotheses


class RefactoringPlanner:
    """Evaluates large classes/coupling circles to generate structured refactoring plans."""

    def generate_plan(self, problem: ProblemObject) -> RefactoringPlan:
        """Generate structured plan to split or cleanup modular layouts."""
        plan_id = f"plan_{problem.problem_id}"

        if problem.problem_type == "CodeSmell":
            return RefactoringPlan(
                plan_id=plan_id,
                target_module=problem.target_file,
                refactoring_type="SplitFile",
                description="Split monolithic class into independent layout files",
                files_affected=[
                    problem.target_file,
                    f"{problem.target_file.split('.')[0]}_utils.py",
                ],
                estimated_risk="Medium",
            )

        return RefactoringPlan(
            plan_id=plan_id,
            target_module=problem.target_file,
            refactoring_type="NamingCleanup",
            description="Align symbol conventions to pep8 styles",
            files_affected=[problem.target_file],
            estimated_risk="Low",
        )


class ImpactAnalyzer:
    """Calculates risk levels on target test suites or public API endpoints."""

    def analyze_impact(self, plan: RefactoringPlan) -> dict[str, Any]:
        """Verify refactoring plans scope footprint sizes."""
        modules_count = len(plan.files_affected)
        impact_level = "Low"
        if modules_count > 5:
            impact_level = "High"
        elif modules_count > 2 or plan.estimated_risk == "Medium":
            impact_level = "Medium"

        return {
            "impact_level": impact_level,
            "affected_files": plan.files_affected,
            "tests_affected": [f"tests/unit/test_{f.split('/')[-1]}" for f in plan.files_affected],
            "requires_api_change": plan.refactoring_type == "ExtractAbstractions",
        }


class EngineeringDiagnosticsEngine:
    """Primary coordinator organizing diagnostics, impact calculations, and advice logs."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.graph = DiagnosticsGraph()
        self.root_cause_analyzer = RootCauseAnalyzer()
        self.refactoring_planner = RefactoringPlanner()
        self.impact_analyzer = ImpactAnalyzer()

    def submit_problem(self, problem: ProblemObject) -> None:
        """Register problem node in graph database and dispatch event."""
        if not problem.problem_id or not problem.problem_type:
            raise EngineeringDiagnosticsError("Problem ID and type are required.")

        self.graph.add_problem(problem)

        self.event_bus.publish_sync(
            Event(
                name="problem.detected",
                category="Diagnostics",
                source="EngineeringDiagnosticsEngine",
                payload={"problem_id": problem.problem_id, "type": problem.problem_type},
            )
        )

    def run_diagnostics(
        self, problem_id: str, repo_history: list[dict[str, Any]]
    ) -> list[Hypothesis]:
        """Analyze root causes, link nodes in graph, and notify Event Bus."""
        if problem_id not in self.graph.problems:
            raise EngineeringDiagnosticsError(f"Problem '{problem_id}' not registered.")

        problem = self.graph.problems[problem_id]
        hypotheses = self.root_cause_analyzer.analyze_problem(problem, repo_history)

        for hyp in hypotheses:
            self.graph.associate_hypothesis(problem_id, hyp)

        self.event_bus.publish_sync(
            Event(
                name="root_cause.analyzed",
                category="Diagnostics",
                source="EngineeringDiagnosticsEngine",
                payload={"problem_id": problem_id, "hypotheses_count": len(hypotheses)},
            )
        )

        self.event_bus.publish_sync(
            Event(
                name="diagnostics_graph.updated",
                category="Diagnostics",
                source="EngineeringDiagnosticsEngine",
                payload={"problem_id": problem_id},
            )
        )

        return hypotheses

    def generate_refactoring_plan(self, problem_id: str) -> dict[str, Any]:
        """Plan refactoring strategy, calculate impact levels, and notify observers."""
        if problem_id not in self.graph.problems:
            raise EngineeringDiagnosticsError(f"Problem '{problem_id}' not registered.")

        problem = self.graph.problems[problem_id]
        plan = self.refactoring_planner.generate_plan(problem)
        impact = self.impact_analyzer.analyze_impact(plan)

        self.event_bus.publish_sync(
            Event(
                name="refactoring_plan.generated",
                category="Diagnostics",
                source="EngineeringDiagnosticsEngine",
                payload={"plan_id": plan.plan_id},
            )
        )

        self.event_bus.publish_sync(
            Event(
                name="impact_analysis.completed",
                category="Diagnostics",
                source="EngineeringDiagnosticsEngine",
                payload={"plan_id": plan.plan_id, "impact_level": impact["impact_level"]},
            )
        )

        # Engineering Advisor recommendations
        self.event_bus.publish_sync(
            Event(
                name="engineering_advice.published",
                category="Diagnostics",
                source="EngineeringDiagnosticsEngine",
                payload={"problem_id": problem_id, "advice": plan.description},
            )
        )

        return {"plan": plan, "impact": impact}
