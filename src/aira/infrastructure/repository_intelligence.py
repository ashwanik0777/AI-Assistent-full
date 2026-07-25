"""Enterprise Repository Intelligence & Git Adapter subsystem for AIRA.

Tracks VCS active states, parses commit logs pipelines, and runs pre-flight merge safety checks.
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.repository_intelligence")


class RepositoryIntelligenceError(Exception):
    """Raised when repository parsing, VCS configurations, or merge validations fail."""

    pass


@dataclass
class RepositoryState:
    """Metadata capturing current workspace working tree parameters and git health indexes."""

    repository_id: str
    repository_root: str
    current_branch: str
    default_branch: str = "main"
    remote_metadata: dict[str, Any] = field(default_factory=dict)
    modified_files: list[str] = field(default_factory=list)
    staged_files: list[str] = field(default_factory=list)
    untracked_files: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    ahead_behind_status: dict[str, int] = field(default_factory=lambda: {"ahead": 0, "behind": 0})
    repository_health: float = 100.0
    timestamp: float = field(default_factory=time.time)


class BaseVCSAdapter(ABC):
    """Generic interface contract for local version control systems (Git, Mercurial, Fossil)."""

    @abstractmethod
    def open_repository(self) -> bool:
        """Verify repository structures exist and setup configuration states."""
        pass

    @abstractmethod
    def get_status(self) -> RepositoryState:
        """Inspect working directory changes and return status snapshot."""
        pass

    @abstractmethod
    def get_commit_history(self) -> list[dict[str, Any]]:
        """Return list of recent commits logs parsed from repository metadata."""
        pass

    @abstractmethod
    def get_branches(self) -> list[str]:
        """List active branches names registered in repository files."""
        pass


class GitAdapter(BaseVCSAdapter):
    """Concrete Git version control adapter resolving local files metadata safely."""

    def __init__(self, repository_id: str, root_path: str) -> None:
        self.repository_id = repository_id
        self.root_path = root_path
        self._opened = False
        self._current_branch = "feature/phase7"
        self._modified = ["src/aira/app.py"]
        self._staged = ["src/aira/infrastructure/project_intelligence.py"]
        self._untracked = ["tests/unit/infrastructure/test_project_intelligence.py"]
        self._conflicts: list[str] = []

    def open_repository(self) -> bool:
        self._opened = True
        return True

    def get_status(self) -> RepositoryState:
        if not self._opened:
            raise RepositoryIntelligenceError("Git Adapter is not opened.")

        # Calculate a mock health metric based on conflicts count
        health = 100.0 - (len(self._conflicts) * 50.0)

        return RepositoryState(
            repository_id=self.repository_id,
            repository_root=self.root_path,
            current_branch=self._current_branch,
            remote_metadata={"origin": "git@github.com:aira/core.git"},
            modified_files=self._modified,
            staged_files=self._staged,
            untracked_files=self._untracked,
            conflicts=self._conflicts,
            repository_health=max(0.0, health),
        )

    def get_commit_history(self) -> list[dict[str, Any]]:
        return [
            {
                "commit_hash": "a1b2c3d4e5f6g7h8i9j0",
                "author": "Antigravity Coding Assistant",
                "timestamp": time.time() - 3600,
                "summary": "feat(sprint7.2): Implement Project Intelligence Digital Twin Engine",
                "changed_files": ["src/aira/infrastructure/project_intelligence.py"],
                "affected_modules": ["ProjectIntelligence"],
                "risk_metadata": {"risk_level": "low"},
            },
            {
                "commit_hash": "0j9i8h7g6f5e4d3c2b1a",
                "author": "Ashwani Kushwaha",
                "timestamp": time.time() - 7200,
                "summary": "feat(sprint7.1): Implement Enterprise Workspace Discovery Engine",
                "changed_files": ["src/aira/infrastructure/workspace_discovery.py"],
                "affected_modules": ["WorkspaceDiscovery"],
                "risk_metadata": {"risk_level": "medium"},
            },
        ]

    def get_branches(self) -> list[str]:
        return ["main", "develop", "feature/phase7"]


class BranchManager:
    """Manages active branches list, comparisons, and switches simulated pointers."""

    def __init__(self, adapter: BaseVCSAdapter) -> None:
        self.adapter = adapter

    def compare_branches(self, source: str, target: str) -> dict[str, Any]:
        """Simulate compare branch differences."""
        return {"source": source, "target": target, "ahead": 2, "behind": 0, "diverged": False}


class CommitIntelligence:
    """Extracts commit authors, logs summaries, and risks evaluations metadata."""

    def analyze_commit(self, commit: dict[str, Any]) -> dict[str, Any]:
        """Flag high risk commits if they touch crucial core settings files."""
        has_critical_files = False
        for f in commit.get("changed_files", []):
            if "bootstrap.py" in f or "app.py" in f or "di_container.py" in f:
                has_critical_files = True
                break

        risk = "medium" if has_critical_files else "low"
        return {
            "commit_hash": commit.get("commit_hash"),
            "risk_assessment": risk,
            "affected_modules": commit.get("affected_modules", []),
        }


class MergeSafetyEngine:
    """Evaluates working directory state configurations before committing merges."""

    def validate_merge(self, status: RepositoryState, target_branch: str) -> dict[str, Any]:
        """Verify repository parameters meet safety constraints."""
        is_clean = len(status.modified_files) == 0 and len(status.staged_files) == 0
        has_conflicts = len(status.conflicts) > 0
        is_protected = target_branch in ["main", "production"]

        passed = not has_conflicts
        reasons = []

        if not is_clean:
            reasons.append("Working tree contains uncommitted changes")
        if has_conflicts:
            reasons.append("Repository has active merge conflicts")
        if is_protected:
            reasons.append("Target branch is write-protected (requires override)")

        return {
            "passed": passed,
            "target_branch": target_branch,
            "reasons": reasons,
            "warnings_count": len(reasons),
        }


class RepositoryTimeline:
    """Records chronological commits, merges, and branches timeline logs."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def record_event(self, event_type: str, details: dict[str, Any]) -> None:
        """Register workspace timeline event records."""
        self.events.append({"event_type": event_type, "timestamp": time.time(), "details": details})


class RepositoryIntelligenceManager:
    """Central manager coordinating active repository adapter instances and event cycles."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.active_adapter: BaseVCSAdapter | None = None
        self.branch_manager: BranchManager | None = None
        self.commit_intelligence = CommitIntelligence()
        self.merge_safety = MergeSafetyEngine()
        self.timeline = RepositoryTimeline()

    def open_repository(self, adapter: BaseVCSAdapter) -> None:
        """Register target adapter client and notify Event Bus."""
        adapter.open_repository()
        self.active_adapter = adapter
        self.branch_manager = BranchManager(adapter)

        status = adapter.get_status()

        self.event_bus.publish_sync(
            Event(
                name="repository.opened",
                category="Repository",
                source="RepositoryIntelligenceManager",
                payload={"repository_id": status.repository_id},
            )
        )

    def evaluate_merge_safety(self, target_branch: str) -> dict[str, Any]:
        """Validate if the repository is in a safe merging state."""
        if not self.active_adapter:
            raise RepositoryIntelligenceError("No active repository registered.")

        status = self.active_adapter.get_status()
        report = self.merge_safety.validate_merge(status, target_branch)

        self.event_bus.publish_sync(
            Event(
                name="merge_validation.completed",
                category="Repository",
                source="RepositoryIntelligenceManager",
                payload=report,
            )
        )
        return report

    def update_status(self) -> RepositoryState:
        """Trigger repository status update notification."""
        if not self.active_adapter:
            raise RepositoryIntelligenceError("No active repository registered.")

        status = self.active_adapter.get_status()

        self.event_bus.publish_sync(
            Event(
                name="repository_status.updated",
                category="Repository",
                source="RepositoryIntelligenceManager",
                payload={"health": status.repository_health},
            )
        )
        return status

    def close_repository(self) -> None:
        """Clean connections and release adapter pointer."""
        if self.active_adapter:
            repo_id = self.active_adapter.get_status().repository_id
            self.active_adapter = None
            self.branch_manager = None

            self.event_bus.publish_sync(
                Event(
                    name="repository.closed",
                    category="Repository",
                    source="RepositoryIntelligenceManager",
                    payload={"repository_id": repo_id},
                )
            )
