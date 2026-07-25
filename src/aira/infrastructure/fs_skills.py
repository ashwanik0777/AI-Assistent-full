"""Enterprise Filesystem Skill Pack for AIRA.

Provides safe virtual filesystem (VFS) coordination, path traversal validation,
and platform filesystem adapters.
"""

import shutil
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.permission_manager import PermissionManager
from aira.infrastructure.service_registry import ServiceRegistry
from aira.infrastructure.skill_engine import BaseSkill, SkillEngineError, SkillMetadata

logger = structlog.get_logger("aira.fs_skills")


class FilesystemError(SkillEngineError):
    """Base exception for all filesystem operations failures."""

    pass


class UnsafePathError(FilesystemError):
    """Raised when traversal attempts or prohibited root modifications occur."""

    pass


class VirtualFilesystem:
    """Resolves logical location tokens into isolated absolute paths."""

    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir
        self.roots = {
            "HOME": root_dir / "home",
            "PROJECTS": root_dir / "projects",
            "DOCUMENTS": root_dir / "documents",
            "DOWNLOADS": root_dir / "downloads",
            "DESKTOP": root_dir / "desktop",
            "TEMP": root_dir / "temp",
            "WORKSPACE": root_dir / "workspace",
        }

        # Automatically construct directories structure
        for directory in self.roots.values():
            directory.mkdir(parents=True, exist_ok=True)

    def resolve_logical_path(self, path_str: str) -> Path:
        """Translate logical prefix (e.g. WORKSPACE/file.txt) to absolute Path."""
        parts = path_str.strip().split("/", 1)
        prefix = parts[0].upper()

        if prefix in self.roots:
            relative = parts[1] if len(parts) > 1 else ""
            return (self.roots[prefix] / relative).resolve()

        # Fallback to WORKSPACE relative if no prefix matched
        return (self.roots["WORKSPACE"] / path_str).resolve()


class PathValidator:
    """Validates path string parameters ensuring safety constraints."""

    @staticmethod
    def validate_path(path: Path, allowed_roots: list[Path]) -> None:
        """Assert path resolved value remains inside the VFS root bounds."""
        try:
            resolved = path.resolve()
        except Exception as ex:
            raise UnsafePathError(f"Failed to resolve path: {path}") from ex

        # Traversal protection check
        is_allowed = False
        for root in allowed_roots:
            try:
                resolved_root = root.resolve()
                if resolved.parts[: len(resolved_root.parts)] == resolved_root.parts:
                    is_allowed = True
                    break
            except Exception:
                continue

        if not is_allowed:
            raise UnsafePathError(f"Path resolves outside allowed roots boundary: {path}")

        # Prohibited System folder matching protection check
        for prohibited in ["/System", "/private", "/etc", "/var", "/bin", "/sbin"]:
            if str(resolved).startswith(prohibited):
                raise UnsafePathError(f"Access to reserved location is forbidden: {resolved}")


class BaseFilesystemAdapter(ABC):
    """Abstract base class that all operating system filesystem adapters must implement."""

    @abstractmethod
    def read_file(self, path: Path) -> str:
        """Read text content from file."""
        pass

    @abstractmethod
    def write_file(self, path: Path, content: str) -> None:
        """Write text content into file."""
        pass

    @abstractmethod
    def append_file(self, path: Path, content: str) -> None:
        """Append text content into file."""
        pass

    @abstractmethod
    def create_folder(self, path: Path) -> None:
        """Create new directory."""
        pass

    @abstractmethod
    def list_directory(self, path: Path) -> list[str]:
        """List filenames inside directory."""
        pass

    @abstractmethod
    def move_file(self, src: Path, dst: Path) -> None:
        """Move file to target destination."""
        pass

    @abstractmethod
    def copy_file(self, src: Path, dst: Path) -> None:
        """Copy file to target destination."""
        pass

    @abstractmethod
    def rename_file(self, src: Path, name: str) -> None:
        """Rename targeted file."""
        pass

    @abstractmethod
    def exists(self, path: Path) -> bool:
        """Check whether target path exists."""
        pass


class MacFilesystemAdapter(BaseFilesystemAdapter):
    """macOS implementation of filesystem operations."""

    def read_file(self, path: Path) -> str:
        if not path.is_file():
            raise FilesystemError(f"File not found: {path}")
        return path.read_text(encoding="utf-8")

    def write_file(self, path: Path, content: str) -> None:
        path.write_text(content, encoding="utf-8")

    def append_file(self, path: Path, content: str) -> None:
        with path.open("a", encoding="utf-8") as f:
            f.write(content)

    def create_folder(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)

    def list_directory(self, path: Path) -> list[str]:
        if not path.is_dir():
            raise FilesystemError(f"Directory not found: {path}")
        return [entry.name for entry in path.iterdir()]

    def move_file(self, src: Path, dst: Path) -> None:
        shutil.move(str(src), str(dst))

    def copy_file(self, src: Path, dst: Path) -> None:
        shutil.copy2(str(src), str(dst))

    def rename_file(self, src: Path, name: str) -> None:
        src.rename(src.parent / name)

    def exists(self, path: Path) -> bool:
        return path.exists()


class WindowsFilesystemAdapter(BaseFilesystemAdapter):
    """Windows filesystem adapter placeholder."""

    def read_file(self, path: Path) -> str:
        raise FilesystemError("Windows filesystem adapter is not implemented.")

    def write_file(self, path: Path, content: str) -> None:
        raise FilesystemError("Windows filesystem adapter is not implemented.")

    def append_file(self, path: Path, content: str) -> None:
        raise FilesystemError("Windows filesystem adapter is not implemented.")

    def create_folder(self, path: Path) -> None:
        raise FilesystemError("Windows filesystem adapter is not implemented.")

    def list_directory(self, path: Path) -> list[str]:
        raise FilesystemError("Windows filesystem adapter is not implemented.")

    def move_file(self, src: Path, dst: Path) -> None:
        raise FilesystemError("Windows filesystem adapter is not implemented.")

    def copy_file(self, src: Path, dst: Path) -> None:
        raise FilesystemError("Windows filesystem adapter is not implemented.")

    def rename_file(self, src: Path, name: str) -> None:
        raise FilesystemError("Windows filesystem adapter is not implemented.")

    def exists(self, path: Path) -> bool:
        raise FilesystemError("Windows filesystem adapter is not implemented.")


class LinuxFilesystemAdapter(BaseFilesystemAdapter):
    """Linux filesystem adapter placeholder."""

    def read_file(self, path: Path) -> str:
        raise FilesystemError("Linux filesystem adapter is not implemented.")

    def write_file(self, path: Path, content: str) -> None:
        raise FilesystemError("Linux filesystem adapter is not implemented.")

    def append_file(self, path: Path, content: str) -> None:
        raise FilesystemError("Linux filesystem adapter is not implemented.")

    def create_folder(self, path: Path) -> None:
        raise FilesystemError("Linux filesystem adapter is not implemented.")

    def list_directory(self, path: Path) -> list[str]:
        raise FilesystemError("Linux filesystem adapter is not implemented.")

    def move_file(self, src: Path, dst: Path) -> None:
        raise FilesystemError("Linux filesystem adapter is not implemented.")

    def copy_file(self, src: Path, dst: Path) -> None:
        raise FilesystemError("Linux filesystem adapter is not implemented.")

    def rename_file(self, src: Path, name: str) -> None:
        raise FilesystemError("Linux filesystem adapter is not implemented.")

    def exists(self, path: Path) -> bool:
        raise FilesystemError("Linux filesystem adapter is not implemented.")


class FilesystemManager:
    """Orchestrates path validations, evaluates safety modes, and triggers adapter actions."""

    def __init__(
        self,
        config: AppConfig,
        registry: ServiceRegistry,
        event_bus: EventBus,
        permission_manager: PermissionManager,
    ) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus
        self.permission_manager = permission_manager

        # Root VFS directory isolated within user config paths
        self.vfs = VirtualFilesystem(config.paths.data_dir / "vfs")
        self.validator = PathValidator()

        # Instantiate platform adapter
        if sys.platform == "darwin":
            self.adapter: BaseFilesystemAdapter = MacFilesystemAdapter()
        elif sys.platform == "win32":
            self.adapter = WindowsFilesystemAdapter()
        else:
            self.adapter = LinuxFilesystemAdapter()

        self.read_only = False

    def read_file(self, path_str: str) -> str:
        """Resolve, validate permission boundary rules, and read content."""
        self.event_bus.publish_sync(
            Event(
                name="filesystem.request",
                category="Filesystem",
                source="FilesystemManager",
                payload={"action": "READ", "path": path_str},
            )
        )

        # Check permission checks gate
        self.permission_manager.authorize_execution(
            permission="FILESYSTEM_ACCESS", capability="READ_FILE"
        )

        resolved_path = self.vfs.resolve_logical_path(path_str)
        self.event_bus.publish_sync(
            Event(
                name="filesystem.path_resolved",
                category="Filesystem",
                source="FilesystemManager",
                payload={"logical": path_str, "resolved": str(resolved_path)},
            )
        )

        # Validate roots containment
        self.validator.validate_path(resolved_path, list(self.vfs.roots.values()))
        self.event_bus.publish_sync(
            Event(
                name="filesystem.validation_passed",
                category="Filesystem",
                source="FilesystemManager",
                payload={"path": str(resolved_path)},
            )
        )

        try:
            content = self.adapter.read_file(resolved_path)
            self.event_bus.publish_sync(
                Event(
                    name="filesystem.read_completed",
                    category="Filesystem",
                    source="FilesystemManager",
                    payload={"path": str(resolved_path)},
                )
            )
            return content
        except Exception as ex:
            self.event_bus.publish_sync(
                Event(
                    name="filesystem.operation_failed",
                    category="Filesystem",
                    source="FilesystemManager",
                    payload={"path": str(resolved_path), "error": str(ex)},
                )
            )
            raise

    def write_file(self, path_str: str, content: str) -> None:
        """Resolve, validate permission boundary rules, and write content."""
        self.event_bus.publish_sync(
            Event(
                name="filesystem.request",
                category="Filesystem",
                source="FilesystemManager",
                payload={"action": "WRITE", "path": path_str},
            )
        )

        if self.read_only:
            raise FilesystemError("Cannot write file: Manager is in read-only policy mode.")

        # Check permission checks gate
        self.permission_manager.authorize_execution(
            permission="FILESYSTEM_ACCESS", capability="WRITE_FILE"
        )

        resolved_path = self.vfs.resolve_logical_path(path_str)
        self.event_bus.publish_sync(
            Event(
                name="filesystem.path_resolved",
                category="Filesystem",
                source="FilesystemManager",
                payload={"logical": path_str, "resolved": str(resolved_path)},
            )
        )

        # Validate roots containment
        self.validator.validate_path(resolved_path, list(self.vfs.roots.values()))
        self.event_bus.publish_sync(
            Event(
                name="filesystem.validation_passed",
                category="Filesystem",
                source="FilesystemManager",
                payload={"path": str(resolved_path)},
            )
        )

        try:
            self.adapter.write_file(resolved_path, content)
            self.event_bus.publish_sync(
                Event(
                    name="filesystem.write_completed",
                    category="Filesystem",
                    source="FilesystemManager",
                    payload={"path": str(resolved_path)},
                )
            )
        except Exception as ex:
            self.event_bus.publish_sync(
                Event(
                    name="filesystem.operation_failed",
                    category="Filesystem",
                    source="FilesystemManager",
                    payload={"path": str(resolved_path), "error": str(ex)},
                )
            )
            raise

    def create_folder(self, path_str: str) -> None:
        """Resolve, validate permission boundary rules, and create folder directory."""
        self.event_bus.publish_sync(
            Event(
                name="filesystem.request",
                category="Filesystem",
                source="FilesystemManager",
                payload={"action": "CREATE_DIR", "path": path_str},
            )
        )

        if self.read_only:
            raise FilesystemError("Cannot create folder: Manager is in read-only policy mode.")

        # Check permission checks gate
        self.permission_manager.authorize_execution(
            permission="FILESYSTEM_ACCESS", capability="CREATE_FOLDER"
        )

        resolved_path = self.vfs.resolve_logical_path(path_str)
        self.event_bus.publish_sync(
            Event(
                name="filesystem.path_resolved",
                category="Filesystem",
                source="FilesystemManager",
                payload={"logical": path_str, "resolved": str(resolved_path)},
            )
        )

        # Validate roots containment
        self.validator.validate_path(resolved_path, list(self.vfs.roots.values()))
        self.event_bus.publish_sync(
            Event(
                name="filesystem.validation_passed",
                category="Filesystem",
                source="FilesystemManager",
                payload={"path": str(resolved_path)},
            )
        )

        try:
            self.adapter.create_folder(resolved_path)
            self.event_bus.publish_sync(
                Event(
                    name="filesystem.directory_created",
                    category="Filesystem",
                    source="FilesystemManager",
                    payload={"path": str(resolved_path)},
                )
            )
        except Exception as ex:
            self.event_bus.publish_sync(
                Event(
                    name="filesystem.operation_failed",
                    category="Filesystem",
                    source="FilesystemManager",
                    payload={"path": str(resolved_path), "error": str(ex)},
                )
            )
            raise


class FileReadSkill(BaseSkill):
    """AIRA execution skill for reading files safely."""

    def __init__(self, manager: FilesystemManager) -> None:
        metadata = SkillMetadata(
            skill_id="file_read",
            name="Read File Skill",
            version="0.1.0",
            description="Read text content from files safely",
            author="AIRA",
            category="Filesystem",
            supported_platforms=["darwin"],
            required_permissions=["FILESYSTEM_ACCESS"],
            required_capabilities=["READ_FILE"],
            input_schema={"required": ["path"]},
        )
        super().__init__(metadata)
        self.manager = manager

    def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        self.validate(input_data)
        content = self.manager.read_file(input_data["path"])
        return {"status": "SUCCESS", "content": content}


class FileWriteSkill(BaseSkill):
    """AIRA execution skill for writing files safely."""

    def __init__(self, manager: FilesystemManager) -> None:
        metadata = SkillMetadata(
            skill_id="file_write",
            name="Write File Skill",
            version="0.1.0",
            description="Write text content into files safely",
            author="AIRA",
            category="Filesystem",
            supported_platforms=["darwin"],
            required_permissions=["FILESYSTEM_ACCESS"],
            required_capabilities=["WRITE_FILE"],
            input_schema={"required": ["path", "content"]},
        )
        super().__init__(metadata)
        self.manager = manager

    def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        self.validate(input_data)
        self.manager.write_file(input_data["path"], input_data["content"])
        return {"status": "SUCCESS", "message": f"Wrote content into: {input_data['path']}"}


class CreateFolderSkill(BaseSkill):
    """AIRA execution skill for creating folder directories safely."""

    def __init__(self, manager: FilesystemManager) -> None:
        metadata = SkillMetadata(
            skill_id="create_folder",
            name="Create Folder Skill",
            version="0.1.0",
            description="Create folder directories safely",
            author="AIRA",
            category="Filesystem",
            supported_platforms=["darwin"],
            required_permissions=["FILESYSTEM_ACCESS"],
            required_capabilities=["CREATE_FOLDER"],
            input_schema={"required": ["path"]},
        )
        super().__init__(metadata)
        self.manager = manager

    def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        self.validate(input_data)
        self.manager.create_folder(input_data["path"])
        return {"status": "SUCCESS", "message": f"Folder directory created: {input_data['path']}"}
