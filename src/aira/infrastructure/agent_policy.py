"""Enterprise Policy Engine & Safety Framework for AIRA.

Provides risk analysis, mapping rules, caching, and approvals management.
"""

import time
from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.agent_policy")


class AgentPolicyError(Exception):
    """Raised when risk analyzer scores, decision validations, or governance rules are violated."""

    pass


@dataclass
class PolicyDecision:
    """Consolidated policy result capturing risk score evaluations and applied scopes."""

    decision_id: str
    intent_id: str
    risk_score: float
    decision_outcome: str  # Allow, Deny, Ask Once, Require Explicit Approval
    applied_policy: str
    evidence: str
    reason: str
    expiration: float
    metadata: dict[str, Any] = field(default_factory=dict)
    version: str = "1.0.0"


@dataclass
class AuditRecord:
    """Governance record detailing historical user validation approvals."""

    audit_id: str
    decision_id: str
    timestamp: float = field(default_factory=time.time)
    user_approval_status: str = "Pending"
    execution_result: str = "Unknown"


class RiskAnalyzer:
    """Rates capability actions risk indexes on a numeric scale (0.0 to 10.0)."""

    def evaluate_risk(self, capability: str) -> float:
        """Score risk index based on target activity descriptions keywords."""
        cap_lower = capability.lower()
        if "delete" in cap_lower or "write" in cap_lower:
            return 8.5
        if "read" in cap_lower or "analyze" in cap_lower:
            return 2.0
        return 5.0


class PolicyEngine:
    """Translates evaluated numeric risk index scores into standardized outcomes."""

    def evaluate_policy(self, risk_score: float) -> tuple[str, str]:
        """Determine policy target rules and outcomes names."""
        if risk_score >= 8.0:
            return "Deny", "HighRiskPolicy"
        if risk_score >= 5.0:
            return "Require Explicit Approval", "MediumRiskPolicy"
        return "Allow", "LowRiskPolicy"


class DecisionCache:
    """Stores reusable Low-Risk allow decisions to bypass redundant engines evaluations."""

    def __init__(self) -> None:
        self.cached_decisions: dict[str, PolicyDecision] = {}

    def get_cached(self, intent_id: str) -> PolicyDecision | None:
        """Lookup active cached decision if present and unexpired."""
        decision = self.cached_decisions.get(intent_id)
        if decision and time.time() < decision.expiration:
            return decision
        return None

    def cache_decision(self, decision: PolicyDecision) -> None:
        """Record decision cache entry."""
        self.cached_decisions[decision.intent_id] = decision


class ApprovalManager:
    """Logs active human approvals history steps."""

    def __init__(self) -> None:
        # Map intent_id -> status (Pending, Approved, Rejected)
        self.approvals_status: dict[str, str] = {}

    def request_approval(self, intent_id: str) -> None:
        """Mark intent as pending validation authorization."""
        self.approvals_status[intent_id] = "Pending"

    def approve(self, intent_id: str) -> None:
        """Set intent as approved."""
        self.approvals_status[intent_id] = "Approved"

    def reject(self, intent_id: str) -> None:
        """Set intent as rejected."""
        self.approvals_status[intent_id] = "Rejected"


class GovernanceAuditManager:
    """Maintains logs histories of decisions outcomes for compliance auditing checks."""

    def __init__(self) -> None:
        self.audit_records: list[AuditRecord] = []

    def record_audit(
        self, audit_id: str, decision_id: str, status: str, result: str
    ) -> AuditRecord:
        """Save a new compliance validation log record."""
        record = AuditRecord(
            audit_id=audit_id,
            decision_id=decision_id,
            user_approval_status=status,
            execution_result=result,
        )
        self.audit_records.append(record)
        return record


class PolicyOrchestrator:
    """Evaluates risk indexes, enforces policy rules, and records audit logs."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.risk_analyzer = RiskAnalyzer()
        self.policy_engine = PolicyEngine()
        self.decision_cache = DecisionCache()
        self.approval_manager = ApprovalManager()
        self.audit_manager = GovernanceAuditManager()

    def evaluate_execution(self, intent_id: str, capability: str) -> PolicyDecision:
        """Orchestrate evaluation: cache check -> risk scoring -> policy map -> audit logs."""
        # 1. Cache Check
        cached = self.decision_cache.get_cached(intent_id)
        if cached:
            self.event_bus.publish_sync(
                Event(
                    name="decision.cached",
                    category="Security",
                    source="PolicyOrchestrator",
                    payload={"decision_id": cached.decision_id},
                )
            )
            return cached

        # 2. Risk Score Evaluation
        score = self.risk_analyzer.evaluate_risk(capability)
        self.event_bus.publish_sync(
            Event(
                name="risk.evaluated",
                category="Security",
                source="PolicyOrchestrator",
                payload={"intent_id": intent_id, "score": score},
            )
        )

        # 3. Policy outcome mapping
        outcome, policy_name = self.policy_engine.evaluate_policy(score)
        self.event_bus.publish_sync(
            Event(
                name="policy.applied",
                category="Security",
                source="PolicyOrchestrator",
                payload={"policy": policy_name},
            )
        )

        decision_id = f"dec_{intent_id}"
        decision = PolicyDecision(
            decision_id=decision_id,
            intent_id=intent_id,
            risk_score=score,
            decision_outcome=outcome,
            applied_policy=policy_name,
            evidence=f"Risk Score evaluated to {score} based on '{capability}' capability.",
            reason="Automated policy scoring engine evaluation.",
            expiration=time.time() + 60.0,
        )

        # Handle approvals workflow check triggers
        if outcome == "Require Explicit Approval":
            app_status = self.approval_manager.approvals_status.get(intent_id)
            if not app_status:
                self.approval_manager.request_approval(intent_id)
                self.event_bus.publish_sync(
                    Event(
                        name="approval.requested",
                        category="Security",
                        source="PolicyOrchestrator",
                        payload={"intent_id": intent_id},
                    )
                )
            elif app_status == "Approved":
                self.event_bus.publish_sync(
                    Event(
                        name="approval.granted",
                        category="Security",
                        source="PolicyOrchestrator",
                        payload={"intent_id": intent_id},
                    )
                )
                self.event_bus.publish_sync(
                    Event(
                        name="execution.authorized",
                        category="Security",
                        source="PolicyOrchestrator",
                        payload={"intent_id": intent_id},
                    )
                )
                # Cache successful authorized decisions
                self.decision_cache.cache_decision(decision)
                return decision

            # Stop execution
            self.event_bus.publish_sync(
                Event(
                    name="execution.denied",
                    category="Security",
                    source="PolicyOrchestrator",
                    payload={"intent_id": intent_id},
                )
            )
            # Record audit log
            self.audit_manager.record_audit(
                f"audit_{intent_id}", decision_id, app_status or "Pending", "Blocked"
            )
            raise AgentPolicyError(
                f"Access Denied: Intent '{intent_id}' requires explicit approval."
            )

        if outcome == "Deny":
            self.event_bus.publish_sync(
                Event(
                    name="execution.denied",
                    category="Security",
                    source="PolicyOrchestrator",
                    payload={"intent_id": intent_id},
                )
            )
            self.audit_manager.record_audit(f"audit_{intent_id}", decision_id, "Rejected", "Denied")
            raise AgentPolicyError(
                f"Access Denied: High-risk intent '{intent_id}' is blocked by policy."
            )

        # Allow case
        self.event_bus.publish_sync(
            Event(
                name="execution.authorized",
                category="Security",
                source="PolicyOrchestrator",
                payload={"intent_id": intent_id},
            )
        )
        self.decision_cache.cache_decision(decision)
        self.audit_manager.record_audit(
            f"audit_{intent_id}", decision_id, "AutoApproved", "Success"
        )
        return decision
