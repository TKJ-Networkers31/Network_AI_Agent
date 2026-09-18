"""
agents/akane/connection_manager.py — AKANE Persistent Connection Engine
(APCE), Phase 2.2.

SATU-SATUNYA modul yang boleh membuka/menutup/menjalankan perintah lewat
tools/ssh/shell.py (PersistentShell / invoke_shell). REI dan
network_tools TIDAK BOLEH memanggil paramiko atau tools/ssh/shell.py
secara langsung - semua harus lewat ConnectionManager di file ini.

FIX (Optimalisasi APCE):
1. Race condition TOCTOU di open_connection(): sebelumnya cek
   MAX_CONCURRENT_SESSIONS dilakukan DI DALAM lock, tapi shell.open()
   (I/O lambat, blocking) dipanggil DI LUAR lock. Dua request
   open_connection() untuk device BERBEDA yang datang bersamaan bisa
   sama-sama lolos cek limit sebelum salah satu tercatat di
   self._sessions, sehingga limit bisa terlampaui. Fix: slot direservasi
   ke self._pending_hosts SAAT MASIH DALAM LOCK yang sama dengan
   pengecekan limit, dilepas lagi di blok finally apa pun hasilnya.
2. tools/ssh/shell.py::PersistentShell.execute() sekarang mengembalikan
   dict {"output", "prompt_matched"} bukan string mentah - execute() di
   sini diupdate untuk membaca bentuk baru itu dan menambahkan field
   "warning" ke hasil kalau prompt_matched=False, supaya caller (REI/
   LLM/UI) tahu output mungkin terpotong alih-alih diam-diam dianggap
   sukses penuh.
"""

import os
import threading
import time
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv

from tools.ssh.shell import PersistentShell
from agents.akane.session_state import (
    ConnectionSession, new_session_id,
    STATUS_BUSY, STATUS_CLOSED, STATUS_ERROR,
)
from core.events import event_bus
from core.logger import get_logger, log_event

logger = get_logger("connection_manager")

BASE_DIR = Path(__file__).resolve().parents[2]  # AIRA_ECOSYSTEM/
INVENTORY_FILE = BASE_DIR / "inventory" / "router.yaml"

load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR.parent / ".env", override=False)

MAX_CONCURRENT_SESSIONS = 5
IDLE_TIMEOUT_SECONDS = 10 * 60  # 10 menit
MONITOR_INTERVAL_SECONDS = 30


class ConnectionManager:
    """Singleton. Ambil instance lewat get_connection_manager()."""

    def __init__(self):
        self._sessions: dict[str, ConnectionSession] = {}
        self._host_index: dict[str, str] = {}  # "host:port:username" -> session_id
        self._pending_hosts: set[str] = set()  # host_key sedang dibuka (reservasi slot)
        self._lock = threading.RLock()
        self._session_locks: dict[str, threading.Lock] = {}

        self._monitor_stop = threading.Event()
        self._monitor_thread = threading.Thread(
            target=self._idle_monitor_loop, daemon=True
        )
        self._monitor_thread.start()

    # ------------------------------------------------------------
    # INVENTORY HELPERS
    # ------------------------------------------------------------

    def _load_inventory(self) -> dict:
        with open(INVENTORY_FILE, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _resolve_device(self, device_name: str) -> Optional[dict]:
        devices = self._load_inventory().get("devices", {})

        if device_name in devices:
            return {"name": device_name, **devices[device_name]}

        lowered = device_name.strip().lower()
        for key, value in devices.items():
            if key.lower() == lowered:
                return {"name": key, **value}

        return None

    @staticmethod
    def _host_key(host: str, port: int, username: str) -> str:
        return f"{host}:{port}:{username}"

    def _get_lock(self, session_id: str) -> threading.Lock:
        with self._lock:
            return self._session_locks.setdefault(session_id, threading.Lock())

    # ------------------------------------------------------------
    # PUBLIC: OPEN / CLOSE / EXECUTE
    # ------------------------------------------------------------

    def open_connection(
        self,
        host: str,
        username: str,
        password: Optional[str] = None,
        port: int = 22,
        device_name: Optional[str] = None,
    ) -> dict:
        password = password or os.getenv("SSH_PASSWORD")

        if not password:
            return {"success": False, "error": "Password SSH tidak diberikan dan SSH_PASSWORD tidak diset di .env."}

        key = self._host_key(host, port, username)

        with self._lock:
            existing_id = self._host_index.get(key)

            if existing_id and existing_id in self._sessions:
                session = self._sessions[existing_id]
                if session.status != STATUS_CLOSED:
                    logger.info("Reuse session yang sudah ada untuk %s (session=%s)", key, existing_id)
                    return {"success": True, "session": session.to_dict(), "reused": True}

            active_count = sum(1 for s in self._sessions.values() if s.status != STATUS_CLOSED)
            pending_count = len(self._pending_hosts)

            # FIX: reservasi slot di sini, MASIH DALAM LOCK yang sama dengan
            # pengecekan limit, sebelum shell.open() (I/O lambat) dipanggil
            # di luar lock. `key` yang sudah pending untuk dirinya sendiri
            # tidak dihitung dobel.
            if key not in self._pending_hosts and (active_count + pending_count) >= MAX_CONCURRENT_SESSIONS:
                return {
                    "success": False,
                    "error": f"Batas maksimal {MAX_CONCURRENT_SESSIONS} koneksi bersamaan tercapai.",
                }

            self._pending_hosts.add(key)

        try:
            shell = PersistentShell()

            try:
                shell.open(host=host, port=port, username=username, password=password)
            except Exception as exc:
                logger.error("Gagal membuka koneksi ke %s: %s", host, exc)
                event_bus.publish(
                    "connection.error", agent="AKANE",
                    data={"host": host, "username": username, "error": str(exc)},
                )
                return {"success": False, "error": str(exc)}

            session_id = new_session_id()
            session = ConnectionSession(
                session_id=session_id, device_name=device_name,
                host=host, port=port, username=username, shell=shell,
            )

            with self._lock:
                self._sessions[session_id] = session
                self._host_index[key] = session_id

            log_event(
                logger, "INFO", f"Koneksi SSH persisten dibuka ke {host}",
                category="connection_manager",
                context={"session_id": session_id, "host": host, "username": username},
            )

            event_bus.publish(
                "connection.opened", agent="AKANE",
                data={"session_id": session_id, **session.to_dict()},
            )

            return {"success": True, "session": session.to_dict(), "reused": False}

        finally:
            # Slot pending selalu dilepas apa pun hasilnya (sukses/gagal),
            # supaya tidak "membocorkan" kuota MAX_CONCURRENT_SESSIONS.
            with self._lock:
                self._pending_hosts.discard(key)

    def open_connection_for_device(self, device_name: str) -> dict:
        device = self._resolve_device(device_name)

        if not device:
            return {"success": False, "error": f"Device '{device_name}' tidak ditemukan di inventory."}

        return self.open_connection(
            host=device["host"],
            username=device["username"],
            password=os.getenv("SSH_PASSWORD"),
            port=device.get("port", 22),
            device_name=device["name"],
        )

    def close_connection(self, session_id: str, reason: str = "manual") -> dict:
        with self._lock:
            session = self._sessions.get(session_id)

        if not session:
            return {"success": False, "error": f"Session '{session_id}' tidak ditemukan."}

        if session.status == STATUS_CLOSED:
            return {"success": True, "already_closed": True}

        lock = self._get_lock(session_id)

        with lock:
            try:
                session.shell.close()
            except Exception as exc:
                logger.warning("Error saat menutup shell session=%s: %s", session_id, exc)

            session.status = STATUS_CLOSED

        with self._lock:
            key = self._host_key(session.host, session.port, session.username)
            if self._host_index.get(key) == session_id:
                self._host_index.pop(key, None)

        log_event(
            logger, "INFO", f"Koneksi SSH ditutup ({reason})",
            category="connection_manager",
            context={"session_id": session_id, "host": session.host, "reason": reason},
        )

        event_bus.publish(
            "connection.closed", agent="AKANE",
            data={"session_id": session_id, "host": session.host, "reason": reason},
        )

        return {"success": True}

    def execute(self, session_id: str, command: str, timeout: float = 25.0) -> dict:
        with self._lock:
            session = self._sessions.get(session_id)

        if not session:
            return {"success": False, "error": f"Session '{session_id}' tidak ditemukan."}

        if session.status == STATUS_CLOSED:
            return {"success": False, "error": "Session sudah ditutup."}

        lock = self._get_lock(session_id)

        # Command queue: kalau sedang ada command berjalan di session yang
        # sama, request berikutnya AKAN MENUNGGU giliran (blocking di
        # lock) alih-alih membuka channel kedua.
        with lock:
            # Auto-reconnect HANYA kalau jaringan putus (transport mati)
            # DAN status BUKAN closed (user belum menekan Close manual).
            if not session.shell.is_alive() and session.status != STATUS_CLOSED:
                logger.warning("Session %s terputus, mencoba reconnect otomatis...", session_id)
                try:
                    session.shell.open(
                        host=session.host, port=session.port,
                        username=session.username,
                        password=os.getenv("SSH_PASSWORD"),
                    )
                    event_bus.publish(
                        "connection.opened", agent="AKANE",
                        data={"session_id": session_id, **session.to_dict(), "reconnected": True},
                    )
                except Exception as exc:
                    session.status = STATUS_ERROR
                    session.last_error = f"Reconnect gagal: {exc}"
                    event_bus.publish(
                        "connection.error", agent="AKANE",
                        data={"session_id": session_id, "error": session.last_error},
                    )
                    return {"success": False, "session_id": session_id, "command": command, "error": session.last_error}

            session.status = STATUS_BUSY

            try:
                # FIX: shell.execute() sekarang mengembalikan dict
                # {"output", "prompt_matched"} - lihat tools/ssh/shell.py.
                exec_result = session.shell.execute(command, timeout=timeout)
                output = exec_result["output"]
                prompt_matched = exec_result["prompt_matched"]

                session.touch()

                event_bus.publish(
                    "connection.command", agent="AKANE", tool=session.device_name or session.host,
                    data={
                        "session_id": session_id, "command": command,
                        "success": True, "prompt_matched": prompt_matched,
                    },
                )

                result = {"success": True, "session_id": session_id, "command": command, "output": output}

                if not prompt_matched:
                    result["warning"] = (
                        "Output mungkin terpotong: prompt RouterOS tidak terdeteksi "
                        f"sebelum timeout ({timeout}s). Coba naikkan timeout atau "
                        "jalankan ulang command ini."
                    )
                    logger.warning(
                        "PROMPT TIDAK COCOK | session=%s command=%r - output "
                        "kemungkinan terpotong.", session_id, command,
                    )

                return result

            except Exception as exc:
                session.status = STATUS_ERROR
                session.last_error = str(exc)

                logger.error("Command '%s' gagal di session=%s: %s", command, session_id, exc)

                event_bus.publish(
                    "connection.error", agent="AKANE", tool=session.device_name or session.host,
                    data={"session_id": session_id, "command": command, "error": str(exc)},
                )

                return {"success": False, "session_id": session_id, "command": command, "error": str(exc)}

    def execute_for_device(self, device_name: str, command: str, timeout: float = 25.0) -> dict:
        """
        Dipanggil oleh network_tools.py. Auto-open session kalau device
        ini belum punya koneksi aktif, lalu reuse channel yang sama untuk
        command-command berikutnya - TIDAK PERNAH login ulang selama
        session masih hidup.
        """
        device = self._resolve_device(device_name)

        if not device:
            return {"success": False, "error": f"Device '{device_name}' tidak ditemukan di inventory."}

        key = self._host_key(device["host"], device.get("port", 22), device["username"])

        with self._lock:
            session_id = self._host_index.get(key)
            session_alive = (
                session_id in self._sessions
                and self._sessions[session_id].status != STATUS_CLOSED
            )

        if not session_alive:
            opened = self.open_connection_for_device(device_name)
            if not opened.get("success"):
                return opened
            session_id = opened["session"]["session_id"]

        return self.execute(session_id, command, timeout=timeout)

    # ------------------------------------------------------------
    # LIST / READ
    # ------------------------------------------------------------

    def list_sessions(self) -> list[dict]:
        with self._lock:
            sessions = list(self._sessions.values())

        return [s.to_dict() for s in sessions if s.status != STATUS_CLOSED]

    def get_session(self, session_id: str) -> Optional[dict]:
        with self._lock:
            session = self._sessions.get(session_id)

        return session.to_dict() if session else None

    # ------------------------------------------------------------
    # IDLE TIMEOUT MONITOR (background thread)
    # ------------------------------------------------------------

    def _idle_monitor_loop(self):
        while not self._monitor_stop.wait(MONITOR_INTERVAL_SECONDS):
            try:
                self._check_idle_sessions()
            except Exception:
                logger.exception("idle_monitor_loop error (diabaikan)")

    def _check_idle_sessions(self):
        with self._lock:
            candidates = [
                s.session_id for s in self._sessions.values()
                if s.status != STATUS_CLOSED and s.idle_seconds() > IDLE_TIMEOUT_SECONDS
            ]

        for session_id in candidates:
            logger.info("Session %s idle > %ds, menutup otomatis.", session_id, IDLE_TIMEOUT_SECONDS)
            self.close_connection(session_id, reason="idle_timeout")
            event_bus.publish("connection.timeout", agent="AKANE", data={"session_id": session_id})

    def shutdown(self):
        """Dipanggil dari FastAPI shutdown event (lihat api/main.py) - tutup
        semua session supaya channel SSH tidak menggantung saat restart/reload."""
        with self._lock:
            ids = list(self._sessions.keys())

        for session_id in ids:
            self.close_connection(session_id, reason="shutdown")

        self._monitor_stop.set()


_manager_singleton: Optional[ConnectionManager] = None
_manager_lock = threading.Lock()


def get_connection_manager() -> ConnectionManager:
    global _manager_singleton

    if _manager_singleton is None:
        with _manager_lock:
            if _manager_singleton is None:
                _manager_singleton = ConnectionManager()

    return _manager_singleton