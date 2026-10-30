"""
agents/akane/session_state.py — struktur data untuk satu sesi koneksi SSH
persisten yang dikelola oleh ConnectionManager (APCE - AKANE Persistent
Connection Engine, Phase 2.2).
"""

import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from tools.ssh.shell import PersistentShell

STATUS_CONNECTING = "connecting"
STATUS_CONNECTED = "connected"
STATUS_BUSY = "busy"
STATUS_CLOSED = "closed"
STATUS_ERROR = "error"


@dataclass
class ConnectionSession:
    session_id: str
    device_name: Optional[str]
    host: str
    port: int
    username: str
    shell: PersistentShell
    connected_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    status: str = STATUS_CONNECTED
    last_error: Optional[str] = None
    max_lifetime_seconds: float = 3600.0  # Default 1 hour max session lifetime
    command_count: int = 0
    total_latency_ms: float = 0.0
    last_latency_ms: float = 0.0

    def touch(self) -> None:
        self.last_activity = time.time()
        if self.status != STATUS_CLOSED:
            self.status = STATUS_CONNECTED

    def record_command(self, latency_ms: float) -> None:
        self.command_count += 1
        self.last_latency_ms = round(latency_ms, 2)
        self.total_latency_ms += latency_ms
        self.touch()

    @property
    def avg_latency_ms(self) -> float:
        if self.command_count <= 0:
            return 0.0
        return round(self.total_latency_ms / self.command_count, 2)

    def idle_seconds(self) -> float:
        return time.time() - self.last_activity

    def uptime_seconds(self) -> float:
        return time.time() - self.connected_at

    def is_expired(self, now: Optional[float] = None) -> bool:
        ts = now if now is not None else time.time()
        return (ts - self.connected_at) > self.max_lifetime_seconds

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "device_name": self.device_name,
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "status": self.status,
            "connected_at": self.connected_at,
            "last_activity": self.last_activity,
            "idle_seconds": round(self.idle_seconds(), 1),
            "uptime_seconds": round(self.uptime_seconds(), 1),
            "command_count": self.command_count,
            "avg_latency_ms": self.avg_latency_ms,
            "last_latency_ms": self.last_latency_ms,
            "last_error": self.last_error,
            "is_expired": self.is_expired(),
        }


def new_session_id() -> str:
    return uuid.uuid4().hex[:12]
