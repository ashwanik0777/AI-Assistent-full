"""Certification and Benchmark generator for Phase 3 - Brain Foundation."""

import time
import sys
import resource
from aira.infrastructure.config import load_config
from aira.infrastructure.event_bus import EventBus
from aira.infrastructure.service_registry import ServiceRegistry
from aira.infrastructure.di_container import DependencyContainer
from aira.infrastructure.brain_core import BrainManager
from aira.infrastructure.model_router import ModelRouterManager
from aira.infrastructure.reasoning_interface import ReasoningManager
from aira.infrastructure.goal_manager import GoalManager
from aira.infrastructure.planner import PlannerManager
from aira.infrastructure.task_graph import TaskGraphManager
from aira.infrastructure.execution_planner import ExecutionPlannerManager
from aira.infrastructure.brain_runtime import BrainRuntimePipeline
from aira.infrastructure.brain_evaluator import BrainEvaluatorManager

def run_certification():
    print("=== STARTING AIRA BRAIN FOUNDATION CERTIFICATION ===")
    
    # 1. Startup Time Measurement
    start_time = time.perf_counter()
    container = DependencyContainer()
    registry = ServiceRegistry(container)
    bus = EventBus()
    config = load_config()
    
    brain_core = BrainManager(config, registry, bus)
    model_router = ModelRouterManager(config, registry, bus)
    reasoning = ReasoningManager(config, registry, bus)
    goal_manager = GoalManager(config, registry, bus)
    planner = PlannerManager(config, registry, bus)
    task_graph = TaskGraphManager(config, registry, bus)
    execution_planner = ExecutionPlannerManager(config, registry, bus)
    
    pipeline = BrainRuntimePipeline(
        config, registry, bus,
        brain_core, model_router, reasoning, goal_manager,
        planner, task_graph, execution_planner
    )
    
    evaluator = BrainEvaluatorManager(config, registry, bus, pipeline)
    startup_latency = (time.perf_counter() - start_time) * 1000.0
    print(f"Brain Startup Latency: {startup_latency:.2f} ms")
    
    # 2. Memory Footprint
    usage = resource.getrusage(resource.RUSAGE_SELF)
    # ru_maxrss is in bytes on macOS, but kilobytes on Linux. On Mac it is bytes.
    print(f"Peak RSS Memory Usage: {usage.ru_maxrss / (1024 * 1024):.2f} MB")
    
    # 3. Running Evaluator Pipeline
    print("Running evaluation scenario benchmarks...")
    report = evaluator.run_evaluations()
    
    print("\n=== EVALUATION REPORT ===")
    print(f"Total Scenarios: {report['total_scenarios']}")
    print(f"Success Count: {report['success_count']}")
    print("Scores:")
    for key, val in report['scores'].items():
        print(f"  - {key}: {val}")
        
    print("\nScenario Reports:")
    for rep in report['reports']:
        print(f"  - [{rep['status']}] Scenario: {rep['scenario_id']} | Latency: {rep['latency']*1000:.2f} ms")
        
    print("=== CERTIFICATION COMPLETE ===")

if __name__ == "__main__":
    run_certification()
