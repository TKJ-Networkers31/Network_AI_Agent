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

import logging
import time
from typing import Any, Optional

from agents.rei.planner import Planner
from agents.rei.registry import REI_TOOLS, REI_TOOL_CATEGORY, REI_TOOL_SCHEMAS
from agents.rei import dio_tools as dio
from agents.rei import maps_tools as mt
from agents.akane.registry import (
    AKANE_TOOLS, AKANE_DANGEROUS_TOOLS, AKANE_TOOL_CATEGORY, AKANE_TOOL_SCHEMAS,
)
from agents.hikari.registry import (
    HIKARI_TOOLS, HIKARI_DANGEROUS_TOOLS, HIKARI_TOOL_CATEGORY, HIKARI_TOOL_SCHEMAS,
)

logger = logging.getLogger("aira.orchestrator")

AGENT_TOOL_MAP: dict[str, Any] = {**AKANE_TOOLS, **HIKARI_TOOLS, **REI_TOOLS, **mt.MAPS_TOOLS}
AGENT_TOOL_CATEGORY: dict[str, str] = {
    **AKANE_TOOL_CATEGORY, **HIKARI_TOOL_CATEGORY, **REI_TOOL_CATEGORY, **mt.MAPS_TOOL_CATEGORY,
}
AGENT_TOOL_SCHEMAS: list[dict] = [
    *AKANE_TOOL_SCHEMAS, *HIKARI_TOOL_SCHEMAS, *REI_TOOL_SCHEMAS, *mt.MAPS_TOOL_SCHEMAS,
]
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


class Orchestrator:

    def __init__(self):
        self.planner = Planner(
            tool_schemas=AGENT_TOOL_SCHEMAS,
            tool_category=AGENT_TOOL_CATEGORY,
            dangerous_tools=DANGEROUS_TOOLS,
        )

    def route(
        self, user_input: str, memory, cancel_event=None, selected_model=None,
        context=None, stream: bool = False,
    ) -> dict:
        start = time.perf_counter()
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

        try:
            if name in DEVICE_TOOLS:
                early_result, arguments = self._prepare_device_args(name, arguments)

                if early_result is not None:
                    return early_result

            return AGENT_TOOL_MAP[name](**arguments)
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
                "error": "Belum ada perangkat di inventory (inventory/router.yaml). Sampaikan ke user.",
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