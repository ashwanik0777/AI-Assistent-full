"""Enterprise Developer Platform Foundation for AIRA.

Provides developer runtimes, public API gateways, contract registries, and api version managers.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.developer_platform")


class DeveloperPlatformError(Exception):
    """Base exception raised for session authentication or API version compatibility failures."""

    pass


@dataclass
class DeveloperSession:
    """Session record defining project scope, versions, permissions, and active status."""

    session_id: str
    developer_identity: str
    project_context: dict[str, Any]
    sdk_version: str
    api_version: str
    permissions: list[str]
    environment: str = "Sandbox"
    active: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
    version: int = 1


class DeveloperRuntime:
    """Tracks developer session status and handles closure lifecycles."""

    def __init__(self) -> None:
        self.sessions: dict[str, DeveloperSession] = {}

    def open_session(self, session: DeveloperSession) -> None:
        """Register developer session."""
        self.sessions[session.session_id] = session

    def close_session(self, session_id: str) -> None:
        """Transition active status flag to false."""
        session = self.sessions.get(session_id)
        if not session:
            raise DeveloperPlatformError(f"Session not found: '{session_id}'")
        session.active = False


class DeveloperContractRegistry:
    """Validates public api contracts parameters."""

    def validate_api_usage(self, endpoint: str, parameters: dict[str, Any]) -> bool:
        """Validate parameter formats against interface contracts."""
        # Policy rule: require payload query parameters
        return not (endpoint == "planning" and "goal" not in parameters)


class ApiVersionManager:
    """Enforces semantic versioning constraints and deprecation alerts."""

    def verify_api_version(self, api_version: str) -> dict[str, Any]:
        """Verify API compatibility and return warnings if deprecated."""
        if api_version == "v1.0":
            return {
                "compatible": True,
                "warning": "API version v1.0 is deprecated. Please upgrade to v1.2.",
                "migration_guidance": "Migrate planning query calls to v1.2.",
            }
        if api_version == "v1.2":
            return {"compatible": True, "warning": None, "migration_guidance": None}
        raise DeveloperPlatformError(
            f"Unsupported API version: '{api_version}'. Supported versions: 'v1.0', 'v1.2'."
        )


class DeveloperAccessManager:
    """Checks session permissions constraints."""

    def authorize_access(self, session: DeveloperSession, required_scope: str) -> None:
        """Verify permission key presence in session scope."""
        if required_scope not in session.permissions:
            raise DeveloperPlatformError(
                f"Permission denied: Missing required scope '{required_scope}'."
            )


class PublicApiGateway:
    """Exposes versioned capabilities endpoints (Workflow, Planning, Observability)."""

    def route_request(self, endpoint: str, parameters: dict[str, Any]) -> dict[str, Any]:
        """Dispatch query and return versioned output data."""
        return {
            "endpoint": endpoint,
            "status": "Success",
            "payload": f"API versioned result for endpoint '{endpoint}'",
        }


class DeveloperPlatform:
    """Coordinating manager resolving developer sessions and version checks."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.runtime = DeveloperRuntime()
        self.gateway = PublicApiGateway()
        self.contract_registry = DeveloperContractRegistry()
        self.version_manager = ApiVersionManager()
        self.access_manager = DeveloperAccessManager()

    def start_developer_session(
        self,
        session_id: str,
        developer_identity: str,
        sdk_version: str,
        api_version: str,
        permissions: list[str],
    ) -> DeveloperSession:
        """Initialize session parameters and publish event signals."""
        session = DeveloperSession(
            session_id=session_id,
            developer_identity=developer_identity,
            project_context={},
            sdk_version=sdk_version,
            api_version=api_version,
            permissions=permissions,
        )
        self.runtime.open_session(session)

        self.event_bus.publish_sync(
            Event(
                name="developer.session.started",
                category="DeveloperPlatform",
                source="DeveloperPlatform",
                payload={"session_id": session_id},
            )
        )

        return session

    def invoke_public_api(
        self, session_id: str, endpoint: str, parameters: dict[str, Any], required_scope: str
    ) -> dict[str, Any]:
        """Validate session, check scope, verify contracts, check version, and invoke API."""
        session = self.runtime.sessions.get(session_id)
        if not session:
            raise DeveloperPlatformError(f"Developer session not found: '{session_id}'")

        if not session.active:
            raise DeveloperPlatformError(f"Developer session is closed: '{session_id}'")

        # 1. Access Check
        self.access_manager.authorize_access(session, required_scope)

        # 2. Version Check
        v_check = self.version_manager.verify_api_version(session.api_version)
        self.event_bus.publish_sync(
            Event(
                name="developer.version.checked",
                category="DeveloperPlatform",
                source="DeveloperPlatform",
                payload={"api_version": session.api_version},
            )
        )

        # 3. Contract Check
        if not self.contract_registry.validate_api_usage(endpoint, parameters):
            raise DeveloperPlatformError(
                f"Contract validation failed for API endpoint '{endpoint}'."
            )

        self.event_bus.publish_sync(
            Event(
                name="developer.contract.validated",
                category="DeveloperPlatform",
                source="DeveloperPlatform",
                payload={"endpoint": endpoint},
            )
        )

        # 4. Invoke
        out = self.gateway.route_request(endpoint, parameters)
        if v_check.get("warning"):
            out["warning"] = v_check["warning"]
            out["migration_guidance"] = v_check["migration_guidance"]

        self.event_bus.publish_sync(
            Event(
                name="developer.api.invoked",
                category="DeveloperPlatform",
                source="DeveloperPlatform",
                payload={"endpoint": endpoint, "session_id": session_id},
            )
        )

        return out

    def close_developer_session(self, session_id: str) -> None:
        """Close active session and publish events."""
        self.runtime.close_session(session_id)

        self.event_bus.publish_sync(
            Event(
                name="developer.session.closed",
                category="DeveloperPlatform",
                source="DeveloperPlatform",
                payload={"session_id": session_id},
            )
        )
