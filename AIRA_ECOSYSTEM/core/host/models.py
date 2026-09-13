"""
core/host/models.py — data model untuk info host (OS) AIRA OS.

Bagian dari Host Abstraction Layer (HAL). Modul ini TIDAK melakukan
deteksi apa pun - murni bentuk data (dataclass) yang dikembalikan oleh
core/host/detector.py dan dikonsumsi oleh adapter (windows.py/linux.py)
serta oleh File System Engine (core/filesystem/*).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class HostInfo:
    os_name: str
    os_version: str
    architecture: str
    hostname: str
    username: str
    home_directory: str
    workspace_root: str
    separator: str
    case_sensitive: bool

    def to_dict(self) -> dict:
        return {
            "os_name": self.os_name,
            "os_version": self.os_version,
            "architecture": self.architecture,
            "hostname": self.hostname,
            "username": self.username,
            "home_directory": self.home_directory,
            "workspace_root": self.workspace_root,
            "separator": self.separator,
            "case_sensitive": self.case_sensitive,
        }