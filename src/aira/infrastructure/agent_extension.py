"""Enterprise Agent Extension SDK, Runtime Contracts & Autonomous Agent Framework for AIRA.

Provides capability profiles, lifecycle contracts, and sandboxes.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.agent_extension")


class AgentExtensionSDKError(Exception):
    """Base exception raised for agent contracts, capability verification, or sandbox violations."""

    pass


@dataclass
class AgentCapabilityProfile:
    """Declared capabilities, permissions bounds, and task mappings profile."""

    agent_id: str
    role: str
    supported_tasks: list[str]
    capabilities: list[str]
    permissions: list[str]
    compatibility: str = ">=0.9.0"
    trust_level: float = 5.0
    metadata: dict[str, Any] = field(default_factory=dict)


class AgentContract(ABC):
    """Lifecycle contract that all extensible custom agents must implement."""

    def __init__(self, profile: AgentCapabilityProfile) -> None:
        self.profile = profile
        self.status = "Created"

    @abstractmethod
    def initialize(self) -> None:
        """Allocate dependencies and setup channels."""
        pass

    @abstractmethod
    def execute(self, task: dict[str, Any]) -> dict[str, Any]:
        """Perform autonomous execution of the assigned intent."""
        pass

    @abstractmethod
    def pause(self) -> None:
        """Pause agent execution."""
        pass

    @abstractmethod
    def resume(self) -> None:
        """Resume paused agent."""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Stop agent and clean registers."""
        pass

    @abstractmethod
    def cleanup(self) -> None:
        """Evict memory caches."""
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Return True if the agent is healthy."""
        pass


class RuntimeValidator:
    """Verifies agent capability profiles and checks compatibility requirements."""

    def __init__(self, platform_version: str = "0.9.0") -> None:
        self.platform_version = platform_version
        self.allowed_permissions = {
            "Memory",
            "Perception",
            "Browser",
            "Desktop",
            "Filesystem",
            "Workflow",
            "Capabilities",
            "Extensions",
            "Networking",
        }

    def validate_profile(self, profile: AgentCapabilityProfile) -> None:
        """Validate platform compatibility and permissions allowlist bounds."""
        # 1. Compatibility check
        req = profile.compatibility.replace(">=", "").strip()
        p_parts = [int(x) for x in self.platform_version.split(".")]
        r_parts = [int(x) for x in req.split(".")]
        if p_parts < r_parts:
            raise AgentExtensionSDKError(
                f"Validation failed: Incompatible version bounds. "
                f"Platform: '{self.platform_version}' vs Agent requires '{profile.compatibility}'."
            )

        # 2. Permissions check
        for perm in profile.permissions:
            if perm not in self.allowed_permissions:
                raise AgentExtensionSDKError(
                    f"Validation failed: Requesting unauthorized permission '{perm}'."
                )


class AgentSandbox:
    """Allocates isolated context memory registries for custom agents."""

    def __init__(self) -> None:
        self.workspaces: dict[str, dict[str, Any]] = {}

    def start_sandbox(self, agent_id: str) -> None:
        """Setup isolated variables map."""
        self.workspaces[agent_id] = {"agent_id": agent_id, "variables": {}, "status": "Isolated"}

    def cleanup_sandbox(self, agent_id: str) -> None:
        """Remove sandbox variables maps."""
        self.workspaces.pop(agent_id, None)


class AgentTemplateGenerator:
    """Generates code templates matching specified roles."""

    def generate_agent_template(self, role: str, agent_id: str) -> dict[str, str]:
        """Return dictionary containing manifest descriptor and code files stubs."""
        return {
            "profile.yaml": (
                f"agent_id: {agent_id.lower()}\n"
                f"role: {role}\n"
                "supported_tasks: [task_process_metrics]\n"
                "capabilities: [cap_process]\n"
                "permissions: [Memory, Filesystem]\n"
                "compatibility: '>=0.9.0'\n"
            ),
            "agent.py": (
                "from aira.infrastructure.agent_extension import AgentContract\n\n"
                f"class Custom{role}Agent(AgentContract):\n"
                "    def initialize(self) -> None:\n"
                "        self.status = 'Ready'\n"
                "    def execute(self, task) -> dict:\n"
                "        return {'status': 'Completed'}\n"
                "    def pause(self) -> None: pass\n"
                "    def resume(self) -> None: pass\n"
                "    def stop(self) -> None: pass\n"
                "    def cleanup(self) -> None: pass\n"
                "    def health_check(self) -> bool: return True\n"
            ),
        }


class AgentExtensionManager:
    """Coordinating manager verifying profiles, initializing sandboxes, and publishing events."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.validator = RuntimeValidator()
        self.sandbox = AgentSandbox()
        self.generator = AgentTemplateGenerator()

        self.installed_agents: dict[str, AgentCapabilityProfile] = {}

    def install_agent_extension(self, profile: AgentCapabilityProfile) -> None:
        """Validate profile structures, setup sandboxes, and publish installation events."""
        try:
            self.validator.validate_profile(profile)
        except AgentExtensionSDKError as e:
            self.event_bus.publish_sync(
                Event(
                    name="agent.validation_failed",
                    category="AgentExtension",
                    source="AgentExtensionManager",
                    payload={"agent_id": profile.agent_id, "reason": str(e)},
                )
            )
            raise

        self.installed_agents[profile.agent_id] = profile
        self.event_bus.publish_sync(
            Event(
                name="agent.validated",
                category="AgentExtension",
                source="AgentExtensionManager",
                payload={"agent_id": profile.agent_id},
            )
        )

        self.event_bus.publish_sync(
            Event(
                name="agent.installed",
                category="AgentExtension",
                source="AgentExtensionManager",
                payload={"agent_id": profile.agent_id, "role": profile.role},
            )
        )

    def enable_agent_extension(self, agent_id: str) -> None:
        """Launch sandboxed variables workspace and publish enabled event."""
        if agent_id not in self.installed_agents:
            raise AgentExtensionSDKError(f"Operation failed: Agent '{agent_id}' is not installed.")

        self.sandbox.start_sandbox(agent_id)

        self.event_bus.publish_sync(
            Event(
                name="agent.enabled",
                category="AgentExtension",
                source="AgentExtensionManager",
                payload={"agent_id": agent_id},
            )
        )

    def disable_agent_extension(self, agent_id: str) -> None:
        """Teardown sandboxed workspaces and publish disabled event."""
        if agent_id not in self.installed_agents:
            raise AgentExtensionSDKError(f"Operation failed: Agent '{agent_id}' is not installed.")

        self.sandbox.cleanup_sandbox(agent_id)

        self.event_bus.publish_sync(
            Event(
                name="agent.disabled",
                category="AgentExtension",
                source="AgentExtensionManager",
                payload={"agent_id": agent_id},
            )
        )

    def generate_agent_starter(self, role: str, agent_id: str) -> dict[str, str]:
        """Trigger code generator templates and publish template events."""
        files = self.generator.generate_agent_template(role, agent_id)
        self.event_bus.publish_sync(
            Event(
                name="agent.template_generated",
                category="AgentExtension",
                source="AgentExtensionManager",
                payload={"role": role, "agent_id": agent_id},
            )
        )
        return files
