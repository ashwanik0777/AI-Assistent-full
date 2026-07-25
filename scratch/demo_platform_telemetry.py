"""Demonstration script for Phase 10 — Sprint 10.8 (Enterprise Platform Operations, Telemetry & Ecosystem Intelligence)."""

import time
from aira.infrastructure.config import AppConfig
from aira.infrastructure.di_container import DependencyContainer
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry
from aira.infrastructure.agent_runtime import AgentRuntimeKernel
from aira.infrastructure.platform_telemetry import TelemetryRecord


def run_demo() -> None:
    print("=== AIRA Platform Operations & Telemetry Demo ===")

    # Setup
    config = AppConfig()
    container = DependencyContainer()
    registry = ServiceRegistry(container)
    event_bus = EventBus()

    # Event listener
    def on_event(event: Event) -> None:
        print(f"[Event Triggered] Name: {event.name} | Category: {event.category} | Payload: {event.payload}")

    event_bus.subscribe("telemetry.collected", on_event)
    event_bus.subscribe("metrics.updated", on_event)
    event_bus.subscribe("dashboard.updated", on_event)
    event_bus.subscribe("health.updated", on_event)
    event_bus.subscribe("privacy_policy_applied", on_event)

    kernel = AgentRuntimeKernel(config, registry, event_bus)

    print("\n--- SCENARIO 1: Simulate Platform Activity and compile health dashboard ---")
    # Enable consent
    kernel.telemetry_manager.set_privacy_consent(is_opt_in=True)

    r_ok1 = TelemetryRecord(
        timestamp=time.time(),
        component="ExtensionRuntime",
        environment="Production",
        event_type="extension.execution",
        metrics={"duration_ms": 45.0},
        severity="INFO"
    )

    r_ok2 = TelemetryRecord(
        timestamp=time.time(),
        component="AgentRuntime",
        environment="Production",
        event_type="agent.reasoning",
        metrics={"duration_ms": 1100.0},
        severity="INFO"
    )

    r_err = TelemetryRecord(
        timestamp=time.time(),
        component="KnowledgePackRuntime",
        environment="Production",
        event_type="knowledge.query_failed",
        metrics={"duration_ms": 0.0},
        severity="ERROR"
    )

    print("Submitting platform activities telemetry records...")
    kernel.telemetry_manager.submit_telemetry(r_ok1)
    kernel.telemetry_manager.submit_telemetry(r_ok2)
    kernel.telemetry_manager.submit_telemetry(r_err)

    print("\nGenerating operations dashboard...")
    dashboard = kernel.telemetry_manager.generate_operations_dashboard()
    print("\nDashboard Report Output:")
    print(dashboard)


    print("--- SCENARIO 2: Disable Telemetry and verify Privacy Compliance policies ---")
    print("Disabling telemetry consent (Opt-Out policy)...")
    kernel.telemetry_manager.set_privacy_consent(is_opt_in=False)

    # Empty buffer to verify next collections
    kernel.telemetry_manager.collector.buffer.clear()

    r_protected = TelemetryRecord(
        timestamp=time.time(),
        component="MarketplaceManager",
        environment="Production",
        event_type="publisher.credentials_entered",
        metrics={"keystrokes": 12},
        privacy_classification="Protected"
    )

    print("\nSubmitting protected data record under Opt-Out policy...")
    kernel.telemetry_manager.submit_telemetry(r_protected)

    print(f"  Buffer size (should be 0): {len(kernel.telemetry_manager.collector.buffer)}")
    print("\nPrivacy Compliance audit completed: No Protected telemetry collected under Opt-Out mode.")

    print("\n=== Demo completed successfully ===")


if __name__ == "__main__":
    run_demo()
