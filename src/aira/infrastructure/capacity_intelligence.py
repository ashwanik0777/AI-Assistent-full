"""Enterprise Capacity Intelligence & Sustainability Optimization Platform.

Provides capacity analyzers, forecast engines, and optimization engines.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.capacity_intelligence")


class CapacityIntelligenceError(Exception):
    """Base exception raised for capacity forecasting failures or validation constraints."""

    pass


@dataclass
class CapacityRecommendation:
    """Recommendation specifying utilization metrics, projections, and green impact."""

    recommendation_id: str
    resource_group: str
    current_utilization: dict[str, float]
    forecast: dict[str, Any]
    optimization_proposal: str
    estimated_cost_impact: float
    estimated_performance_impact: str
    estimated_sustainability_impact: dict[str, Any]
    confidence: float
    metadata: dict[str, Any] = field(default_factory=dict)
    version: int = 1


class CapacityAnalyzer:
    """Measures component usage metrics (CPU, Memory, Storage)."""

    def analyze_utilization(self, current: dict[str, float]) -> dict[str, float]:
        """Verify metrics ranges values and return valid usage map."""
        for metric, val in current.items():
            if val < 0.0 or val > 100.0:
                raise CapacityIntelligenceError(
                    f"Analysis failed: Metric '{metric}' value '{val}' is invalid."
                )
        return current


class ForecastEngine:
    """Predicts peak demand growth and capacity exhaustion trends."""

    def generate_forecast(self, utilization: dict[str, float]) -> dict[str, Any]:
        """Generate projection trend values based on current utilization."""
        cpu = utilization.get("cpu", 0.0)
        # Sustained growth projection
        growth = "Sustained Growth" if cpu > 70.0 else "Stable"
        return {
            "predicted_peak_cpu": cpu * 1.15,
            "growth_trend": growth,
            "days_to_exhaustion": 14 if cpu > 80.0 else 90,
        }


class OptimizationEngine:
    """Formulates resource action proposals (increase capacity, resource consolidation)."""

    def propose_optimization(self, trend: str) -> str:
        """Propose capacity adjustment strategy."""
        if trend == "Sustained Growth":
            return "Increase Capacity"
        elif trend == "Stable":
            return "Resource Consolidation"
        return "No Action"


class EconomicsEngine:
    """Projects operational budget savings opportunities and costs estimations."""

    def estimate_financial_impact(self, proposal: str) -> float:
        """Calculate cost delta based on proposal action key."""
        if proposal == "Increase Capacity":
            return 500.0  # cost increase
        elif proposal == "Resource Consolidation":
            return -350.0  # cost savings
        return 0.0


class SustainabilityAnalyzer:
    """Estimates energy conservation metrics and carbon emission updates."""

    def estimate_sustainability_impact(self, proposal: str) -> dict[str, Any]:
        """Return carbon and energy changes estimates dictionary."""
        if proposal == "Resource Consolidation":
            return {"energy_saved_kwh": 120.0, "carbon_offset_kg": 48.0}
        return {"energy_saved_kwh": 0.0, "carbon_offset_kg": 0.0}


class CapacityRecommendationManager:
    """Coordinating manager resolving metrics, recommendations, and dispatches events."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.analyzer = CapacityAnalyzer()
        self.forecast_engine = ForecastEngine()
        self.optimization_engine = OptimizationEngine()
        self.economics_engine = EconomicsEngine()
        self.sustainability_analyzer = SustainabilityAnalyzer()

        self.recommendations: dict[str, CapacityRecommendation] = {}

    def generate_recommendation(
        self, rec_id: str, resource_group: str, metrics: dict[str, float]
    ) -> CapacityRecommendation:
        """Analyze metrics, run optimization checks, and publish events."""
        # 1. Analyze
        util = self.analyzer.analyze_utilization(metrics)
        self.event_bus.publish_sync(
            Event(
                name="capacity.analyzed",
                category="CapacityIntelligence",
                source="CapacityRecommendationManager",
                payload={"resource_group": resource_group, "utilization": util},
            )
        )

        # 2. Forecast
        forecast = self.forecast_engine.generate_forecast(util)
        self.event_bus.publish_sync(
            Event(
                name="forecast.generated",
                category="CapacityIntelligence",
                source="CapacityRecommendationManager",
                payload={"forecast": forecast},
            )
        )

        # 3. Optimize
        proposal = self.optimization_engine.propose_optimization(forecast["growth_trend"])
        self.event_bus.publish_sync(
            Event(
                name="optimization.proposed",
                category="CapacityIntelligence",
                source="CapacityRecommendationManager",
                payload={"proposal": proposal},
            )
        )

        # 4. Economics & Sustainability
        cost = self.economics_engine.estimate_financial_impact(proposal)
        self.event_bus.publish_sync(
            Event(
                name="economics.updated",
                category="CapacityIntelligence",
                source="CapacityRecommendationManager",
                payload={"cost_delta": cost},
            )
        )

        sustainability = self.sustainability_analyzer.estimate_sustainability_impact(proposal)

        # 5. Recommendation
        rec = CapacityRecommendation(
            recommendation_id=rec_id,
            resource_group=resource_group,
            current_utilization=util,
            forecast=forecast,
            optimization_proposal=proposal,
            estimated_cost_impact=cost,
            estimated_performance_impact="High" if proposal == "Increase Capacity" else "Normal",
            estimated_sustainability_impact=sustainability,
            confidence=0.92,
        )

        self.recommendations[rec_id] = rec

        self.event_bus.publish_sync(
            Event(
                name="recommendation.published",
                category="CapacityIntelligence",
                source="CapacityRecommendationManager",
                payload={"recommendation_id": rec_id},
            )
        )

        return rec
