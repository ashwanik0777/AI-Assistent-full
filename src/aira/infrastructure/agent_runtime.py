"""Enterprise Agent Runtime Kernel & Foundation subsystem for AIRA.

Provides agent descriptors, registries, lifecycle transitions, schedulers, and resource budgets.
"""

import time
from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.agent_runtime")


class AgentRuntimeError(Exception):
    """Raised when runtime constraints, invalid states, or policy checks fail."""

    pass


@dataclass
class AgentDescriptor:
    """Consolidated representation defining capabilities, permissions limits, and metadata."""

    agent_id: str
    agent_name: str
    role: str
    version: str
    capabilities: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    supported_tasks: list[str] = field(default_factory=list)
    priority: int = 1
    resource_limits: dict[str, Any] = field(default_factory=dict)
    lifecycle_state: str = "Created"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentRecord:
    """Identity record tracking operational state, timestamps, and owners."""

    agent_id: str
    agent_name: str
    role: str
    version: str
    capabilities: list[str]
    permissions: list[str]
    lifecycle_state: str = "Created"
    health_status: str = "Healthy"
    owner: str = "System"
    creation_timestamp: float = field(default_factory=time.time)
    last_activity_timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentTask:
    """Task item tracked in the runtime scheduler priority queue."""

    task_id: str
    agent_id: str
    priority: int
    status: str = "Pending"
    timeout_seconds: float = 60.0
    retries: int = 0
    max_retries: int = 3
    cancelled: bool = False


@dataclass
class AgentHealthStats:
    """Telemetry tracking reliability, latencies, and budgets consumption."""

    heartbeat: float = field(default_factory=time.time)
    execution_count: int = 0
    failure_count: int = 0
    success_rate: float = 1.0
    average_runtime: float = 0.0
    cpu_budget: int = 100
    memory_budget_mb: int = 512
    current_status: str = "Healthy"


class AgentRegistry:
    """Stores active records and queries capabilities for discovery mapping."""

    def __init__(self) -> None:
        self._records: dict[str, AgentRecord] = {}

    def register_record(self, record: AgentRecord) -> None:
        """Register a unique agent record in registry."""
        if record.agent_id in self._records:
            raise AgentRuntimeError(
                f"Agent Registration failed: Duplicate Agent ID '{record.agent_id}'."
            )
        self._records[record.agent_id] = record

    def register(self, desc: AgentDescriptor) -> None:
        """Helper supporting legacy registration signature."""
        rec = AgentRecord(
            agent_id=desc.agent_id,
            agent_name=desc.agent_name,
            role=desc.role,
            version=desc.version,
            capabilities=desc.capabilities,
            permissions=desc.permissions,
            lifecycle_state=desc.lifecycle_state,
            metadata=desc.metadata,
        )
        self.register_record(rec)

    def lookup(self, agent_id: str) -> AgentRecord | None:
        """Retrieve agent record by unique ID."""
        return self._records.get(agent_id)

    def list_all(self) -> list[AgentRecord]:
        """List all registered agent records."""
        return list(self._records.values())

    def discover_by_capability(self, capability: str) -> list[AgentRecord]:
        """Find agents exposing a given capability support."""
        return [r for r in self._records.values() if capability in r.capabilities]


class LifecycleController:
    """Manages legal agent state transitions and validates lifecycle integrity."""

    def __init__(self) -> None:
        self.transitions = {
            "Created": {"Registered"},
            "Registered": {"Initialized"},
            "Initialized": {"Ready"},
            "Ready": {"Running"},
            "Running": {"Paused", "Completed", "Failed", "Cancelled"},
            "Paused": {"Running", "Cancelled"},
            "Completed": {"Retired", "Archived"},
            "Failed": {"Ready", "Archived"},
            "Cancelled": {"Archived"},
            "Retired": {"Archived"},
            "Archived": set(),
        }

    def transition_state(self, record: Any, target_state: str) -> None:
        """Move agent record state if legally allowed."""
        current = record.lifecycle_state
        allowed = self.transitions.get(current, set())
        if target_state not in allowed:
            raise AgentRuntimeError(
                f"Lifecycle transition rejected: Cannot move agent '{record.agent_id}' "
                f"from '{current}' to '{target_state}'."
            )
        record.lifecycle_state = target_state
        record.last_activity_timestamp = time.time()


class HealthManager:
    """Telemetry tracking heartbeats, success stats, and budget metrics."""

    def __init__(self) -> None:
        self.telemetry: dict[str, AgentHealthStats] = {}

    def initialize_health(self, agent_id: str, cpu: int = 100, memory_mb: int = 512) -> None:
        """Initialize health model configuration parameters."""
        self.telemetry[agent_id] = AgentHealthStats(cpu_budget=cpu, memory_budget_mb=memory_mb)

    def register_heartbeat(self, agent_id: str) -> None:
        """Log active agent heartbeat signal."""
        if agent_id in self.telemetry:
            self.telemetry[agent_id].heartbeat = time.time()

    def record_run(self, agent_id: str, success: bool, duration: float) -> None:
        """Compute execution statistics and update telemetry profiles."""
        stats = self.telemetry.get(agent_id)
        if not stats:
            return

        stats.execution_count += 1
        if not success:
            stats.failure_count += 1

        total_runs = stats.execution_count
        stats.success_rate = (total_runs - stats.failure_count) / total_runs

        # Running average math
        stats.average_runtime = ((stats.average_runtime * (total_runs - 1)) + duration) / total_runs

        if stats.success_rate < 0.8:
            stats.current_status = "Degraded"
        else:
            stats.current_status = "Healthy"


class VersionManager:
    """Verifies semantic version limits and configuration upgrade states."""

    def validate_compatibility(self, version_a: str, version_b: str) -> bool:
        """Simple semver check matching major components."""
        major_a = version_a.split(".")[0]
        major_b = version_b.split(".")[0]
        return major_a == major_b


class AgentCatalog:
    """Categorizes agents into active, disabled, experimental, deprecated levels."""

    def __init__(self) -> None:
        self.categories: dict[str, list[str]] = {
            "Active": [],
            "Disabled": [],
            "Experimental": [],
            "Deprecated": [],
            "Archived": [],
        }

    def assign_category(self, agent_id: str, category: str) -> None:
        """Move agent ID mapping into target category list."""
        if category not in self.categories:
            raise AgentRuntimeError(f"Invalid catalog category: '{category}'.")

        # Evict from existing
        for cat_list in self.categories.values():
            if agent_id in cat_list:
                cat_list.remove(agent_id)

        self.categories[category].append(agent_id)


class SchedulerFoundation:
    """Priority task queue management, tracking execution slots and timeouts."""

    def __init__(self) -> None:
        self.queue: list[AgentTask] = []

    def schedule_task(self, task: AgentTask) -> None:
        """Queue task and sort by priority order desc."""
        self.queue.append(task)
        self.queue.sort(key=lambda t: t.priority, reverse=True)

    def cancel_task(self, task_id: str) -> None:
        """Request cancel on target task element."""
        for t in self.queue:
            if t.task_id == task_id:
                t.cancelled = True
                t.status = "Cancelled"
                break


class PolicyEngine:
    """Validates safety limits, retries, and execution allowances constraints."""

    def validate_execution_policy(self, record: Any, task: AgentTask) -> bool:
        """Confirm agent permission matches task required permissions parameters."""
        return not ("ShellExecution" in task.status and "shell" not in record.permissions)


class ResourceManager:
    """Monitors CPU budget allocations, token counters, and memory thresholds."""

    def __init__(self) -> None:
        self.allocations: dict[str, dict[str, Any]] = {}

    def allocate_resources(self, agent_id: str, limits: dict[str, Any]) -> None:
        """Bind CPU or memory thresholds to agent tracking registry."""
        self.allocations[agent_id] = {
            "cpu_limit": limits.get("cpu", 100),
            "memory_limit_mb": limits.get("memory_mb", 512),
            "tokens_consumed": 0,
        }

    def record_usage(self, agent_id: str, tokens: int) -> None:
        """Increment tokens consumption counts."""
        if agent_id in self.allocations:
            self.allocations[agent_id]["tokens_consumed"] += tokens


class AgentRuntimeKernel:
    """Principal ARK manager orchestrating schedulers, registries, policies and resources."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.agent_registry = AgentRegistry()
        self.lifecycle_manager = LifecycleController()
        self.scheduler = SchedulerFoundation()
        self.policy_engine = PolicyEngine()
        self.resource_manager = ResourceManager()

        # Phase 9.1 platforms additions
        self.health_manager = HealthManager()
        self.version_manager = VersionManager()
        self.agent_catalog = AgentCatalog()

        # Phase 9.2 context platforms additions
        from aira.infrastructure.agent_context import (
            ContextIsolationEngine,
            ContextLeaseManager,
            PermissionFilter,
            SharedContextBridge,
        )

        self.lease_manager = ContextLeaseManager()
        self.isolation_engine = ContextIsolationEngine()
        self.permission_filter = PermissionFilter()
        self.context_bridge = SharedContextBridge()

        # Phase 9.3 communication bus additions
        from aira.infrastructure.agent_messaging import AgentCommunicationBus

        self.communication_bus = AgentCommunicationBus(
            self.config, self.registry, self.event_bus, self.lease_manager
        )

        # Phase 9.4 orchestrator additions
        from aira.infrastructure.agent_orchestration import OrchestrationEngine

        self.orchestrator = OrchestrationEngine(
            self.config, self.registry, self.event_bus, self.agent_registry
        )

        # Phase 9.5 execution engine additions
        from aira.infrastructure.agent_execution import ExecutionRuntimeEngine

        self.execution_engine = ExecutionRuntimeEngine(self.config, self.registry, self.event_bus)

        # Phase 9.6 policy additions
        from aira.infrastructure.agent_policy import PolicyOrchestrator

        self.policy_orchestrator = PolicyOrchestrator(self.config, self.registry, self.event_bus)

        # Phase 9.7 collaboration engine additions
        from aira.infrastructure.agent_collaboration import CollaborationEngine

        self.collaboration_engine = CollaborationEngine(
            self.config, self.registry, self.event_bus, self.agent_registry
        )

        # Phase 9.8 analytics platform additions
        from aira.infrastructure.agent_analytics import AnalyticsOrchestrator

        self.analytics_orchestrator = AnalyticsOrchestrator(
            self.config, self.registry, self.event_bus
        )
        self.event_bus.subscribe("*", self.analytics_orchestrator.process_event)

        # Phase 9.9 security platform additions
        from aira.infrastructure.agent_security import SecurityOrchestrator

        self.security_orchestrator = SecurityOrchestrator(
            self.config, self.registry, self.event_bus
        )

        # Phase 10.0 extension runtime additions
        from aira.infrastructure.extension_runtime import ExtensionRuntime

        self.extension_runtime = ExtensionRuntime(self.config, self.registry, self.event_bus)

        # Phase 10.1 extension SDK additions
        from aira.infrastructure.extension_sdk import SDKManager

        self.sdk_manager = SDKManager(self.config, self.registry, self.event_bus)

        # Phase 10.2 extension package manager additions
        from aira.infrastructure.extension_package import PackageManager

        self.package_manager = PackageManager(self.config, self.registry, self.event_bus)

        # Phase 10.3 extension marketplace additions
        from aira.infrastructure.extension_marketplace import MarketplaceManager

        self.marketplace_manager = MarketplaceManager(self.config, self.registry, self.event_bus)

        # Phase 10.4 agent extension additions
        from aira.infrastructure.agent_extension import AgentExtensionManager

        self.agent_extension_manager = AgentExtensionManager(
            self.config, self.registry, self.event_bus
        )

        # Phase 10.5 knowledge pack platform additions
        from aira.infrastructure.knowledge_pack import KnowledgeRuntime

        self.knowledge_runtime = KnowledgeRuntime(self.config, self.registry, self.event_bus)

        # Phase 10.6 deployment profile platform additions
        from aira.infrastructure.deployment_profile import DeploymentManager

        self.deployment_manager = DeploymentManager(self.config, self.registry, self.event_bus)

        # Phase 10.7 distributed execution additions
        from aira.infrastructure.distributed_execution import DistributedExecutionManager

        self.distributed_execution_manager = DistributedExecutionManager(
            self.config, self.registry, self.event_bus
        )

        # Phase 10.8 telemetry additions
        from aira.infrastructure.platform_telemetry import TelemetryManager

        self.telemetry_manager = TelemetryManager(self.config, self.registry, self.event_bus)

        # Phase 10.9 extension security additions
        from aira.infrastructure.extension_security import ExtensionSecurityManager

        self.extension_security_manager = ExtensionSecurityManager(
            self.config, self.registry, self.event_bus
        )

        # Phase 11.0 learning manager additions
        from aira.infrastructure.adaptive_learning import LearningManager

        self.learning_manager = LearningManager(self.config, self.registry, self.event_bus)

        # Phase 11.1 feedback intelligence additions
        from aira.infrastructure.feedback_intelligence import FeedbackIntelligenceManager

        self.feedback_intelligence_manager = FeedbackIntelligenceManager(
            self.config, self.registry, self.event_bus
        )

        # Phase 11.2 preference additions
        from aira.infrastructure.preference_intelligence import PreferenceManager

        self.preference_manager = PreferenceManager(self.config, self.registry, self.event_bus)

        # Phase 11.3 knowledge evolution additions
        from aira.infrastructure.knowledge_evolution import KnowledgeEvolutionManager

        self.knowledge_evolution_manager = KnowledgeEvolutionManager(
            self.config, self.registry, self.event_bus
        )

        # Phase 11.4 workflow intelligence additions
        from aira.infrastructure.workflow_intelligence import WorkflowIntelligenceManager

        self.workflow_intelligence_manager = WorkflowIntelligenceManager(
            self.config, self.registry, self.event_bus
        )

        # Phase 11.5 capability intelligence additions
        from aira.infrastructure.capability_intelligence import CapabilityIntelligenceManager

        self.capability_intelligence_manager = CapabilityIntelligenceManager(
            self.config, self.registry, self.event_bus
        )

        # Phase 11.6 memory intelligence additions
        from aira.infrastructure.memory_intelligence import MemoryIntelligenceManager

        self.memory_intelligence_manager = MemoryIntelligenceManager(
            self.config, self.registry, self.event_bus
        )

        # Phase 11.7 organizational intelligence additions
        from aira.infrastructure.organizational_intelligence import (
            OrganizationalIntelligenceManager,
        )

        self.organizational_intelligence_manager = OrganizationalIntelligenceManager(
            self.config, self.registry, self.event_bus
        )

        # Phase 11.8 decision intelligence additions
        from aira.infrastructure.decision_intelligence import DecisionIntelligenceManager

        self.decision_intelligence_manager = DecisionIntelligenceManager(
            self.config, self.registry, self.event_bus
        )

        # Phase 11.9 learning governance additions
        from aira.infrastructure.learning_governance import LearningGovernanceManager

        self.learning_governance_manager = LearningGovernanceManager(
            self.config, self.registry, self.event_bus
        )

        # Phase 12.0 global execution fabric additions
        from aira.infrastructure.global_execution_fabric import GlobalExecutionFabric

        self.global_execution_fabric = GlobalExecutionFabric(
            self.config, self.registry, self.event_bus
        )

        # Phase 12.1 global resource discovery additions
        from aira.infrastructure.global_resource_discovery import GlobalResourceDiscoveryManager

        self.global_resource_discovery_manager = GlobalResourceDiscoveryManager(
            self.config, self.registry, self.event_bus
        )

        # Phase 12.2 intelligent scheduling additions
        from aira.infrastructure.intelligent_scheduling import IntelligentSchedulingManager

        self.intelligent_scheduling_manager = IntelligentSchedulingManager(
            self.config, self.registry, self.event_bus
        )

        # Phase 12.3 federated identity additions
        from aira.infrastructure.federated_identity import FederatedIdentityManager

        self.federated_identity_manager = FederatedIdentityManager(
            self.config, self.registry, self.event_bus
        )

        # Phase 12.4 distributed memory additions
        from aira.infrastructure.distributed_memory import DistributedMemoryFabric

        self.distributed_memory_fabric = DistributedMemoryFabric(
            self.config, self.registry, self.event_bus
        )

        # Phase 12.5 global knowledge distribution additions
        from aira.infrastructure.global_knowledge_distribution import (
            GlobalKnowledgeDistributionManager,
        )

        self.global_knowledge_distribution_manager = GlobalKnowledgeDistributionManager(
            self.config, self.registry, self.event_bus
        )

        # Phase 12.6 edge runtime additions
        from aira.infrastructure.edge_runtime import EdgeRuntimeManager

        self.edge_runtime_manager = EdgeRuntimeManager(self.config, self.registry, self.event_bus)

        # Phase 12.7 disaster recovery additions
        from aira.infrastructure.disaster_recovery import DisasterRecoveryManager

        self.disaster_recovery_manager = DisasterRecoveryManager(
            self.config, self.registry, self.event_bus
        )

        # Phase 12.8 capacity intelligence additions
        from aira.infrastructure.capacity_intelligence import CapacityRecommendationManager

        self.capacity_recommendation_manager = CapacityRecommendationManager(
            self.config, self.registry, self.event_bus
        )

        # Phase 12.9 mission control additions
        from aira.infrastructure.mission_control import MissionControlManager

        self.mission_control_manager = MissionControlManager(
            self.config, self.registry, self.event_bus
        )

        # Phase 13.0 autonomous society additions
        from aira.infrastructure.autonomous_society import SocietyCoordinator

        self.autonomous_society_manager = SocietyCoordinator(
            self.config, self.registry, self.event_bus
        )

        # Phase 13.1 agent identity additions
        from aira.infrastructure.agent_identity import AgentIdentityPlatform

        self.agent_identity_platform = AgentIdentityPlatform(
            self.config, self.registry, self.event_bus
        )

        # Phase 13.2 multi agent communication additions
        from aira.infrastructure.multi_agent_communication import MultiAgentCommunicationPlatform

        self.multi_agent_communication_platform = MultiAgentCommunicationPlatform(
            self.config, self.registry, self.event_bus
        )

        # Phase 13.3 task marketplace additions
        from aira.infrastructure.task_marketplace import TaskMarketplacePlatform

        self.task_marketplace_platform = TaskMarketplacePlatform(
            self.config, self.registry, self.event_bus
        )

        # Phase 13.4 knowledge economy additions
        from aira.infrastructure.knowledge_economy import KnowledgeEconomyPlatform

        self.knowledge_economy_platform = KnowledgeEconomyPlatform(
            self.config, self.registry, self.event_bus
        )

        # Phase 13.5 autonomous planning additions
        from aira.infrastructure.autonomous_planning import AutonomousPlanningPlatform

        self.autonomous_planning_platform = AutonomousPlanningPlatform(
            self.config, self.registry, self.event_bus
        )

        # Phase 13.6 decision intelligence additions
        from aira.infrastructure.collective_decision import DecisionIntelligencePlatform

        self.decision_intelligence_platform = DecisionIntelligencePlatform(
            self.config, self.registry, self.event_bus
        )

        # Phase 13.7 resource governance additions
        from aira.infrastructure.resource_governance import ResourceGovernancePlatform

        self.resource_governance_platform = ResourceGovernancePlatform(
            self.config, self.registry, self.event_bus
        )

        # Phase 13.8 ai safety additions
        from aira.infrastructure.ai_safety import AISafetyPlatform

        self.ai_safety_platform = AISafetyPlatform()
        self.ai_safety_platform.set_dependencies(self.config, self.registry, self.event_bus)

        # Phase 13.9 sandbox simulation additions
        from aira.infrastructure.sandbox_simulation import SandboxSimulationPlatform

        self.sandbox_simulation_platform = SandboxSimulationPlatform(
            self.config, self.registry, self.event_bus
        )

        # Phase 14.0 developer platform additions
        from aira.infrastructure.developer_platform import DeveloperPlatform

        self.developer_platform = DeveloperPlatform(self.config, self.registry, self.event_bus)

        # Phase 14.1 sdk generation additions
        from aira.infrastructure.sdk_generation import MultiLanguageSdkPlatform

        self.sdk_generation_platform = MultiLanguageSdkPlatform(
            self.config, self.registry, self.event_bus
        )

        # Phase 14.2 plugin additions
        from aira.infrastructure.plugin_platform import PluginPlatform

        self.plugin_platform = PluginPlatform(self.config, self.registry, self.event_bus)

        # Phase 14.3 application framework additions
        from aira.infrastructure.ai_application_platform import AiApplicationPlatform

        self.ai_application_platform = AiApplicationPlatform(
            self.config, self.registry, self.event_bus
        )

        # Phase 14.4 workflow studio additions
        from aira.infrastructure.workflow_studio import WorkflowStudioPlatform

        self.workflow_studio_platform = WorkflowStudioPlatform(
            self.config, self.registry, self.event_bus
        )

        # Phase 14.5 solution builder additions
        from aira.infrastructure.solution_builder import SolutionBuilderPlatform

        self.solution_builder_platform = SolutionBuilderPlatform(
            self.config, self.registry, self.event_bus
        )

        # Phase 14.6 marketplace additions
        from aira.infrastructure.marketplace_platform import MarketplacePlatform

        self.marketplace_platform = MarketplacePlatform(self.config, self.registry, self.event_bus)

        # Phase 14.7 developer workbench additions
        from aira.infrastructure.developer_workbench import DeveloperWorkbenchPlatform

        self.developer_workbench_platform = DeveloperWorkbenchPlatform(
            self.config, self.registry, self.event_bus
        )

        # Phase 14.8 developer experience additions
        from aira.infrastructure.developer_dx import DeveloperDxPlatform

        self.developer_dx_platform = DeveloperDxPlatform(self.config, self.registry, self.event_bus)

        # Phase 14.9 community ecosystem additions
        from aira.infrastructure.community_ecosystem import CommunityEcosystemPlatform

        self.community_ecosystem_platform = CommunityEcosystemPlatform(
            self.config, self.registry, self.event_bus
        )

        # Phase 15.0 global control plane additions
        from aira.infrastructure.federated_runtime import GlobalControlPlane

        self.global_control_plane = GlobalControlPlane(self.config, self.registry, self.event_bus)

        # Phase 15.1 global routing additions
        from aira.infrastructure.global_routing import GlobalRoutingGateway

        self.global_routing_gateway = GlobalRoutingGateway(
            self.config, self.registry, self.event_bus
        )

        # Phase 15.2 tenant federation additions
        from aira.infrastructure.tenant_federation import TenantFederationPlatform

        self.tenant_federation_platform = TenantFederationPlatform(
            self.config, self.registry, self.event_bus
        )

        # Phase 15.3 knowledge federation additions
        from aira.infrastructure.knowledge_federation import KnowledgeExchangePlatform

        self.knowledge_exchange_platform = KnowledgeExchangePlatform(
            self.config, self.registry, self.event_bus
        )

        # Phase 15.4 mission federation additions
        from aira.infrastructure.mission_federation import MissionFederationPlatform

        self.mission_federation_platform = MissionFederationPlatform(
            self.config, self.registry, self.event_bus
        )

        # Phase 15.5 sovereign governance additions
        from aira.infrastructure.sovereign_governance import SovereignGovernancePlatform

        self.sovereign_governance_platform = SovereignGovernancePlatform(
            self.config, self.registry, self.event_bus
        )

        # Phase 15.6 mission control additions
        from aira.infrastructure.mission_control import MissionControlPlatform

        self.mission_control_platform = MissionControlPlatform(
            self.config, self.registry, self.event_bus
        )

        # Phase 15.7 federated resilience additions
        from aira.infrastructure.federated_resilience import FederatedResiliencePlatform

        self.federated_resilience_platform = FederatedResiliencePlatform(
            self.config, self.registry, self.event_bus
        )

        # Phase 15.8 compliance governance additions
        from aira.infrastructure.compliance_governance import ComplianceGovernancePlatform

        self.compliance_governance_platform = ComplianceGovernancePlatform(
            self.config, self.registry, self.event_bus
        )

        # Phase 15.9 production readiness additions
        from aira.infrastructure.production_readiness import ProductionReadinessPlatform

        self.production_readiness_platform = ProductionReadinessPlatform(
            self.config, self.registry, self.event_bus
        )

    def register_agent_record(self, record: AgentRecord) -> None:
        """Register record, allocate resources, assign to catalog, and notify events."""
        if not record.agent_id or not record.agent_name:
            raise AgentRuntimeError("Agent registration failed: Records must have unique IDs.")

        self.agent_registry.register_record(record)
        self.lifecycle_manager.transition_state(record, "Registered")

        cpu = 100
        mem = 512
        if hasattr(record, "resource_limits") and record.resource_limits:
            cpu = record.resource_limits.get("cpu", 100)
            mem = record.resource_limits.get("memory_mb", 512)
        self.health_manager.initialize_health(record.agent_id, cpu=cpu, memory_mb=mem)
        self.agent_catalog.assign_category(record.agent_id, "Active")

        self.event_bus.publish_sync(
            Event(
                name="agent.registered",
                category="Runtime",
                source="AgentRuntime",
                payload={"agent_id": record.agent_id, "role": record.role},
            )
        )
        self.event_bus.publish_sync(
            Event(
                name="agent.catalog_updated",
                category="Runtime",
                source="AgentRuntime",
                payload={"agent_id": record.agent_id, "category": "Active"},
            )
        )

    def register_agent(self, desc: AgentDescriptor) -> None:
        """Helper supporting legacy registration signature."""
        rec = AgentRecord(
            agent_id=desc.agent_id,
            agent_name=desc.agent_name,
            role=desc.role,
            version=desc.version,
            capabilities=desc.capabilities,
            permissions=desc.permissions,
            lifecycle_state=desc.lifecycle_state,
            metadata=desc.metadata,
        )
        self.register_agent_record(rec)

    def initialize_agent(self, agent_id: str) -> None:
        """Initialize agent context and move status to Ready."""
        record = self.agent_registry.lookup(agent_id)
        if not record:
            raise AgentRuntimeError(f"Initialization failed: Agent ID '{agent_id}' not found.")

        self.lifecycle_manager.transition_state(record, "Initialized")
        self.event_bus.publish_sync(
            Event(
                name="agent.initialized",
                category="Runtime",
                source="AgentRuntime",
                payload={"agent_id": agent_id},
            )
        )

        self.lifecycle_manager.transition_state(record, "Ready")
        self.event_bus.publish_sync(
            Event(
                name="runtime.health_updated",
                category="Runtime",
                source="AgentRuntime",
                payload={"agent_id": agent_id, "state": "Ready"},
            )
        )

    def update_agent_version(self, agent_id: str, new_version: str) -> None:
        """Validate and apply version changes, triggering event notification."""
        record = self.agent_registry.lookup(agent_id)
        if not record:
            raise AgentRuntimeError(f"Version update failed: Agent ID '{agent_id}' not found.")

        if not self.version_manager.validate_compatibility(record.version, new_version):
            raise AgentRuntimeError(
                f"Version conflict: Cannot upgrade agent '{agent_id}' from version "
                f"'{record.version}' to incompatible version '{new_version}'."
            )

        old_version = record.version
        record.version = new_version
        self.event_bus.publish_sync(
            Event(
                name="agent.version_updated",
                category="Runtime",
                source="AgentRuntime",
                payload={
                    "agent_id": agent_id,
                    "old_version": old_version,
                    "new_version": new_version,
                },
            )
        )

    def run_agent_task(self, agent_id: str, task: AgentTask) -> None:
        """Confirm execution policies and execute targeted transition task alerts."""
        record = self.agent_registry.lookup(agent_id)
        if not record:
            raise AgentRuntimeError(f"Task run failed: Agent ID '{agent_id}' not found.")

        if not self.policy_engine.validate_execution_policy(record, task):
            self.event_bus.publish_sync(
                Event(
                    name="agent.failed",
                    category="Runtime",
                    source="AgentRuntime",
                    payload={"agent_id": agent_id, "reason": "Policy violation"},
                )
            )
            raise AgentRuntimeError(
                f"Policy check failed: Agent '{agent_id}' lacks permission for task."
            )

        self.lifecycle_manager.transition_state(record, "Running")
        self.event_bus.publish_sync(
            Event(
                name="agent.started",
                category="Runtime",
                source="AgentRuntime",
                payload={"agent_id": agent_id, "task_id": task.task_id},
            )
        )

        # Track health stats on execution runs
        t_start = time.time()
        success = True
        try:
            task.status = "Completed"
        except Exception:
            success = False
            task.status = "Failed"

        duration = time.time() - t_start
        self.health_manager.record_run(agent_id, success, duration)

        target_state = "Completed" if success else "Failed"
        self.lifecycle_manager.transition_state(record, target_state)

        event_name = "agent.completed" if success else "agent.failed"
        self.event_bus.publish_sync(
            Event(
                name=event_name,
                category="Runtime",
                source="AgentRuntime",
                payload={"agent_id": agent_id, "task_id": task.task_id},
            )
        )

    def request_context_lease(
        self, agent_id: str, scope: str, permissions: list[str], duration: float, reason: str
    ) -> Any:
        """Grant a ContextLease to target agent and publish event."""
        lease_id = f"lease_{agent_id}_{int(time.time())}"
        lease = self.lease_manager.grant_lease(
            lease_id=lease_id,
            agent_id=agent_id,
            scope=scope,
            permissions=permissions,
            duration=duration,
            reason=reason,
        )
        self.event_bus.publish_sync(
            Event(
                name="lease.granted",
                category="Security",
                source="AgentRuntime",
                payload={"lease_id": lease_id, "agent_id": agent_id},
            )
        )
        return lease

    def renew_context_lease(self, lease_id: str, additional_duration: float) -> None:
        """Extend time lease and trigger renew event."""
        self.lease_manager.renew_lease(lease_id, additional_duration)
        self.event_bus.publish_sync(
            Event(
                name="lease.renewed",
                category="Security",
                source="AgentRuntime",
                payload={"lease_id": lease_id},
            )
        )

    def revoke_context_lease(self, lease_id: str) -> None:
        """Invalidate lease credentials immediately and notify event bus."""
        self.lease_manager.revoke_lease(lease_id)
        self.event_bus.publish_sync(
            Event(
                name="lease.revoked",
                category="Security",
                source="AgentRuntime",
                payload={"lease_id": lease_id},
            )
        )

    def create_agent_sandbox(self, sandbox_id: str, agent_id: str) -> Any:
        """Construct isolated memory sandbox and publish event."""
        sandbox = self.isolation_engine.create_sandbox(sandbox_id, agent_id)
        self.event_bus.publish_sync(
            Event(
                name="sandbox.created",
                category="Security",
                source="AgentRuntime",
                payload={"sandbox_id": sandbox_id, "agent_id": agent_id},
            )
        )
        return sandbox

    def share_agent_context(
        self, source_sandbox_id: str, target_sandbox_id: str, keys: list[str], lease_id: str
    ) -> dict[str, Any]:
        """Validate lease permissions, transfer summary via bridge, publish event."""
        from aira.infrastructure.agent_context import AgentContextError

        if not self.lease_manager.validate_lease(lease_id):
            raise AgentContextError(f"Access Denied: Lease '{lease_id}' is invalid or expired.")

        lease = self.lease_manager.leases[lease_id]
        is_authorized = self.permission_filter.verify_action(
            lease, "Share"
        ) or self.permission_filter.verify_action(lease, "Export")
        if not is_authorized:
            raise AgentContextError(
                f"Access Denied: Lease '{lease_id}' lacks Share/Export permission."
            )

        src = self.isolation_engine.sandboxes.get(source_sandbox_id)
        tgt = self.isolation_engine.sandboxes.get(target_sandbox_id)
        if not src or not tgt:
            raise AgentContextError("Context Transfer failed: Sandbox reference not found.")

        summary = self.context_bridge.transfer_summary(src, tgt, keys)
        self.event_bus.publish_sync(
            Event(
                name="context.shared",
                category="Security",
                source="AgentRuntime",
                payload={
                    "lease_id": lease_id,
                    "source_sandbox": source_sandbox_id,
                    "target_sandbox": target_sandbox_id,
                },
            )
        )
        return summary

    def expire_context_leases(self) -> None:
        """Check expirations of active leases, trigger events for any expired."""
        for lease_id, lease in list(self.lease_manager.leases.items()):
            if time.time() > lease.expiration_time:
                self.event_bus.publish_sync(
                    Event(
                        name="context.expired",
                        category="Security",
                        source="AgentRuntime",
                        payload={"lease_id": lease_id, "agent_id": lease.agent_id},
                    )
                )
