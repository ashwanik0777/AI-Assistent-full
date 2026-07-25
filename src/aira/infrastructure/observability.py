"""Enterprise Runtime Observability Framework for AIRA.

Provides read-only health checks, diagnostics validation, metrics collections,
runtime snapshots, and self-test frameworks.
"""

import json
from datetime import datetime
from typing import Any, Literal

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.di_container import DependencyContainer
from aira.infrastructure.event_bus import EventBus
from aira.infrastructure.kernel import AIRAKernel
from aira.infrastructure.lifecycle import LifecycleOrchestrator
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.observability")

HealthStateType = Literal["HEALTHY", "DEGRADED", "WARNING", "UNAVAILABLE", "FAILED", "UNKNOWN"]


class ObservabilityError(Exception):
    """Base exception for all observability framework failures."""

    pass


class DiagnosticsError(ObservabilityError):
    """Raised during diagnostics checks fail."""

    pass


class SelfTestFailureError(ObservabilityError):
    """Raised when self-test validation executions fail."""

    pass


class MetricRegistry:
    """Read-only metrics accumulator for tracking boot milestones, counts, and errors."""

    def __init__(self) -> None:
        self._counters: dict[str, int] = {}
        self._gauges: dict[str, float] = {}

    def increment(self, name: str, value: int = 1) -> None:
        """Increment a counter metric."""
        self._counters[name] = self._counters.get(name, 0) + value

    def set_gauge(self, name: str, value: float) -> None:
        """Set a gauge metric value."""
        self._gauges[name] = value

    def to_dict(self) -> dict[str, Any]:
        """Serialize metrics catalog."""
        return {"counters": self._counters, "gauges": self._gauges}


class SelfTestFramework:
    """Performs validation checks on core components to confirm operational readiness."""

    def __init__(
        self,
        config: AppConfig,
        container: DependencyContainer,
        registry: ServiceRegistry,
        event_bus: EventBus,
        kernel: AIRAKernel,
    ) -> None:
        self._config = config
        self._container = container
        self._registry = registry
        self._event_bus = event_bus
        self._kernel = kernel

    def run_all_tests(self) -> dict[str, Any]:
        """Execute validation tests on core services, returning pass/fail details."""
        results = {}

        # 1. Config Validation
        try:
            assert self._config.version == "0.1.0"
            assert self._config.env.profile in ["development", "testing", "production"]
            results["config"] = {"status": "PASSED"}
        except Exception as e:
            results["config"] = {"status": "FAILED", "error": str(e)}

        # 2. Logger Validation
        try:
            # Verify we can resolve structlog loggers
            log = structlog.get_logger("aira.selftest")
            log.debug("Observability self-test verification ping")
            results["logger"] = {"status": "PASSED"}
        except Exception as e:
            results["logger"] = {"status": "FAILED", "error": str(e)}

        # 3. DI Validation
        try:
            self._container.validate_container()
            results["di"] = {"status": "PASSED"}
        except Exception as e:
            results["di"] = {"status": "FAILED", "error": str(e)}

        # 4. Registry Validation
        try:
            self._registry.validate_registry()
            results["registry"] = {"status": "PASSED"}
        except Exception as e:
            results["registry"] = {"status": "FAILED", "error": str(e)}

        # 5. Event Bus Validation
        try:
            received = []
            self._event_bus.subscribe(
                "selftest.ping", lambda ev: received.append(True), is_temporary=True
            )
            from aira.infrastructure.event_bus import Event

            ping_ev = Event("selftest.ping", "Testing", "Observability", {})
            self._event_bus.publish_sync(ping_ev)
            assert len(received) == 1
            results["event_bus"] = {"status": "PASSED"}
        except Exception as e:
            results["event_bus"] = {"status": "FAILED", "error": str(e)}

        # 6. Kernel Validation
        try:
            assert self._kernel.state in ["READY", "RUNNING", "INITIALIZING"]
            results["kernel"] = {"status": "PASSED"}
        except Exception as e:
            results["kernel"] = {"status": "FAILED", "error": str(e)}

        # Check if any checks failed
        failed_tests = [k for k, v in results.items() if v["status"] == "FAILED"]
        if failed_tests:
            logger.error("Observability self-tests failed", failed=failed_tests)
            raise SelfTestFailureError(f"Self-tests failed for components: {failed_tests}")

        logger.info("Observability self-tests completed: SUCCESS")
        return results


class ObservabilityFramework:
    """Enterprise Observability Coordinator providing snapshots, diagnostics, and reports."""

    def __init__(
        self,
        config: AppConfig,
        container: DependencyContainer,
        registry: ServiceRegistry,
        event_bus: EventBus,
        lifecycle: LifecycleOrchestrator,
        kernel: AIRAKernel,
    ) -> None:
        self.config = config
        self.container = container
        self.registry = registry
        self.event_bus = event_bus
        self.lifecycle = lifecycle
        self.kernel = kernel

        self.metrics = MetricRegistry()
        self.self_tester = SelfTestFramework(config, container, registry, event_bus, kernel)

        # Initialize base counters
        self.metrics.increment("errors_count", 0)
        self.metrics.increment("warnings_count", 0)

    def evaluate_health(self) -> dict[str, Any]:
        """Compute status profiles for registered services and kernel states."""
        health_details = {}
        services = self.registry.list_services()

        healthy_count = 0
        failed_count = 0

        for s in services:
            # Map registry states to observability health states
            if s.status == "READY":
                state = "HEALTHY"
                healthy_count += 1
            elif s.status == "FAILED":
                state = "FAILED"
                failed_count += 1
            elif s.status == "DISABLED":
                state = "UNAVAILABLE"
            else:
                state = "UNKNOWN"

            health_details[s.name] = {
                "state": state,
                "score": s.health_score,
                "uptime_seconds": (
                    (datetime.now() - s.uptime_start).total_seconds() if s.uptime_start else 0.0
                ),
            }

        # Deduce overall status
        if failed_count > 0:
            overall = "DEGRADED"
        elif healthy_count == len(services):
            overall = "HEALTHY"
        else:
            overall = "WARNING"

        return {
            "status": overall,
            "components": health_details,
            "timestamp": datetime.now().isoformat(),
        }

    def generate_diagnostics_report(self) -> dict[str, Any]:
        """Generate structured runtime diagnostic audits of core systems."""
        try:
            return {
                "config_checksum": hash(str(self.config.model_dump())),
                "registered_services": [s.name for s in self.registry.list_services()],
                "di_services_count": len(self.container.list_services()),
                "event_bus_stats": self._event_bus_diagnostics(),
                "lifecycle_state": self.lifecycle.state,
                "kernel_state": self.kernel.state,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            err_msg = f"Failed to generate diagnostics report: {e}"
            logger.error("Observability diagnostics failure", error=str(e))
            raise DiagnosticsError(err_msg) from e

    def _event_bus_diagnostics(self) -> dict[str, Any]:
        try:
            return self.event_bus.get_diagnostics()
        except Exception:
            return {"error": "Event bus diagnostics lookup failed"}

    def take_snapshot(self) -> dict[str, Any]:
        """Capture and return a serializable state snapshot of the active application session."""
        try:
            health = self.evaluate_health()

            return {
                "app_info": {"name": "AIRA", "version": self.config.version},
                "timestamp": datetime.now().isoformat(),
                "kernel": {
                    "state": self.kernel.state,
                    "session_id": self.kernel.context.session_id,
                    "runtime_id": self.kernel.context.runtime_id,
                },
                "health": health,
                "metrics": self.metrics.to_dict(),
                "services": [s.to_dict() for s in self.registry.list_services()],
            }
        except Exception as e:
            err_msg = f"Failed to generate runtime snapshot: {e}"
            logger.error("Snapshot extraction failed", error=str(e))
            raise ObservabilityError(err_msg) from e

    def generate_report(self, report_type: Literal["summary", "detailed", "diagnostics"]) -> str:
        """Export serialized reports structured in JSON formats."""
        try:
            if report_type == "summary":
                data = {
                    "status": self.evaluate_health()["status"],
                    "kernel_state": self.kernel.state,
                    "timestamp": datetime.now().isoformat(),
                }
            elif report_type == "diagnostics":
                data = self.generate_diagnostics_report()
            else:
                data = self.take_snapshot()

            return json.dumps(data, indent=2)
        except Exception as e:
            err_msg = f"Report generation failed for type '{report_type}': {e}"
            logger.error("Observability report failure", report_type=report_type, error=str(e))
            raise ObservabilityError(err_msg) from e
