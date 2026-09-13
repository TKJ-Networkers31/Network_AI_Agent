"""
core/host/linux.py — Linux (POSIX) adapter untuk Host Abstraction Layer.
"""

from pathlib import Path, PurePosixPath

from core.host.models import HostInfo


class LinuxHostAdapter:
    """Implementasi HAL untuk Linux/POSIX."""

    def __init__(self, host_info: HostInfo):
        self.host_info = host_info

    def get_home(self) -> Path:
        return Path(self.host_info.home_directory)

    def get_workspace(self) -> Path:
        return Path(self.host_info.workspace_root)

    def normalize_path(self, raw_path: str) -> PurePosixPath:
        cleaned = raw_path.replace("\\", "/")
        return PurePosixPath(cleaned)

    def resolve_relative(self, base: Path, relative_path: str) -> Path:
        relative_path = relative_path.replace("\\", "/").lstrip("/")
        return (base / relative_path).resolve()

    def path_separator(self) -> str:
        return "/"

    def is_case_sensitive(self) -> bool:
        return True