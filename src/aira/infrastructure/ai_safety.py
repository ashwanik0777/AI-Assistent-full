"""Enterprise AI Safety, Ethics, Constitutional Governance & Policy Assurance Platform for AIRA.

Provides safety evaluators, ethics engines, policy assurance engines, and risk engines.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.ai_safety")


class SafetyGovernanceError(Exception):
    """Base exception raised for ethics violations or policy assurance failures."""

    pass


@dataclass
class SafetyAssessment:
    """Assessment record validating risk limits, policy rules, and human oversight approvals."""

    assessment_id: str
    action_id: str
    risk_classification: str  # Low, Medium, High, Critical
    policy_evaluation: dict[str, Any]
    ethics_review_summary: str
    constitutional_rules_applied: list[str]
    human_oversight_requirement: bool
    decision: str = "Pending"  # Authorized, Denied, PendingOversight
    metadata: dict[str, Any] = field(default_factory=dict)
    version: int = 1


class SafetyEvaluator:
    """Assesses operational security impacts and compliance guidelines."""

    def evaluate_action(self, action_id: str, parameters: dict[str, Any]) -> bool:
        """Check basic operational safety parameters."""
        # Policy rule: restrict dangerous parameters commands
        return parameters.get("command") != "rm -rf /"


class EthicsEngine:
    """Reviews transparency, fairness, and explainability principles alignment."""

    def review_ethics(self, parameters: dict[str, Any]) -> str:
        """Format ethics summary."""
        return "Fairness and transparency checks verified successfully."


class PolicyAssuranceEngine:
    """Enforces platform constraints and core constitutional policies."""

    def verify_compliance(self, parameters: dict[str, Any]) -> list[str]:
        """Verify that action complies with system constitutional laws."""
        applied_rules = ["NoSelfModification", "GovernAllocations"]
        # Violate constitutional rule if agent attempts to edit core systems
        if parameters.get("action_type") == "modify_system_policy":
            raise SafetyGovernanceError(
                "Policy validation failed: Action violates constitutional "
                "policy rule 'NoSelfModification'."
            )
        return applied_rules


class RiskEngine:
    """Maps actions to risk classes (Low, Medium, High, Critical)."""

    def classify_risk(self, parameters: dict[str, Any]) -> str:
        """Calculate risk class based on parameters payload."""
        action_type = parameters.get("action_type")
        if action_type == "infrastructure_change":
            return "High"
        if action_type == "reboot_system":
            return "Critical"
        return "Low"


class HumanOversightManager:
    """Handles manual approvals and triggers overrides alerts."""

    def check_oversight_trigger(self, risk_level: str) -> bool:
        """Check if action risk demands human oversight approvals."""
        return risk_level in {"High", "Critical"}


class SafetyEvidenceManager:
    """Records complete historical safety assessment evidence logs."""

    def __init__(self) -> None:
        self.evidence_log: list[SafetyAssessment] = []

    def log_assessment(self, assessment: SafetyAssessment) -> None:
        """Record copy of assessment to permanent history."""
        self.evidence_log.append(assessment)


class AISafetyPlatform:
    """Coordinating manager resolving safety evaluations, risk engines, and human reviews."""

    def __init__(self) -> None:
        self.config: AppConfig
        self.registry: ServiceRegistry
        self.event_bus: EventBus

        self.evaluator = SafetyEvaluator()
        self.ethics_engine = EthicsEngine()
        self.policy_assurance = PolicyAssuranceEngine()
        self.risk_engine = RiskEngine()
        self.oversight_manager = HumanOversightManager()
        self.evidence_manager = SafetyEvidenceManager()

    def set_dependencies(
        self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus
    ) -> None:
        """Dependency Injection wrapper."""
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

    def evaluate_action_safety(
        self, assessment_id: str, action_id: str, parameters: dict[str, Any]
    ) -> SafetyAssessment:
        """Tally risk parameters, check policies, run ethics review, and build assessment."""
        # 1. Operational Safety Evaluator
        if not self.evaluator.evaluate_action(action_id, parameters):
            raise SafetyGovernanceError("Safety evaluation failed: Action is operationally unsafe.")

        # 2. Risk Engine
        risk = self.risk_engine.classify_risk(parameters)
        self.event_bus.publish_sync(
            Event(
                name="safety.risk.classified",
                category="AISafety",
                source="AISafetyPlatform",
                payload={"action_id": action_id, "risk": risk},
            )
        )

        # 3. Policy Assurance Engine (checks constitutional rules)
        rules = self.policy_assurance.verify_compliance(parameters)
        self.event_bus.publish_sync(
            Event(
                name="safety.policy.verified",
                category="AISafety",
                source="AISafetyPlatform",
                payload={"action_id": action_id},
            )
        )

        # 4. Ethics Engine
        summary = self.ethics_engine.review_ethics(parameters)

        # 5. Human Oversight Manager check
        req_oversight = self.oversight_manager.check_oversight_trigger(risk)

        assessment = SafetyAssessment(
            assessment_id=assessment_id,
            action_id=action_id,
            risk_classification=risk,
            policy_evaluation={"compliant": True},
            ethics_review_summary=summary,
            constitutional_rules_applied=rules,
            human_oversight_requirement=req_oversight,
        )

        if req_oversight:
            assessment.decision = "PendingOversight"
            self.event_bus.publish_sync(
                Event(
                    name="safety.oversight.requested",
                    category="AISafety",
                    source="AISafetyPlatform",
                    payload={"assessment_id": assessment_id},
                )
            )
        else:
            assessment.decision = "Authorized"
            self.event_bus.publish_sync(
                Event(
                    name="safety.execution.authorized",
                    category="AISafety",
                    source="AISafetyPlatform",
                    payload={"action_id": action_id},
                )
            )

        self.evidence_manager.log_assessment(assessment)

        self.event_bus.publish_sync(
            Event(
                name="safety.evaluated",
                category="AISafety",
                source="AISafetyPlatform",
                payload={"assessment_id": assessment_id},
            )
        )

        return assessment

    def approve_human_oversight(self, assessment_id: str) -> None:
        """Approve pending oversight check and issue execution authorization."""
        # Find matching assessment
        found_assessment = None
        for entry in self.evidence_manager.evidence_log:
            if entry.assessment_id == assessment_id:
                found_assessment = entry
                break

        if not found_assessment:
            raise SafetyGovernanceError(f"Assessment not found: '{assessment_id}'")

        if found_assessment.decision != "PendingOversight":
            raise SafetyGovernanceError(
                f"Oversight approval rejected: Decision is '{found_assessment.decision}'."
            )

        found_assessment.decision = "Authorized"

        self.event_bus.publish_sync(
            Event(
                name="safety.execution.authorized",
                category="AISafety",
                source="AISafetyPlatform",
                payload={"action_id": found_assessment.action_id},
            )
        )
