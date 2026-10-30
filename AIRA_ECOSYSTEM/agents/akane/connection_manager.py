"""
agents/akane/connection_manager.py — AIRA Persistent Connection Engine
(APCE), Phase 2.2 & Master Engineering Upgrade.

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

FITUR & PERBAIKAN MASTER UPGRADE:
1. Persistent SSH transport reuse across consecutive operations.
2. Per-target single-flight lock (`_target_locks`) to eliminate TOCTOU and concurrent duplicate sessions to the same host.
3. Reconnect storm backoff (`_backoff`) with exponential backoff on consecutive failures.
4. Maximum session lifetime enforcement (`MAX_SESSION_LIFETIME_SECONDS`) to refresh long-running SSH transports safely.
5. Command latency profiling (`latency_ms`, `avg_latency_ms`) on ConnectionSession.
6. Unified evidence collection interface: `get_identity()`, `get_interfaces()`, `get_routes()`, `get_ip_addresses()`,
   `get_firewall_rules()`, `get_nat_rules()`, `get_configuration_snapshot()`, returning structured timestamped dictionaries.
7. Connection observability statistics via `get_stats()`.
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from tools.ssh.shell import PersistentShell
from agents.akane.session_state import (
    ConnectionSession, new_session_id,
    STATUS_BUSY, STATUS_CLOSED, STATUS_CONNECTING, STATUS_ERROR,
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
MAX_SESSION_LIFETIME_SECONDS = 60 * 60  # 1 jam (max transport lifetime)
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
        self._target_locks: dict[str, threading.Lock] = {}  # Per-target single-flight lock
        self._backoff: dict[str, dict] = {}  # "host_key" -> {attempts, last_failed_at, cooldown_sec}

        self._total_sessions_opened = 0
        self._total_sessions_reused = 0

        # Password sesi MANUAL (host diketik tangan, bukan dari inventory).
        # Hanya di memori proses; tidak pernah ditulis ke disk/log/event.
        self._manual_secrets: dict[str, Any] = {}

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
        key_data = target.get("key")

        if password is None and not key_data:
            return {
                "success": False,
                "error": (
                    f"Device '{device_name}' belum punya credential SSH (password atau private key). "
                    "Tambahkan credential di menu Devices lalu coba lagi."
                ),
            }

        return {
            "success": True,
            "name": target.get("name") or target.get("device_name") or device_name,
            "host": target["host"],
            "port": int(target.get("port") or 22),
            "username": target["username"],
            "password": password,
            "key_data": key_data,
        }

    @staticmethod
    def _host_key(host: str, port: int, username: str) -> str:
        return f"{host}:{port}:{username}"

    def _get_lock(self, session_id: str) -> threading.Lock:
        with self._lock:
            return self._session_locks.setdefault(session_id, threading.Lock())

    def _get_target_lock(self, host_key: str) -> threading.Lock:
        with self._lock:
            return self._target_locks.setdefault(host_key, threading.Lock())

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
        key_data: Optional[str] = None,
    ) -> dict:
        # Jika host yang diberikan adalah nama alias perangkat di inventory (mis. "R1") alih-alih IP/domain:
        if host and ("." not in host and ":" not in host):
            target = self._resolve_target(host)
            if target.get("success"):
                device_name = device_name or target.get("name")
                host = target["host"]
                username = username or target.get("username", "admin")
                if password is None and not key_data:
                    password = target.get("password")
                    key_data = target.get("key")
                port = port if port != 22 else target.get("port", 22)

        if password is None and not key_data:
            password = os.getenv("SSH_PASSWORD")

        if password is None and not key_data:
            return {
                "success": False,
                "error": (
                    "Credential SSH tidak diberikan. Berikan password atau SSH key (password boleh "
                    "kosong jika router tanpa password), atau simpan di inventory."
                ),
            }

        key = self._host_key(host, port, username)
        target_lock = self._get_target_lock(key)

        with target_lock:
            # 1. Check Reconnect Storm Backoff
            now = time.time()
            with self._lock:
                bo = self._backoff.get(key)
                if bo and (now - bo["last_failed_at"]) < bo["cooldown_sec"]:
                    remaining = round(bo["cooldown_sec"] - (now - bo["last_failed_at"]), 1)
                    return {
                        "success": False,
                        "error": f"Reconnect backoff aktif untuk {key}. Coba lagi dalam {remaining}s (percobaan gagal: {bo['attempts']}).",
                        "backoff_active": True,
                        "cooldown_remaining_sec": remaining,
                    }

            # 2. Check existing active session reuse
            with self._lock:
                existing_id = self._host_index.get(key)
                if existing_id and existing_id in self._sessions:
                    session = self._sessions[existing_id]
                    if session.status != STATUS_CLOSED:
                        # If session reached max lifetime, close gracefully to refresh
                        if session.is_expired():
                            logger.info("Session %s reached max lifetime (%ds), refreshing connection.", existing_id, MAX_SESSION_LIFETIME_SECONDS)
                        else:
                            self._total_sessions_reused += 1
                            logger.info("Reuse session yang sudah ada untuk %s (session=%s)", key, existing_id)
                            return {"success": True, "session": session.to_dict(), "reused": True}

                active_count = sum(1 for s in self._sessions.values() if s.status != STATUS_CLOSED)
                pending_count = len(self._pending_hosts)

                if key not in self._pending_hosts and (active_count + pending_count) >= MAX_CONCURRENT_SESSIONS:
                    return {
                        "success": False,
                        "error": f"Batas maksimal {MAX_CONCURRENT_SESSIONS} koneksi bersamaan tercapai.",
                    }

                self._pending_hosts.add(key)

            try:
                shell = PersistentShell()

                try:
                    shell.open(host=host, port=port, username=username, password=password, key_data=key_data)
                except Exception as exc:
                    logger.error("Gagal membuka koneksi ke %s: %s", host, exc)
                    # Record failure backoff
                    with self._lock:
                        b = self._backoff.get(key, {"attempts": 0, "last_failed_at": 0.0, "cooldown_sec": 2.0})
                        b["attempts"] += 1
                        b["last_failed_at"] = time.time()
                        b["cooldown_sec"] = min(60.0, 2.0 * (2 ** (b["attempts"] - 1)))
                        self._backoff[key] = b

                    self._publish(
                        "connection.error",
                        data={"host": host, "username": username, "error": str(exc)},
                    )
                    return {"success": False, "error": str(exc)}

                # Connection successful — clear backoff
                with self._lock:
                    self._backoff.pop(key, None)
                    self._total_sessions_opened += 1

                session_id = new_session_id()
                session = ConnectionSession(
                    session_id=session_id, device_name=device_name,
                    host=host, port=port, username=username, shell=shell,
                    max_lifetime_seconds=MAX_SESSION_LIFETIME_SECONDS,
                )

                with self._lock:
                    self._sessions[session_id] = session
                    self._host_index[key] = session_id

                    if not device_name:
                        self._manual_secrets[session_id] = {"password": password, "key_data": key_data}

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
                with self._lock:
                    self._pending_hosts.discard(key)

    def open_connection_for_device(self, device_name: str) -> dict:
        target = self._resolve_target(device_name)

        if not target["success"]:
            return {"success": False, "error": target["error"]}

        return self.open_connection(
            host=target["host"],
            username=target["username"],
            password=target.get("password"),
            key_data=target.get("key_data"),
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
        if session.device_name:
            target = self._resolve_target(session.device_name)
            if not target["success"]:
                return target
            return target

        with self._lock:
            sec = self._manual_secrets.get(session.session_id)

        password = None
        key_data = None
        if isinstance(sec, dict):
            password = sec.get("password")
            key_data = sec.get("key_data")
        elif isinstance(sec, str):
            password = sec

        if password is None and not key_data:
            password = os.getenv("SSH_PASSWORD")

        if password is None and not key_data:
            return {"success": False, "error": "Credential sesi manual tidak tersedia untuk reconnect."}

        return {
            "success": True, "host": session.host, "port": session.port,
            "username": session.username, "password": password, "key_data": key_data,
        }

    def execute(self, session_id: str, command: str, timeout: float = 25.0) -> dict:
        with self._lock:
            session = self._sessions.get(session_id)

        if not session:
            return {"success": False, "error": f"Session '{session_id}' tidak ditemukan."}

        if session.status == STATUS_CLOSED:
            return {"success": False, "error": "Session sudah ditutup."}

        lock = self._get_lock(session_id)

        with lock:
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
                        username=creds["username"], password=creds.get("password"),
                        key_data=creds.get("key_data"),
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
                t0 = time.perf_counter()
                exec_result = session.shell.execute(command, timeout=timeout)
                latency_ms = (time.perf_counter() - t0) * 1000.0

                output = exec_result["output"]
                prompt_matched = exec_result["prompt_matched"]

                session.record_command(latency_ms)

                self._publish(
                    "connection.command", tool=session.device_name or session.host,
                    data={
                        "session_id": session_id, "command": command,
                        "success": True, "prompt_matched": prompt_matched,
                        "latency_ms": round(latency_ms, 2),
                    },
                )

                result = {
                    "success": True,
                    "session_id": session_id,
                    "command": command,
                    "output": output,
                    "latency_ms": round(latency_ms, 2),
                    "avg_latency_ms": session.avg_latency_ms,
                }

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
        target = self._resolve_target(device_name)

        if not target["success"]:
            return {"success": False, "error": target["error"]}

        key = self._host_key(target["host"], target["port"], target["username"])

        with self._lock:
            session_id = self._host_index.get(key)
            session_alive = (
                session_id in self._sessions
                and self._sessions[session_id].status != STATUS_CLOSED
                and not self._sessions[session_id].is_expired()
            )

        if not session_alive:
            opened = self.open_connection_for_device(device_name)
            if not opened.get("success"):
                return opened
            session_id = opened["session"]["session_id"]
        else:
            with self._lock:
                self._total_sessions_reused += 1

        return self.execute(session_id, command, timeout=timeout)

    def execute_command(
        self,
        command: str,
        device_name: Optional[str] = None,
        host: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        port: int = 22,
        key_data: Optional[str] = None,
        timeout: float = 25.0,
    ) -> dict:
        if device_name:
            target = self._resolve_target(device_name)
            if target.get("success"):
                return self.execute_for_device(device_name, command, timeout=timeout)
            if not host and ("." in device_name or ":" in device_name):
                host = device_name

        if not host:
            return {
                "success": False,
                "error": "Tentukan nama perangkat dari inventory (device_name) atau alamat IP/host router.",
            }

        user = username or "admin"
        key = self._host_key(host, port, user)

        with self._lock:
            session_id = self._host_index.get(key)
            session_alive = (
                session_id in self._sessions
                and self._sessions[session_id].status != STATUS_CLOSED
                and not self._sessions[session_id].is_expired()
            )

        if not session_alive:
            opened = self.open_connection(
                host=host,
                username=user,
                password=password,
                key_data=key_data,
                port=port,
                device_name=device_name if device_name and device_name != host else None,
            )
            if not opened.get("success"):
                return opened
            session_id = opened["session"]["session_id"]
        else:
            with self._lock:
                self._total_sessions_reused += 1

        res = self.execute(session_id, command, timeout=timeout)
        if res.get("success"):
            res["target"] = device_name or host
        return res

    # ------------------------------------------------------------
    # UNIFIED STRUCTURED EVIDENCE CONTRACT INTERFACE
    # ------------------------------------------------------------

    def _execute_evidence_command(self, device_name: str, command: str, evidence_type: str, timeout: float = 20.0) -> dict:
        t0 = time.time()
        res = self.execute_for_device(device_name, command, timeout=timeout)
        if not res.get("success"):
            return {
                "success": False,
                "device_name": device_name,
                "evidence_type": evidence_type,
                "command": command,
                "timestamp": t0,
                "error": res.get("error", "Execution failed"),
            }

        output = res.get("output", "").strip()
        return {
            "success": True,
            "device_name": device_name,
            "evidence_type": evidence_type,
            "command": command,
            "timestamp": t0,
            "latency_ms": res.get("latency_ms", 0.0),
            "raw_output": output,
            "session_id": res.get("session_id"),
        }

    def get_identity(self, device_name: str) -> dict:
        """Retrieves system identity evidence from router."""
        return self._execute_evidence_command(device_name, "/system identity print", "identity")

    def get_interfaces(self, device_name: str) -> dict:
        """Retrieves network interface table evidence."""
        return self._execute_evidence_command(device_name, "/interface print brief", "interfaces")

    def get_routes(self, device_name: str) -> dict:
        """Retrieves routing table evidence."""
        return self._execute_evidence_command(device_name, "/ip route print", "routes")

    def get_ip_addresses(self, device_name: str) -> dict:
        """Retrieves IP addresses evidence."""
        return self._execute_evidence_command(device_name, "/ip address print detail", "ip_addresses")

    def get_firewall_rules(self, device_name: str) -> dict:
        """Retrieves firewall filter rules evidence."""
        return self._execute_evidence_command(device_name, "/ip firewall filter print detail", "firewall_rules")

    def get_nat_rules(self, device_name: str) -> dict:
        """Retrieves firewall NAT rules evidence."""
        return self._execute_evidence_command(device_name, "/ip firewall nat print detail", "nat_rules")

    def get_configuration_snapshot(self, device_name: str, timeout: float = 30.0) -> dict:
        """
        Gathers comprehensive configuration snapshot evidence from device.
        Used for pre-change baselines, audit, and reasoning.
        """
        start_ts = time.time()
        sections = {
            "identity": "/system identity print",
            "resources": "/system resource print",
            "interfaces": "/interface print brief",
            "ip_addresses": "/ip address print detail",
            "routes": "/ip route print",
            "firewall_filter": "/ip firewall filter print count-only",
            "nat_rules": "/ip firewall nat print",
        }

        collected = {}
        errors = []
        for sec, cmd in sections.items():
            res = self.execute_for_device(device_name, cmd, timeout=12.0)
            if res.get("success"):
                collected[sec] = res.get("output", "").strip()
            else:
                err = res.get("error") or "Unknown error"
                errors.append(f"{sec}: {err}")
                collected[sec] = f"[Error: {err}]"

        return {
            "success": len(errors) == 0 or len(collected) > 0,
            "device_name": device_name,
            "evidence_type": "configuration_snapshot",
            "timestamp": start_ts,
            "duration_sec": round(time.time() - start_ts, 2),
            "sections": collected,
            "errors": errors,
        }

    def test_target_credentials(
        self,
        host: str,
        username: str,
        password: Optional[str] = None,
        port: int = 22,
        key_data: Optional[str] = None,
        timeout: float = 4.0,
    ) -> dict:
        """
        Tests SSH credentials and retrieves router identity without displacing or
        terminating active managed sessions.

        Distinguishes:
        - auth_failure: Authentication credentials rejected.
        - timeout: Socket connection or handshake timed out.
        - host_key_failure: Host key mismatch or rejected.
        - unreachable: Network or port level refusal / host unreachable.
        - internal_error: Unexpected internal error during probe.

        Reuses existing active session for (host, port, username) if one is already open and healthy.
        Never logs or exposes passwords or private keys.
        """
        import socket
        import paramiko
        from core.topology_models import sanitize_untrusted_text

        # 1. An existing active session can only satisfy reachability if NO explicit credentials
        # were supplied to test. If explicit credentials (password or key_data) are provided,
        # we MUST test those specific credentials rather than assuming active session matches.
        has_explicit_creds = (password is not None) or (key_data is not None)
        key = self._host_key(host, port, username)

        if not has_explicit_creds:
            with self._lock:
                existing_id = self._host_index.get(key)
                if existing_id and existing_id in self._sessions:
                    session = self._sessions[existing_id]
                    if session.status != STATUS_CLOSED and not session.is_expired():
                        try:
                            cmd_res = self.execute(session_id=existing_id, command="/system identity print", timeout=timeout)
                            if cmd_res.get("success"):
                                ident = None
                                for line in (cmd_res.get("output") or "").splitlines():
                                    if "name:" in line.lower():
                                        ident = line.split(":", 1)[1].strip()
                                        break
                                return {
                                    "success": True,
                                    "authenticated": True,
                                    "identity": ident,
                                    "reused_session": True,
                                    "error_type": None,
                                    "message": "Koneksi & autentikasi berhasil (menggunakan sesi aktif).",
                                }
                        except Exception as exc:
                            logger.warning("Active session probe failed for %s: %s; falling back to direct probe.", key, exc)

        # 2. Ephemeral isolated probe without taking or closing active session slots
        client = paramiko.SSHClient()
        try:
            client.load_system_host_keys()
        except Exception:
            pass

        known_hosts_path = os.getenv("AIRA_KNOWN_HOSTS_FILE")
        if known_hosts_path and os.path.exists(known_hosts_path):
            try:
                client.load_host_keys(known_hosts_path)
            except Exception:
                pass

        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        identity = None
        auth_ok = False
        error_type = None
        error_msg = ""

        try:
            connect_kwargs = {
                "hostname": host,
                "port": port,
                "username": username,
                "look_for_keys": False,
                "allow_agent": False,
                "timeout": float(timeout),
                "banner_timeout": float(timeout),
                "auth_timeout": float(timeout),
            }
            if password is not None:
                connect_kwargs["password"] = password

            if key_data:
                import io
                key_obj = None
                for key_cls in (paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey):
                    try:
                        key_obj = key_cls.from_private_key(io.StringIO(key_data))
                        break
                    except Exception:
                        continue
                if key_obj:
                    connect_kwargs["pkey"] = key_obj

            client.connect(**connect_kwargs)
            auth_ok = True

            # Attempt to retrieve identity
            try:
                _, stdout, _ = client.exec_command("/system identity print", timeout=min(timeout, 3.0))
                out = stdout.read().decode("utf-8", errors="ignore")
                for line in out.splitlines():
                    if "name:" in line.lower():
                        identity = line.split(":", 1)[1].strip()
                        break
            except Exception:
                pass

        except paramiko.AuthenticationException:
            auth_ok = False
            error_type = "auth_failure"
            error_msg = "Koneksi port terbuka, namun autentikasi username/password ditolak."
        except paramiko.BadHostKeyException as exc:
            auth_ok = False
            error_type = "host_key_failure"
            try:
                detail = str(exc)
            except Exception:
                detail = getattr(exc, "hostname", host) or "Host key mismatch"
            error_msg = f"Verifikasi host key SSH gagal: {sanitize_untrusted_text(detail, 100)}"
        except (socket.timeout, TimeoutError):
            auth_ok = False
            error_type = "timeout"
            error_msg = f"Koneksi SSH timed out setelah {timeout} detik."
        except paramiko.SSHException as exc:
            auth_ok = False
            exc_str = str(exc).lower()
            if "time out" in exc_str or "timed out" in exc_str:
                error_type = "timeout"
                error_msg = f"Koneksi SSH timed out setelah {timeout} detik."
            elif "authentication" in exc_str:
                error_type = "auth_failure"
                error_msg = "Koneksi port terbuka, namun autentikasi username/password ditolak."
            elif "host key" in exc_str:
                error_type = "host_key_failure"
                error_msg = f"Verifikasi host key SSH gagal: {sanitize_untrusted_text(str(exc), 100)}"
            else:
                error_type = "internal_error"
                error_msg = f"SSH handshake gagal: {sanitize_untrusted_text(str(exc), 100)}"
        except (OSError, socket.error) as exc:
            auth_ok = False
            error_type = "unreachable"
            error_msg = f"Perangkat tidak dapat dijangkau via SSH: {sanitize_untrusted_text(str(exc), 100)}"
        except Exception as exc:
            auth_ok = False
            error_type = "internal_error"
            error_msg = f"SSH handshake gagal: {sanitize_untrusted_text(str(exc), 100)}"
        finally:
            try:
                client.close()
            except Exception:
                pass

        return {
            "success": True,
            "authenticated": auth_ok,
            "identity": identity,
            "reused_session": False,
            "error_type": error_type,
            "message": error_msg or ("Koneksi & autentikasi berhasil!" if auth_ok else "Host tidak merespons."),
        }

    # ------------------------------------------------------------
    # OBSERVABILITY & STATS
    # ------------------------------------------------------------

    def get_stats(self) -> dict:
        """Returns connection pool metrics and active sessions statistics."""
        with self._lock:
            active_sessions = [s.to_dict() for s in self._sessions.values() if s.status != STATUS_CLOSED]
            backoff_info = {
                k: {
                    "attempts": v["attempts"],
                    "cooldown_remaining": max(0.0, round(v["cooldown_sec"] - (time.time() - v["last_failed_at"]), 1)),
                }
                for k, v in self._backoff.items()
                if (time.time() - v["last_failed_at"]) < v["cooldown_sec"]
            }

        total_commands = sum(s.get("command_count", 0) for s in active_sessions)
        avg_latencies = [s.get("avg_latency_ms", 0.0) for s in active_sessions if s.get("command_count", 0) > 0]
        overall_avg_lat = round(sum(avg_latencies) / max(1, len(avg_latencies)), 2) if avg_latencies else 0.0

        return {
            "active_sessions_count": len(active_sessions),
            "max_concurrent_sessions": MAX_CONCURRENT_SESSIONS,
            "total_sessions_opened": self._total_sessions_opened,
            "total_sessions_reused": self._total_sessions_reused,
            "total_commands_executed": total_commands,
            "overall_avg_latency_ms": overall_avg_lat,
            "active_backoffs": backoff_info,
            "sessions": active_sessions,
        }

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
    # IDLE & LIFETIME MONITOR (background thread)
    # ------------------------------------------------------------

    def _idle_monitor_loop(self):
        while not self._monitor_stop.wait(MONITOR_INTERVAL_SECONDS):
            try:
                self._check_idle_sessions()
            except Exception:
                logger.exception("idle_monitor_loop error (diabaikan)")

    def _check_idle_sessions(self):
        with self._lock:
            idle_candidates = [
                s.session_id for s in self._sessions.values()
                if s.status != STATUS_CLOSED and s.idle_seconds() > IDLE_TIMEOUT_SECONDS
            ]
            expired_candidates = [
                s.session_id for s in self._sessions.values()
                if s.status != STATUS_CLOSED and s.status != STATUS_BUSY and s.is_expired()
            ]

        for session_id in idle_candidates:
            logger.info("Session %s idle > %ds, menutup otomatis.", session_id, IDLE_TIMEOUT_SECONDS)
            self.close_connection(session_id, reason="idle_timeout")
            self._publish("connection.timeout", data={"session_id": session_id, "reason": "idle_timeout"})

        for session_id in expired_candidates:
            if session_id not in idle_candidates:
                logger.info("Session %s expired (lifetime > %ds), menutup otomatis untuk refresh.", session_id, MAX_SESSION_LIFETIME_SECONDS)
                self.close_connection(session_id, reason="max_lifetime")
                self._publish("connection.timeout", data={"session_id": session_id, "reason": "max_lifetime"})

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
