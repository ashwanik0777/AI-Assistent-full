"""Enterprise Agent Context, Memory Isolation & Context Lease Platform for AIRA.

Provides isolated sandboxes, time-bound leases, access filters, and shared context bridges.
"""

import time
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger("aira.agent_context")


class AgentContextError(Exception):
    """Raised when sandbox isolation limits or expired leases are violated."""

    pass


@dataclass
class ContextLease:
    """Credential token detailing bounds, scopes and expiration limits of memory access."""

    lease_id: str
    agent_id: str
    granted_scope: str
    permissions: list[str]
    allowed_resources: list[str]
    expiration_time: float
    context_snapshot_ref: str
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)
    version: str = "1.0.0"


@dataclass
class AgentContextSandbox:
    """Isolated local store protecting local agent memory allocations."""

    sandbox_id: str
    agent_id: str
    working_memory: dict[str, Any] = field(default_factory=dict)
    scratch_space: dict[str, Any] = field(default_factory=dict)
    task_cache: dict[str, Any] = field(default_factory=dict)
    lifecycle_state: str = "Created"
    metadata: dict[str, Any] = field(default_factory=dict)


class ContextLeaseManager:
    """Issues, checks, revokes and validates ContextLease credentials."""

    def __init__(self) -> None:
        self.leases: dict[str, ContextLease] = {}

    def grant_lease(
        self,
        lease_id: str,
        agent_id: str,
        scope: str,
        permissions: list[str],
        duration: float,
        reason: str,
    ) -> ContextLease:
        """Issue a new lease valid until expiration timestamp."""
        lease = ContextLease(
            lease_id=lease_id,
            agent_id=agent_id,
            granted_scope=scope,
            permissions=permissions,
            allowed_resources=[],
            expiration_time=time.time() + duration,
            context_snapshot_ref=f"snap_{lease_id}",
            reason=reason,
        )
        self.leases[lease_id] = lease
        return lease

    def validate_lease(self, lease_id: str) -> bool:
        """Confirm lease exists and is not expired."""
        lease = self.leases.get(lease_id)
        if not lease:
            return False
        return not (time.time() > lease.expiration_time)

    def renew_lease(self, lease_id: str, additional_duration: float) -> None:
        """Extend expiration timestamp of lease."""
        lease = self.leases.get(lease_id)
        if not lease:
            raise AgentContextError(f"Lease extension failed: Lease ID '{lease_id}' not found.")
        lease.expiration_time = time.time() + additional_duration

    def revoke_lease(self, lease_id: str) -> None:
        """Invalidate lease immediately."""
        if lease_id in self.leases:
            # Set expiration to epoch
            self.leases[lease_id].expiration_time = 0.0


class ContextIsolationEngine:
    """Spawns sandboxes and coordinates isolation layers."""

    def __init__(self) -> None:
        self.sandboxes: dict[str, AgentContextSandbox] = {}

    def create_sandbox(self, sandbox_id: str, agent_id: str) -> AgentContextSandbox:
        """Construct an isolated memory sandbox for target agent."""
        sandbox = AgentContextSandbox(
            sandbox_id=sandbox_id, agent_id=agent_id, lifecycle_state="Ready"
        )
        self.sandboxes[sandbox_id] = sandbox
        return sandbox

    def destroy_sandbox(self, sandbox_id: str) -> None:
        """Evict sandbox reference from isolation layer."""
        if sandbox_id in self.sandboxes:
            self.sandboxes[sandbox_id].lifecycle_state = "Destroyed"
            del self.sandboxes[sandbox_id]


class PermissionFilter:
    """Verifies action request parameters against lease permissions allowances."""

    def verify_action(self, lease: ContextLease, action: str) -> bool:
        """Match requested action with granted lease permissions tags."""
        # Actions: Read, Write, Append, Share, Export
        return action in lease.permissions


class SharedContextBridge:
    """Governs safe context transitions, filtering output summaries and references."""

    def transfer_summary(
        self,
        source_sandbox: AgentContextSandbox,
        target_sandbox: AgentContextSandbox,
        keys: list[str],
    ) -> dict[str, Any]:
        """Extract summary projection from source sandbox to transfer to target."""
        summary = {}
        for k in keys:
            if k in source_sandbox.working_memory:
                summary[k] = source_sandbox.working_memory[k]
        target_sandbox.working_memory.update(summary)
        return summary
