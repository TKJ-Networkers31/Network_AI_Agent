"""
agents/akane/connection_manager.py — AIRA Persistent Connection Engine
(APCE), Phase 2.2.

Nama resmi APCE sekarang "AIRA Persistent Connection Engine" (sebelumnya
"AKANE Persistent Connection Engine"). Path file tetap
agents/akane/connection_manager.py supaya import lama tidak patah; event di
Event Bus kini ditandai agent="AIRA".

SATU-SATUNYA modul yang boleh membuka/menutup/menjalankan perintah lewat
tools/ssh/shell.py (PersistentShell / invoke_shell). REI dan
network_tools TIDAK BOLEH memanggil paramiko atau tools/ssh/shell.py
secara langsung - semua harus lewat ConnectionManager di file ini.

Integrasi DIO: orchestrator (core/orchestrator.py) memastikan device_name
valid SEBELUM execute_for_device() dipanggil - kalau kosong/ambigu AIRA
bertanya lewat form pilihan perangkat.

PERUBAHAN (Inventory SQLite):
- Device & credential TIDAK lagi dibaca dari inventory/router.yaml dan
  password TIDAK lagi dari SSH_PASSWORD di .env. Semuanya lewat
  core/inventory_store.py::resolve_ssh() (satu-satunya jalur yang
  mengembalikan secret ter-decrypt).
- Password kosong "" adalah password VALID (RouterOS default user admin
  tanpa password) dan dibedakan dari None (= tidak ada credential). Semua
  pengecekan memakai `is None`, BUKAN `not password`.
- Reconnect otomatis mengambil credential TERBARU dari inventory (kalau
  device terdaftar), jadi ganti password di menu Devices langsung berlaku
  tanpa restart. Untuk sesi manual (host diketik tangan) password disimpan
  di memori proses saja (tidak pernah ke disk/log/event).
- Credential bertipe ssh_key belum didukung oleh PersistentShell
  (tools/ssh/shell.py hanya menerima password); device yang HANYA punya
  key mendapat pesan error yang jelas, bukan gagal diam-diam.

FIX (Optimalisasi APCE):
1. Race condition TOCTOU di open_connection(): slot direservasi ke
   self._pending_hosts SAAT MASIH DALAM LOCK yang sama dengan pengecekan
   MAX_CONCURRENT_SESSIONS, dilepas lagi di blok finally apa pun hasilnya.
2. PersistentShell.execute() mengembalikan dict {"output", "prompt_matched"};
   execute() di sini menambahkan field "warning" kalau prompt_matched=False
   supaya output yang mungkin terpotong tidak dianggap sukses penuh.
"""

import os
import threading
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from tools.ssh.shell import PersistentShell
from agents.akane.session_state import (
    ConnectionSession, new_session_id,
    STATUS_BUSY, STATUS_CLOSED, STATUS_ERROR,
)
from core.events import event_bus
from core.inventory_store import get_inventory_store
from core.logger import get_logger, log_event

logger = get_logger("connection_manager")

# Penanda sumber event untuk APCE di Event Bus / log.
EVENT_AGENT = "AIRA"

BASE_DIR = Path(__file__).resolve().parents[2]  # AIRA_ECOSYSTEM/

load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR.parent / ".env", override=False)

MAX_CONCURRENT_SESSIONS = 5
IDLE_TIMEOUT_SECONDS = 10 * 60  # 10 menit
MONITOR_INTERVAL_SECONDS = 30

KEY_ONLY_ERROR = (
    "Device ini hanya punya credential bertipe ssh_key, sedangkan koneksi persisten "
    "(invoke_shell) saat ini hanya mendukung password. Tambahkan credential ssh_password "
    "ke device ini di menu Devices."
)


class ConnectionManager:
    """Singleton. Ambil instance lewat get_connection_manager()."""

    def __init__(self):
        self._sessions: dict[str, ConnectionSession] = {}
        self._host_index: dict[str, str] = {}  # "host:port:username" -> session_id
        self._pending_hosts: set[str] = set()  # host_key sedang dibuka (reservasi slot)
        self._lock = threading.RLock()
        self._session_locks: dict[str, threading.Lock] = {}

        # Password sesi MANUAL (host diketik tangan, bukan dari inventory).
        # Hanya di memori proses; tidak pernah ditulis ke disk/log/event.
        self._manual_secrets: dict[str, str] = {}

        self._monitor_stop = threading.Event()
        self._monitor_thread = threading.Thread(
            target=self._idle_monitor_loop, daemon=True
        )
        self._monitor_thread.start()

    # ------------------------------------------------------------
    # INVENTORY HELPERS
    # ------------------------------------------------------------

    @staticmethod
    def _resolve_target(device_name: str) -> dict:
        """
        Device + credential dari Inventory Store.

        Return {"success": True, "name", "host", "port", "username", "password"}
        atau {"success": False, "error": ...}. `password` bisa "" (valid) atau
        None (tidak ada credential ssh_password).
        """
        target = get_inventory_store().resolve_ssh(device_name)

        if not target.get("success"):
            return {
                "success": False,
                "error": target.get("error") or f"Device '{device_name}' tidak ditemukan di inventory.",
            }

        password = target.get("password")

        if password is None:
            if target.get("key"):
                return {"success": False, "error": KEY_ONLY_ERROR}

            return {
                "success": False,
                "error": (
                    f"Device '{device_name}' belum punya credential SSH. Tambahkan credential "
                    "(menu Devices, atau tool add_credential/link_credential) lalu coba lagi."
                ),
            }

        return {
            "success": True,
            "name": target.get("name") or target.get("device_name") or device_name,
            "host": target["host"],
            "port": int(target.get("port") or 22),
            "username": target["username"],
            "password": password,
        }

    @staticmethod
    def _host_key(host: str, port: int, username: str) -> str:
        return f"{host}:{port}:{username}"

    def _get_lock(self, session_id: str) -> threading.Lock:
        with self._lock:
            return self._session_locks.setdefault(session_id, threading.Lock())

    @staticmethod
    def _publish(event_name: str, **kwargs) -> None:
        """Event Bus tidak boleh menggagalkan operasi koneksi."""
        try:
            event_bus.publish(event_name, agent=EVENT_AGENT, **kwargs)
        except Exception:
            logger.exception("APCE | gagal publish %s (diabaikan).", event_name)

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
        # None = tidak diberikan -> fallback .env. "" = password kosong yang
        # SENGAJA (valid), jangan ditimpa fallback.
        if password is None:
            password = os.getenv("SSH_PASSWORD")

        if password is None:
            return {
                "success": False,
                "error": (
                    "Password SSH tidak diberikan. Isi password (boleh kosong kalau device memang "
                    "tanpa password), atau daftarkan device + credential di menu Devices."
                ),
            }

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

            # Reservasi slot di sini, MASIH DALAM LOCK yang sama dengan
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
                self._publish(
                    "connection.error",
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

                # Sesi manual: simpan password di memori untuk reconnect.
                # Sesi dari inventory tidak menyimpan apa pun (credential
                # selalu diambil segar dari Inventory Store).
                if not device_name:
                    self._manual_secrets[session_id] = password

            log_event(
                logger, "INFO", f"Koneksi SSH persisten dibuka ke {host}",
                category="connection_manager",
                context={"session_id": session_id, "host": host, "username": username},
            )

            self._publish(
                "connection.opened",
                data={"session_id": session_id, **session.to_dict()},
            )

            return {"success": True, "session": session.to_dict(), "reused": False}

        finally:
            # Slot pending selalu dilepas apa pun hasilnya (sukses/gagal),
            # supaya tidak "membocorkan" kuota MAX_CONCURRENT_SESSIONS.
            with self._lock:
                self._pending_hosts.discard(key)

    def open_connection_for_device(self, device_name: str) -> dict:
        target = self._resolve_target(device_name)

        if not target["success"]:
            return {"success": False, "error": target["error"]}

        return self.open_connection(
            host=target["host"],
            username=target["username"],
            password=target["password"],
            port=target["port"],
            device_name=target["name"],
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

            # Password sesi manual dibuang begitu sesi ditutup.
            self._manual_secrets.pop(session_id, None)

        log_event(
            logger, "INFO", f"Koneksi SSH ditutup ({reason})",
            category="connection_manager",
            context={"session_id": session_id, "host": session.host, "reason": reason},
        )

        self._publish(
            "connection.closed",
            data={"session_id": session_id, "host": session.host, "reason": reason},
        )

        return {"success": True}

    def _reconnect_credentials(self, session: ConnectionSession) -> dict:
        """
        Credential untuk reconnect otomatis.
        Sesi dari inventory -> ambil SEGAR dari Inventory Store.
        Sesi manual        -> password di memori, fallback SSH_PASSWORD.
        Return {"success", "host", "port", "username", "password"} / {"success": False, "error"}.
        """
        if session.device_name:
            target = self._resolve_target(session.device_name)

            if not target["success"]:
                return target

            return target

        with self._lock:
            password = self._manual_secrets.get(session.session_id)

        if password is None:
            password = os.getenv("SSH_PASSWORD")

        if password is None:
            return {"success": False, "error": "Password sesi manual tidak tersedia untuk reconnect."}

        return {
            "success": True, "host": session.host, "port": session.port,
            "username": session.username, "password": password,
        }

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

                creds = self._reconnect_credentials(session)

                if not creds["success"]:
                    session.status = STATUS_ERROR
                    session.last_error = f"Reconnect gagal: {creds['error']}"
                    self._publish(
                        "connection.error",
                        data={"session_id": session_id, "error": session.last_error},
                    )
                    return {"success": False, "session_id": session_id, "command": command, "error": session.last_error}

                try:
                    session.shell.open(
                        host=creds["host"], port=creds["port"],
                        username=creds["username"], password=creds["password"],
                    )
                    self._publish(
                        "connection.opened",
                        data={"session_id": session_id, **session.to_dict(), "reconnected": True},
                    )
                except Exception as exc:
                    session.status = STATUS_ERROR
                    session.last_error = f"Reconnect gagal: {exc}"
                    self._publish(
                        "connection.error",
                        data={"session_id": session_id, "error": session.last_error},
                    )
                    return {"success": False, "session_id": session_id, "command": command, "error": session.last_error}

            session.status = STATUS_BUSY

            try:
                # shell.execute() mengembalikan dict {"output", "prompt_matched"}.
                exec_result = session.shell.execute(command, timeout=timeout)
                output = exec_result["output"]
                prompt_matched = exec_result["prompt_matched"]

                session.touch()

                self._publish(
                    "connection.command", tool=session.device_name or session.host,
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

                self._publish(
                    "connection.error", tool=session.device_name or session.host,
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
        target = self._resolve_target(device_name)

        if not target["success"]:
            return {"success": False, "error": target["error"]}

        key = self._host_key(target["host"], target["port"], target["username"])

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
            self._publish("connection.timeout", data={"session_id": session_id})

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