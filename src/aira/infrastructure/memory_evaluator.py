"""Enterprise Memory Quality, Evaluation & Benchmark Framework for AIRA.

Provides continuous monitoring, audits checks, latencies benchmarks, and context explainability.
"""

import threading
import time
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.knowledge_graph import KnowledgeGraphStore
from aira.infrastructure.procedural_memory import ProcedureLibrary
from aira.infrastructure.retrieval_engine import HybridRetrievalEngine
from aira.infrastructure.semantic_memory import SemanticStore
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.memory_evaluator")


class MemoryEvaluatorError(Exception):
    """Raised when health scoring calculations, audits sweeps, or benchmark checks fail."""

    pass


class MemoryAuditor:
    """Scans memory systems searching for integrity broken nodes or overlaps."""

    def run_audit(
        self,
        semantic_store: SemanticStore,
        procedure_lib: ProcedureLibrary,
        graph_store: KnowledgeGraphStore,
    ) -> dict[str, Any]:
        """Perform full validation audit checks across all stores."""
        facts = semantic_store.list_all()
        procedures = procedure_lib.list_all()
        relationships = graph_store.list_relationships()
        entities = graph_store.list_entities()

        entity_ids = {e.entity_id for e in entities}
        broken_relationships = 0
        orphan_entities = set(entity_ids)

        for rel in relationships:
            if rel.source_entity not in entity_ids or rel.target_entity not in entity_ids:
                broken_relationships += 1
            orphan_entities.discard(rel.source_entity)
            orphan_entities.discard(rel.target_entity)

        # Count facts missing confidence metadata
        incomplete_facts = sum(1 for f in facts if f.confidence_score is None)

        # Find duplicate facts having matching subject/predicate
        seen_triples = set()
        duplicate_facts = 0
        for f in facts:
            key = (f.subject.lower(), f.predicate.lower())
            if key in seen_triples:
                duplicate_facts += 1
            else:
                seen_triples.add(key)

        return {
            "duplicate_facts": duplicate_facts,
            "broken_relationships": broken_relationships,
            "orphan_entities_count": len(orphan_entities),
            "incomplete_facts_metadata": incomplete_facts,
            "deprecated_procedures": sum(1 for p in procedures if p.success_score < 0.3),
            "total_facts": len(facts),
            "total_procedures": len(procedures),
            "total_relationships": len(relationships),
            "total_entities": len(entities),
        }


class MemoryBenchmarkSuite:
    """Timer metrics sweeps mapping insertions and lookups latencies."""

    def run_benchmarks(
        self,
        semantic_store: SemanticStore,
        procedure_lib: ProcedureLibrary,
        graph_store: KnowledgeGraphStore,
        retrieval_engine: HybridRetrievalEngine,
    ) -> dict[str, Any]:
        """Measure speed execution durations in milliseconds."""
        results = {}

        # 1. Benchmark Graph Traversal query speed
        start = time.perf_counter()
        _ = graph_store.list_relationships()
        results["graph_query_latency_ms"] = (time.perf_counter() - start) * 1000.0

        # 2. Benchmark Semantic facts extraction lookup list
        start = time.perf_counter()
        _ = semantic_store.list_all()
        results["facts_lookup_latency_ms"] = (time.perf_counter() - start) * 1000.0

        # 3. Benchmark Procedures library catalog checks
        start = time.perf_counter()
        _ = procedure_lib.list_all()
        results["procedures_lookup_latency_ms"] = (time.perf_counter() - start) * 1000.0

        # 4. Benchmark hybrid retrieval planner and context assembly
        start = time.perf_counter()
        _ = retrieval_engine.assemble_context(
            query="What database does CareerHub use?",
            semantic_store=semantic_store,
            procedure_lib=procedure_lib,
            graph_store=graph_store,
        )
        results["retrieval_context_assembly_latency_ms"] = (time.perf_counter() - start) * 1000.0

        return results


class HealthAnalyzer:
    """Scores reliability, metadata freshness, and structural health profiles."""

    def calculate_health_scores(
        self, audit_results: dict[str, Any], benchmark_results: dict[str, Any]
    ) -> dict[str, Any]:
        """Perform mathematical weighting conversions to format scorecards."""
        # 1. Integrity Score: penalize broken graph links and duplicate keys
        base_integrity = 100.0
        penalties = (audit_results["broken_relationships"] * 10) + (
            audit_results["duplicate_facts"] * 5
        )
        integrity_score = max(0.0, base_integrity - penalties)

        # 2. Efficiency Score: penalize retrieval latencies exceeding 20ms thresholds
        retrieval_time = benchmark_results.get("retrieval_context_assembly_latency_ms", 0.0)
        efficiency_score = max(0.0, 100.0 - max(0.0, (retrieval_time - 20.0) * 2.0))

        # 3. Reliability Score: penalize low success rates procedures
        proc_penalty = audit_results["deprecated_procedures"] * 15.0
        reliability_score = max(0.0, 100.0 - proc_penalty)

        # 4. Overall health average weighting card metrics
        overall_score = (integrity_score + efficiency_score + reliability_score) / 3.0

        return {
            "overall_health_score": round(overall_score, 2),
            "integrity_score": round(integrity_score, 2),
            "efficiency_score": round(efficiency_score, 2),
            "reliability_score": round(reliability_score, 2),
            "freshness_score": 100.0,  # Base scale framework placeholder
            "quality_score": round((integrity_score + reliability_score) / 2.0, 2),
        }


class RetrievalEvaluator:
    """Generates explainability reports detail selections choices."""

    def evaluate_retrieval(self, payload: dict[str, Any], query: str) -> dict[str, Any]:
        """Formulate explainability reasons for retrieved keys."""
        explanations = []

        for f in payload.get("facts", []):
            explanations.append(
                {
                    "item": f"{f['subject']} {f['predicate']} {f['object']}",
                    "source": "SemanticStore",
                    "reason": f"Matches semantic terms query matching keywords for: '{query}'",
                    "confidence": 1.0,
                }
            )

        for p in payload.get("procedures", []):
            explanations.append(
                {
                    "item": p["name"],
                    "source": "ProcedureLibrary",
                    "reason": "Matches procedure tasks terms mappings",
                    "confidence": 1.0,
                }
            )

        return {
            "query": query,
            "explainability_trail": explanations,
            "context_size_char": len(str(payload)),
            "source_diversity": list({e["source"] for e in explanations}),
        }


class MemoryEvaluatorEngine:
    """Orchestrates quality audit checks, health evaluations, and speed benchmarks."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.auditor = MemoryAuditor()
        self.benchmark_suite = MemoryBenchmarkSuite()
        self.health_analyzer = HealthAnalyzer()
        self.retrieval_evaluator = RetrievalEvaluator()
        self.lock = threading.Lock()

    def run_evaluations(
        self,
        semantic_store: SemanticStore,
        procedure_lib: ProcedureLibrary,
        graph_store: KnowledgeGraphStore,
        retrieval_engine: HybridRetrievalEngine,
    ) -> dict[str, Any]:
        """Perform synchronous audit passes, benchmark sweeps, and score compiles."""
        with self.lock:
            # 1. Audit check
            audit_res = self.auditor.run_audit(semantic_store, procedure_lib, graph_store)
            self.event_bus.publish_sync(
                Event(
                    name="audit.completed",
                    category="Memory",
                    source="MemoryEvaluatorEngine",
                    payload=audit_res,
                )
            )

            # 2. Benchmark run
            bench_res = self.benchmark_suite.run_benchmarks(
                semantic_store, procedure_lib, graph_store, retrieval_engine
            )
            self.event_bus.publish_sync(
                Event(
                    name="benchmark.completed",
                    category="Memory",
                    source="MemoryEvaluatorEngine",
                    payload=bench_res,
                )
            )

            # 3. Calculate Health Scorecard
            health_res = self.health_analyzer.calculate_health_scores(audit_res, bench_res)
            self.event_bus.publish_sync(
                Event(
                    name="health.updated",
                    category="Memory",
                    source="MemoryEvaluatorEngine",
                    payload=health_res,
                )
            )

            self.event_bus.publish_sync(
                Event(
                    name="quality.evaluated",
                    category="Memory",
                    source="MemoryEvaluatorEngine",
                    payload={"health_score": health_res["overall_health_score"]},
                )
            )

            report = {
                "audit": audit_res,
                "benchmarks": bench_res,
                "health": health_res,
                "timestamp": time.time(),
            }

            self.event_bus.publish_sync(
                Event(
                    name="report.generated",
                    category="Memory",
                    source="MemoryEvaluatorEngine",
                    payload={"overall_health": health_res["overall_health_score"]},
                )
            )

            return report

    def evaluate_and_explain_retrieval(
        self, query: str, retrieval_payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Formulate explainability details for a past retrieval cycle."""
        with self.lock:
            eval_res = self.retrieval_evaluator.evaluate_retrieval(retrieval_payload, query)
            self.event_bus.publish_sync(
                Event(
                    name="retrieval.evaluated",
                    category="Memory",
                    source="MemoryEvaluatorEngine",
                    payload={"explanations": len(eval_res["explainability_trail"])},
                )
            )
            return eval_res
