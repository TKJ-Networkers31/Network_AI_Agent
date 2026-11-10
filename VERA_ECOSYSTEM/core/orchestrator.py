"""
core/orchestrator.py — otak routing AIRA.
User -> AIRA -> REI (Planning) -> AKANE/HIKARI/REI-tools -> AIRA -> User

route() menerima:
  - cancel_event   : threading.Event untuk tombol Stop (diteruskan ke Planner)
  - selected_model : SelectedModel dari Model Router (dipilih Brain)
  - context        : AIRAContext dari Context Builder (disusun Brain), diteruskan
                     apa adanya ke Planner
  - stream         : bool (Sprint 2.5) - minta provider streaming; diteruskan
                     apa adanya ke Planner. Default False = perilaku lama.
Orchestrator tidak memilih model dan tidak menyusun konteks. Tidak ada lagi callback on_event: event
realtime lewat Event Bus.

Integrasi APCE + DIO (device resolution):
  Tool jaringan yang mewajibkan 'device_name' (dideteksi dari skema, bukan
  daftar manual) dilewatkan _prepare_device_args() sebelum dieksekusi:
    - device_name valid                    -> dipakai (nama dikanonkan)
    - kosong + hanya 1 device di inventory -> otomatis dipakai
    - kosong/tidak dikenal + >1 device     -> AIRA bertanya lewat DIO
                                              (pilihan perangkat); Planner
                                              menampilkan form & menunggu
    - inventory kosong                     -> error jelas ke LLM
  Koneksi SSH sendiri tetap dikelola AIRA Persistent Connection Engine
  (agents/akane/connection_manager.py, lewat agents/akane/network_tools.py).

Google Maps: tool maps_* (agents/rei/maps_tools.py) digabung di sini.
"""

import json
import logging
import re
import time
from typing import Any, Optional

from agents.rei.planner import Planner
from agents.rei.registry import REI_TOOLS, REI_TOOL_CATEGORY, REI_TOOL_SCHEMAS
from agents.rei import dio_tools as dio
from agents.rei import maps_tools as mt
from agents.rei import artifact_tools as art
from agents.akane.registry import (
    AKANE_TOOLS, AKANE_DANGEROUS_TOOLS, AKANE_TOOL_CATEGORY, AKANE_TOOL_SCHEMAS,
)
from agents.hikari.registry import (
    HIKARI_TOOLS, HIKARI_DANGEROUS_TOOLS, HIKARI_TOOL_CATEGORY, HIKARI_TOOL_SCHEMAS,
)
from core.dio.parameter_resolver import (
    DIOParameterResolver,
    ParameterStatus,
    build_device_registration_schema,
)

logger = logging.getLogger("aira.orchestrator")


def _deduplicate_schemas(schemas: list) -> list:
    """Deduplicates tool schema definitions by function name to satisfy strict LLM APIs."""
    seen: set[str] = set()
    unique: list = []
    for entry in schemas:
        name = entry.get("function", {}).get("name") if isinstance(entry, dict) else None
        if not name or name not in seen:
            if name:
                seen.add(name)
            unique.append(entry)
    return unique


AGENT_TOOL_MAP = {
    **AKANE_TOOLS,
    **HIKARI_TOOLS,
    **REI_TOOLS,
    **mt.MAPS_TOOLS,
}

AGENT_TOOL_CATEGORY = {
    **AKANE_TOOL_CATEGORY,
    **HIKARI_TOOL_CATEGORY,
    **REI_TOOL_CATEGORY,
    **mt.MAPS_TOOL_CATEGORY,
}

AGENT_TOOL_SCHEMAS = _deduplicate_schemas([
    *AKANE_TOOL_SCHEMAS,
    *HIKARI_TOOL_SCHEMAS,
    *REI_TOOL_SCHEMAS,
    *mt.MAPS_TOOL_SCHEMAS,
])

DANGEROUS_TOOLS: set[str] = set(AKANE_DANGEROUS_TOOLS) | set(HIKARI_DANGEROUS_TOOLS)


def _device_tool_names(schemas) -> set[str]:
    """Tool yang mewajibkan device_name, dibaca dari skema."""
    names: set[str] = set()

    for entry in schemas:
        function = entry.get("function", {}) if isinstance(entry, dict) else {}
        required = (function.get("parameters") or {}).get("required") or []

        if function.get("name") and "device_name" in required:
            names.add(function["name"])

    return names


DEVICE_TOOLS: set[str] = _device_tool_names(AGENT_TOOL_SCHEMAS)

TOOL_REQUIRED_PERMISSIONS: dict[str, str] = {
    # Network Configuration & Mutation
    "apply_config": "config.apply",
    "plan_config_change": "config.apply",
    "execute_router_command": "config.apply",
    "update_device": "devices.update",
    "delete_device": "devices.delete",
    "add_device": "devices.create",
    "add_credential": "devices.update",
    "link_credential": "devices.update",

    # Network Inventory & Topology
    "list_devices": "inventory.read",
    "connect_device": "devices.read",
    "disconnect_device": "devices.read",
    "list_connections": "devices.read",
    "list_credentials": "devices.read",
    "get_network_topology": "topology.read",

    # Network Device Telemetry & Status
    "get_interfaces": "devices.read",
    "get_ip_addresses": "devices.read",
    "get_routes": "devices.read",
    "get_arp": "devices.read",
    "get_dns": "devices.read",
    "get_nat": "devices.read",
    "get_dhcp_client": "devices.read",
    "get_dhcp_server": "devices.read",
    "get_firewall": "devices.read",
    "get_neighbors": "devices.read",
    "get_resources": "devices.read",
    "get_identity": "devices.read",
    "generate_router_report": "devices.read",

    # Diagnostics
    "ping": "devices.diagnostics",
    "traceroute": "devices.diagnostics",
    "nslookup": "devices.diagnostics",
    "diagnose_network_route": "devices.diagnostics",
    "auto_diagnose_network": "devices.diagnostics",
    "troubleshoot_network_node": "devices.diagnostics",
    "find_network_path": "devices.diagnostics",

    # NMS Telemetry
    "snmp_get_system_info": "nms.read",
    "snmp_get_interface_traffic": "nms.metrics.read",

    # SOC Security Audits
    "audit_network_firewall": "soc.events.read",
    "audit_network_vlan": "soc.events.read",
}


def _is_device_registration_request(text: str) -> bool:
    clean = (text or "").strip().lower()

    # Section 4: Conceptual, explanatory, or configuration questions must NEVER trigger onboarding form
    conceptual_markers = [
        "bagaimana", "cara", "apa itu", "jelaskan", "mengapa", "kenapa", "apakah",
        "tutorial", "panduan", "konsep", "bisa kah", "bisakah", "contoh", "teori",
        "mac", "mac-address", "mac address", "arp", "bridge", "switch", "port-security",
        "filter", "whitelist", "blacklist", "dhcp lease", "access-list", "access list",
    ]
    if any(marker in clean for marker in conceptual_markers):
        return False

    add_words = ["tambah", "tambahkan", "daftarkan", "register", "onboard"]
    dev_words = ["router baru", "device baru", "perangkat baru", "node baru", "ke inventory", "di inventory"]
    has_add = any(w in clean for w in add_words)
    has_dev = any(w in clean for w in dev_words)

    # If IP is already provided, let normal execution proceed
    has_ip = bool(re.search(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", clean))
    return has_add and has_dev and not has_ip


def _parse_form_submission_values(text: str) -> Optional[dict]:
    """Extracts values from DIO form submission message if present."""
    if not text:
        return None

    # Format 1: DIO JSON system message ("Instruksi sistem: User baru saja mengisi form...")
    if "Instruksi sistem: User baru saja mengisi form" in text:
        match = re.search(r"dengan data berikut:\s*(\{.*?\})", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                pass

    # Format 2: Direct form submission marker "[Form Submission: add_device]" or "[Form Submission...]"
    if "[Form Submission" in text:
        data = {}
        for line in text.splitlines():
            line = line.strip()
            if ":" in line and not line.startswith("["):
                k, v = line.split(":", 1)
                data[k.strip()] = v.strip()
        if data:
            return data

    return None


class Orchestrator:

    def __init__(self):
        self.planner = Planner(
            tool_schemas=AGENT_TOOL_SCHEMAS,
            tool_category=AGENT_TOOL_CATEGORY,
            dangerous_tools=DANGEROUS_TOOLS,
        )
        self.parameter_resolver = DIOParameterResolver(AGENT_TOOL_SCHEMAS)

    def route(
        self, user_input: str, memory, cancel_event=None, selected_model=None,
        context=None, stream: bool = False,
    ) -> dict:
        start = time.perf_counter()

        # 1. Direct Schema-Driven Form Generation for Device Registration (Phase F.2)
        if _is_device_registration_request(user_input):
            schema = build_device_registration_schema()
            answer = "Baik, saya akan membantu mendaftarkan perangkat. Silakan lengkapi informasi berikut melalui form interaktif:"
            memory.add_user(user_input)
            memory.add_message({"role": "assistant", "content": answer})
            return {
                "answer": answer,
                "steps": [{
                    "type": "tool_call",
                    "name": "request_structured_input",
                    "category": "interaction",
                    "arguments": {"intent": "add_device", "title": "Register Network Device"},
                    "success": True,
                    "duration": 0.02,
                    "result_preview": "Form pendaftaran perangkat ditampilkan.",
                }],
                "token_usage": None,
                "session_token_usage": None,
                "error": False,
                "duration": round(time.perf_counter() - start, 3),
                "interaction_schema": schema,
            }

        # 2. Form Submission Handling for Device Registration (Phase F.2)
        sub_values = _parse_form_submission_values(user_input)
        if sub_values and "name" in sub_values and "host" in sub_values:
            from core.events import event_scope
            user_id_scope = None
            if isinstance(context, dict):
                user_id_scope = context.get("user_id") or context.get("username")
            elif hasattr(context, "user_id"):
                user_id_scope = getattr(context, "user_id", None)
            elif hasattr(context, "username"):
                user_id_scope = getattr(context, "username", None)

            with event_scope(user_id=user_id_scope or "lingga_admin"):
                tool_res = self._execute_tool("add_device", sub_values)
            if tool_res.get("success"):
                dev = tool_res.get("device", {})
                d_name = dev.get("name") or sub_values.get("name")
                d_host = dev.get("host") or sub_values.get("host")
                d_type = dev.get("device_type") or sub_values.get("device_type") or "mikrotik"
                answer = f"Perangkat **{d_name}** ({d_host}, tipe: `{d_type}`) berhasil didaftarkan ke inventory."
            else:
                err = tool_res.get("error", "Gagal mendaftarkan perangkat.")
                answer = f"Gagal mendaftarkan perangkat ke inventory: {err}"

            memory.add_user(user_input)
            memory.add_message({"role": "assistant", "content": answer})
            return {
                "answer": answer,
                "steps": [{
                    "type": "tool_call",
                    "name": "add_device",
                    "category": "inventory",
                    "arguments": {k: ("***" if "pass" in k.lower() else v) for k, v in sub_values.items()},
                    "success": bool(tool_res.get("success")),
                    "duration": 0.05,
                    "result_preview": str(tool_res),
                }],
                "token_usage": None,
                "session_token_usage": None,
                "error": not tool_res.get("success"),
                "duration": round(time.perf_counter() - start, 3),
                "interaction_schema": None,
            }

        # 3. Standard Planner & Reasoning Loop
        result = self.planner.run(
            user_input, memory,
            tool_executor=self._execute_tool,
            cancel_event=cancel_event,
            selected_model=selected_model,
            context=context,
            stream=stream,
        )
        result["duration"] = round(time.perf_counter() - start, 3)
        return result

    # ------------------------------------------------------------ tools

    def _execute_tool(self, name: str, arguments: dict) -> dict:
        if name not in AGENT_TOOL_MAP:
            return {"success": False, "error": f"Tool '{name}' tidak dikenal oleh orchestrator."}

        # Backend-enforced AI Tool Authorization (Phase F.1)
        required_perm = TOOL_REQUIRED_PERMISSIONS.get(name)
        if required_perm:
            from core.events import current_event_scope
            scope = current_event_scope()
            user_id = scope.get("user_id")
            if not user_id or user_id == "guest_anonymous":
                return {
                    "success": False,
                    "tool": name,
                    "error": f"Izin Ditolak: Autentikasi akun diperlukan untuk menjalankan tool '{name}'.",
                }
            from core.tenant.rbac_service import get_rbac_service
            rbac_svc = get_rbac_service()
            if not rbac_svc.has_permission(user_id, required_perm):
                return {
                    "success": False,
                    "tool": name,
                    "error": f"Izin Ditolak (Permission Denied): Akun Anda tidak memiliki izin '{required_perm}' yang diperlukan untuk menjalankan tool '{name}'. Silakan hubungi administrator jika Anda memerlukan akses ini.",
                }

        # Universal DIO Parameter Resolution & Schema Validation Barrier
        inventory_devices = None
        try:
            inv_res = AKANE_TOOLS["list_devices"]()
            if inv_res.get("success"):
                inventory_devices = inv_res.get("devices") or []
        except Exception:
            pass

        resolution = self.parameter_resolver.resolve(
            tool_name=name,
            arguments=arguments,
            inventory_devices=inventory_devices,
        )

        if not resolution.can_execute:
            return resolution.to_early_tool_result()

        exec_args = resolution.resolved_arguments

        try:
            return AGENT_TOOL_MAP[name](**exec_args)
        except Exception as exc:
            logger.exception("Tool '%s' gagal", name)
            return {"success": False, "tool": name, "error": str(exc)}

    def _prepare_device_args(self, tool_name: str, arguments: dict) -> "tuple[Optional[dict], dict]":
        """
        Return (early_result, arguments). early_result tidak None berarti tool
        TIDAK dieksekusi dan hasil itu langsung dikembalikan ke Planner
        (pertanyaan DIO atau error).
        """
        inventory = AKANE_TOOLS["list_devices"]()

        if not inventory.get("success"):
            return {
                "success": False, "tool": tool_name,
                "error": f"Gagal membaca inventory perangkat: {inventory.get('error')}",
            }, arguments

        devices = inventory.get("devices") or []

        if not devices:
            return {
                "success": False, "tool": tool_name,
                "error": "Belum ada perangkat di inventory. Tambahkan perangkat lewat tab Devices atau minta AIRA untuk mendaftarkannya.",
            }, arguments

        given = str(arguments.get("device_name") or "").strip()
        lowered = {str(d["name"]).lower(): d["name"] for d in devices}

        if given and given.lower() in lowered:
            return None, {**arguments, "device_name": lowered[given.lower()]}

        if not given and len(devices) == 1:
            return None, {**arguments, "device_name": devices[0]["name"]}

        reason = (
            f"Perangkat '{given}' tidak ada di inventory. Pilih salah satu:"
            if given else "Perangkat mana yang mau dicek?"
        )

        return dio.request_device_choice(tool_name, devices, reason=reason), arguments