"""
core/host/detector.py — deteksi otomatis host (Windows/Linux) untuk HAL.

SATU-SATUNYA tempat yang boleh memutuskan OS apa yang sedang berjalan
dan adapter mana yang dipakai. File System Engine (core/filesystem/*)
TIDAK PERNAH memanggil platform.system() sendiri - selalu lewat HAL ini.
"""

import getpass
import logging
import platform
import socket
from pathlib import Path
from typing import Optional

from core.host.models import HostInfo
from core.host.windows import WindowsHostAdapter
from core.host.linux import LinuxHostAdapter
from core.events import event_bus

logger = logging.getLogger("aira.host.detector")

_WINDOWS_DEFAULT_DRIVE = "D:/AIRA_WORKSPACE"
_WINDOWS_FALLBACK_DRIVE = "C:/AIRA_WORKSPACE"
_LINUX_WORKSPACE_SUBDIR = "AIRA_WORKSPACE"


def _detect_os_name() -> str:
    system = platform.system().lower()

    if system == "windows":
        return "windows"

    if system == "linux":
        return "linux"

    # Sprint 02 hanya mendukung Windows & Linux. OS lain (mis. macOS)
    # di-fallback ke adapter Linux (POSIX-compatible) supaya HAL tidak
    # crash total di host yang tidak eksplisit didukung.
    logger.warning(
        "OS '%s' tidak eksplisit didukung Sprint 02 - fallback ke "
        "adapter Linux (POSIX).", system,
    )
    return "linux"


def _resolve_windows_workspace_root() -> str:
    if Path("D:/").exists():
        return _WINDOWS_DEFAULT_DRIVE
    return _WINDOWS_FALLBACK_DRIVE


def _resolve_linux_workspace_root(home_directory: str) -> str:
    return str(Path(home_directory) / _LINUX_WORKSPACE_SUBDIR)


def detect_host() -> HostInfo:
    """Deteksi host saat ini dan kembalikan HostInfo lengkap."""

    os_name = _detect_os_name()
    home_directory = str(Path.home())

    if os_name == "windows":
        workspace_root = _resolve_windows_workspace_root()
        separator = "\\"
        case_sensitive = False
    else:
        workspace_root = _resolve_linux_workspace_root(home_directory)
        separator = "/"
        case_sensitive = True

    try:
        hostname = socket.gethostname()
    except Exception:
        hostname = "unknown-host"

    try:
        username = getpass.getuser()
    except Exception:
        username = "unknown-user"

    info = HostInfo(
        os_name=os_name,
        os_version=platform.version(),
        architecture=platform.machine(),
        hostname=hostname,
        username=username,
        home_directory=home_directory,
        workspace_root=workspace_root,
        separator=separator,
        case_sensitive=case_sensitive,
    )

    logger.info(
        "HOST DETECTED | os=%s arch=%s workspace_root=%s",
        info.os_name, info.architecture, info.workspace_root,
    )

    try:
        event_bus.publish("host.detected", agent="HAL", data=info.to_dict())
    except Exception:
        logger.exception("Gagal publish event host.detected (diabaikan).")

    return info


def get_host_adapter(host_info: Optional[HostInfo] = None):
    """Kembalikan adapter (Windows/Linux) sesuai HostInfo (Dependency
    Injection) - kalau tidak diberikan, dideteksi otomatis."""

    info = host_info or detect_host()

    if info.os_name == "windows":
        return WindowsHostAdapter(info)

    return LinuxHostAdapter(info)


_singleton_host_info: Optional[HostInfo] = None
_singleton_adapter = None


def get_host_info() -> HostInfo:
    """Singleton - deteksi host sekali per proses."""

    global _singleton_host_info

    if _singleton_host_info is None:
        _singleton_host_info = detect_host()

    return _singleton_host_info


def get_default_adapter():
    """Singleton adapter, dibangun dari get_host_info()."""

    global _singleton_adapter

    if _singleton_adapter is None:
        _singleton_adapter = get_host_adapter(get_host_info())

    return _singleton_adapter