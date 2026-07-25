"""Enterprise Resource Governance, Budget Intelligence & Autonomous Allocation Platform for AIRA.

Provides allocation engines, budget managers, quota managers, and consumption monitors.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.resource_governance")


class ResourceAllocationError(Exception):
    """Base exception raised for budget violations or quota exhaustions."""

    pass


@dataclass
class ResourceAllocation:
    """Allocation contract defining budget values, quota allowances, and approval state statuses."""

    allocation_id: str
    requester: str
    resource_class: str  # CPU, GPU, Memory, Storage, KnowledgeQuotas, APIQuotas
    budget: float
    quota: float
    approval_status: str = "Requested"  # Requested, Approved, Rejected, Active, Terminated
    consumption_limits: dict[str, Any] = field(default_factory=dict)
    policy_references: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    version: int = 1


class AllocationEngine:
    """Authorizes resource requests according to governance policy lists alignment."""

    def authorize_request(self, requester: str, resource_class: str) -> bool:
        """Verify safety bounds coordinates allocation access permission."""
        # Policy rule: prevent unauthorized resource types (e.g. invalid ACCELERATOR)
        allowed = {"CPU", "GPU", "Memory", "Storage", "KnowledgeQuotas", "APIQuotas"}
        return resource_class in allowed


class BudgetManager:
    """Enforces spending cost limit envelopes constraints."""

    def __init__(self) -> None:
        self.agent_budgets: dict[str, float] = {}

    def reserve_budget(self, agent_id: str, amount: float) -> None:
        """Reserve spending budget and block if limit is exceeded."""
        current = self.agent_budgets.get(agent_id, 1000.0)  # default budget
        if amount > current:
            raise ResourceAllocationError(
                f"Budget exceeded: Requesting cost '{amount}' exceeds budget limit '{current}'."
            )
        self.agent_budgets[agent_id] = current - amount


class QuotaManager:
    """Manages usages limits, elastic burst allowances, and capacities details."""

    def __init__(self) -> None:
        self.quota_capacity: dict[str, float] = {}

    def reserve_quota(self, resource_class: str, amount: float) -> None:
        """Reserve quota allowance capacity."""
        capacity = self.quota_capacity.get(resource_class, 100.0)  # default capacity limit
        if amount > capacity:
            raise ResourceAllocationError(
                f"Quota exhaustion: Requesting '{amount}' "
                f"units exceeds limit capacity '{capacity}'."
            )
        self.quota_capacity[resource_class] = capacity - amount


class ConsumptionMonitor:
    """Audits actual usage records and flags policy violations."""

    def record_usage(self, allocation: ResourceAllocation, actual_units: float) -> None:
        """Update actual utilization and detect usage spikes violations."""
        if actual_units > allocation.quota:
            raise ResourceAllocationError(
                f"Quota violation: Actual usage '{actual_units}' "
                f"exceeded quota allowance '{allocation.quota}'."
            )


class ResourceAuditManager:
    """Logs complete permanent usage traces histories."""

    def __init__(self) -> None:
        self.audit_log: list[dict[str, Any]] = []

    def audit_allocation(self, allocation: ResourceAllocation) -> None:
        """Log allocation state to history registry."""
        self.audit_log.append(
            {
                "allocation_id": allocation.allocation_id,
                "requester": allocation.requester,
                "resource": allocation.resource_class,
                "status": allocation.approval_status,
            }
        )


class ResourceGovernancePlatform:
    """Coordinating manager resolving resource requests, quotas reservations, and audits."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.allocation_engine = AllocationEngine()
        self.budget_manager = BudgetManager()
        self.quota_manager = QuotaManager()
        self.consumption_monitor = ConsumptionMonitor()
        self.audit_manager = ResourceAuditManager()

        self.allocations: dict[str, ResourceAllocation] = {}

    def request_resource_allocation(
        self, alloc_id: str, requester: str, resource_class: str, budget: float, quota: float
    ) -> ResourceAllocation:
        """Validate requests format, check budget levels, reserve quotas, and publish events."""
        self.event_bus.publish_sync(
            Event(
                name="resource.allocation.requested",
                category="ResourceGovernance",
                source="ResourceGovernancePlatform",
                payload={"allocation_id": alloc_id},
            )
        )

        # 1. Authorize
        if not self.allocation_engine.authorize_request(requester, resource_class):
            raise ResourceAllocationError(f"Authorization failed for resource '{resource_class}'.")

        # 2. Budget check
        self.budget_manager.reserve_budget(requester, budget)
        self.event_bus.publish_sync(
            Event(
                name="resource.budget.updated",
                category="ResourceGovernance",
                source="ResourceGovernancePlatform",
                payload={"requester": requester},
            )
        )

        # 3. Quota check
        self.quota_manager.reserve_quota(resource_class, quota)
        self.event_bus.publish_sync(
            Event(
                name="resource.quota.changed",
                category="ResourceGovernance",
                source="ResourceGovernancePlatform",
                payload={"resource_class": resource_class},
            )
        )

        # Create allocation
        alloc = ResourceAllocation(
            allocation_id=alloc_id,
            requester=requester,
            resource_class=resource_class,
            budget=budget,
            quota=quota,
            approval_status="Approved",
        )

        self.allocations[alloc_id] = alloc
        self.audit_manager.audit_allocation(alloc)

        self.event_bus.publish_sync(
            Event(
                name="resource.allocation.approved",
                category="ResourceGovernance",
                source="ResourceGovernancePlatform",
                payload={"allocation_id": alloc_id},
            )
        )

        return alloc

    def record_usage_units(self, alloc_id: str, units: float) -> None:
        """Forward monitoring values, track violations, and publish events."""
        alloc = self.allocations.get(alloc_id)
        if not alloc:
            raise ResourceAllocationError(f"Allocation not found: '{alloc_id}'")

        try:
            self.consumption_monitor.record_usage(alloc, units)
        except ResourceAllocationError as e:
            # Terminate allocation status on violation
            alloc.approval_status = "Terminated"
            self.audit_manager.audit_allocation(alloc)
            raise e

        self.event_bus.publish_sync(
            Event(
                name="resource.consumption.recorded",
                category="ResourceGovernance",
                source="ResourceGovernancePlatform",
                payload={"allocation_id": alloc_id, "usage": units},
            )
        )
