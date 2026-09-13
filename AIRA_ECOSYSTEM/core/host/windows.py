"""
core/host/windows.py — Windows adapter untuk Host Abstraction Layer.
"""

from pathlib import Path, PureWindowsPath

from core.host.models import HostInfo


class WindowsHostAdapter:
    """Implementasi HAL untuk Windows."""

    def __init__(self, host_info: HostInfo):
        self.host_info = host_info

    def get_home(self) -> Path:
        return Path(self.host_info.home_directory)

    def get_workspace(self) -> Path:
        return Path(self.host_info.workspace_root)

    def normalize_path(self, raw_path: str) -> PureWindowsPath:
        """
        Normalisasi string path mentah (bisa pakai '/' atau '\\') jadi
        PureWindowsPath yang valid, TANPA me-resolve terhadap workspace
        (itu tanggung jawab WorkspaceManager.resolve()).
        """
        cleaned = raw_path.replace("/", "\\")
        return PureWindowsPath(cleaned)

    def resolve_relative(self, base: Path, relative_path: str) -> Path:
        """
        Gabungkan base (biasanya workspace root) dengan path relatif dari
        user. Sandbox enforcement FINAL tetap dilakukan di
        WorkspaceManager.resolve() (defense in depth) - fungsi ini hanya
        membangun path kandidat.
        """
        relative_path = relative_path.replace("\\", "/").lstrip("/")
        return (base / relative_path).resolve()

    def path_separator(self) -> str:
        return "\\"

    def is_case_sensitive(self) -> bool:
        return False