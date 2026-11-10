"""
core/vae/composer.py — VERA Adaptive Experience (VAE) Experience Composer.

Transforms narrative intelligence, raw tool outputs, execution steps,
and planned layouts into high-fidelity, validated VAE Protocol v2 payloads.
Adheres strictly to the Narrative-First Response Policy.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict, List, Optional
import uuid

from core.vae.models import VaeBlock, VaeBlockType, VaePayload
from core.vae.planner import ExperiencePlan, ExperiencePlanner, VaeIntent
from core.vae.protocol import validate_vae_payload

logger = logging.getLogger("vera.vae.composer")


class ExperienceComposer:
    """
    Composes full VAE payloads containing both narrative conclusions
    and rich, structured visual representations.
    """

    def __init__(self, planner: Optional[ExperiencePlanner] = None):
        self.planner = planner or ExperiencePlanner()

    @staticmethod
    def sanitize_narrative(text: str) -> str:
        """
        Cleans narrative text by removing leaking UI artifacts, raw metadata phrases,
        and fixing malformed HTML linebreaks into clean markdown.
        """
        if not text:
            return ""

        cleaned = text

        # 1. Purge leaking tool usage artifacts (e.g., "1 tool digunakan svg", "2 tools used")
        cleaned = re.sub(
            r"(?i)(?:\b\d+\s+tool(?:s)?\s+(?:digunakan|used)(?:\s+\w+)?\.?|\btool\s+digunakan\b)",
            "",
            cleaned,
        )

        # 2. Convert <br> or <br/> or <br /> to standard newlines
        cleaned = re.sub(r"<br\s*/?>", "\n", cleaned, flags=re.IGNORECASE)

        # 3. Collapse 3+ consecutive newlines into 2
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

        return cleaned.strip()

    @staticmethod
    def _parse_size_mb(val_str: str) -> float:
        """Parses strings like '54.3MiB', '1024KiB', '2.1GiB' into MB float."""
        if not val_str:
            return 0.0
        val_str = str(val_str).strip()
        m = re.match(r"^([\d.]+)\s*([KMGkmg]?)i?[Bb]?", val_str)
        if not m:
            try:
                return float(val_str) / (1024 * 1024)
            except Exception:
                return 0.0
        num = float(m.group(1))
        unit = (m.group(2) or "").upper()
        if unit == "K":
            return round(num / 1024.0, 2)
        elif unit == "G":
            return round(num * 1024.0, 2)
        return round(num, 2)

    def extract_system_resources(self, steps: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Extracts CPU, Memory, Disk, Uptime, and OS details from tool outputs."""
        for step in reversed(steps):
            t_name = (step.get("tool") or step.get("name") or "").lower()
            if any(k in t_name for k in ("resource", "resources", "system_info")):
                raw = step.get("output") or step.get("result") or {}
                text = ""
                if isinstance(raw, dict):
                    text = raw.get("output") or str(raw)
                    # If dict already has typed fields
                    if "cpu_load" in raw or "cpu-load" in raw:
                        cpu = raw.get("cpu_load") or raw.get("cpu-load") or 0
                        return {
                            "cpu_load_pct": float(str(cpu).replace("%", "")),
                            "free_memory_mb": self._parse_size_mb(raw.get("free-memory") or raw.get("free_memory")),
                            "total_memory_mb": self._parse_size_mb(raw.get("total-memory") or raw.get("total_memory")),
                            "uptime": str(raw.get("uptime") or "N/A"),
                            "version": str(raw.get("version") or "RouterOS"),
                            "board_name": str(raw.get("board-name") or raw.get("board_name") or "RouterOS Device"),
                        }
                elif isinstance(raw, str):
                    text = raw

                if text:
                    res: Dict[str, Any] = {}
                    for line in text.splitlines():
                        if ":" in line:
                            k, v = line.split(":", 1)
                            res[k.strip().lower().replace(" ", "-")] = v.strip()

                    cpu_str = res.get("cpu-load", "0%").replace("%", "")
                    try:
                        cpu_load = float(cpu_str)
                    except ValueError:
                        cpu_load = 0.0

                    total_mem = self._parse_size_mb(res.get("total-memory", "0"))
                    free_mem = self._parse_size_mb(res.get("free-memory", "0"))
                    used_mem = max(0.0, round(total_mem - free_mem, 2))
                    mem_pct = round((used_mem / total_mem * 100), 1) if total_mem > 0 else 0.0

                    total_hdd = self._parse_size_mb(res.get("total-hdd-space", "0"))
                    free_hdd = self._parse_size_mb(res.get("free-hdd-space", "0"))
                    used_hdd = max(0.0, round(total_hdd - free_hdd, 2))
                    hdd_pct = round((used_hdd / total_hdd * 100), 1) if total_hdd > 0 else 0.0

                    return {
                        "cpu_load_pct": cpu_load,
                        "cpu_status": "critical" if cpu_load > 85 else ("warning" if cpu_load > 70 else "healthy"),
                        "total_memory_mb": total_mem,
                        "free_memory_mb": free_mem,
                        "used_memory_mb": used_mem,
                        "memory_usage_pct": mem_pct,
                        "memory_status": "critical" if mem_pct > 90 else ("warning" if mem_pct > 75 else "healthy"),
                        "total_hdd_mb": total_hdd,
                        "free_hdd_mb": free_hdd,
                        "used_hdd_mb": used_hdd,
                        "hdd_usage_pct": hdd_pct,
                        "uptime": res.get("uptime", "N/A"),
                        "version": res.get("version", "N/A"),
                        "board_name": res.get("board-name", res.get("platform", "MikroTik Router")),
                        "cpu_count": res.get("cpu-count", "1"),
                        "cpu_frequency": res.get("cpu-frequency", "N/A"),
                    }
        return None

    def extract_interface_list(self, steps: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
        """Extracts interface states from tool outputs."""
        for step in reversed(steps):
            t_name = (step.get("tool") or step.get("name") or "").lower()
            if "interface" in t_name:
                raw = step.get("output") or step.get("result") or {}
                if isinstance(raw, dict) and "interfaces" in raw and isinstance(raw["interfaces"], list):
                    return raw["interfaces"]

                text = raw.get("output") if isinstance(raw, dict) else (raw if isinstance(raw, str) else "")
                if text:
                    interfaces = []
                    for line in text.splitlines():
                        line_str = line.strip()
                        if not line_str or line_str.startswith("#") or line_str.startswith("Flags:"):
                            continue
                        parts = line_str.split()
                        if len(parts) >= 2:
                            # RouterOS format: [index] [flags] [name] [type] ...
                            # e.g., "0  R ether1 ether 1500" or "0 ether1 ether 1500" or "R ether1 ether 1500"
                            idx = 0
                            if parts[idx].isdigit():
                                idx += 1
                            flags = ""
                            if idx < len(parts) and (any(c in parts[idx] for c in "RXDSA") or parts[idx] in ("R", "X", "D", "S", "A")):
                                flags = parts[idx]
                                idx += 1
                            name = parts[idx] if idx < len(parts) else parts[0]
                            is_running = "R" in flags or "running" in line_str.lower()
                            itype = "ether"
                            for cand in ("ether", "wlan", "bridge", "vlan", "sfp", "pppoe"):
                                if cand in line_str.lower():
                                    itype = cand
                                    break
                            interfaces.append({
                                "name": name,
                                "type": itype,
                                "status": "UP" if is_running else "DOWN",
                                "running": is_running,
                                "raw": line_str,
                            })
                    if interfaces:
                        return interfaces
        return None

    def extract_traceroute_hops(self, steps: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Extracts traceroute hops from diagnostics outputs."""
        for step in reversed(steps):
            t_name = (step.get("tool") or step.get("name") or "").lower()
            if "traceroute" in t_name or "tracepath" in t_name:
                raw = step.get("output") or step.get("result") or {}
                if isinstance(raw, dict):
                    if "hops" in raw and isinstance(raw["hops"], list) and raw["hops"]:
                        return {
                            "target": raw.get("target", "Target Host"),
                            "reached": raw.get("reached", False),
                            "total_hops": raw.get("total_hops", len(raw["hops"])),
                            "hops": raw["hops"],
                        }
        return None

    def extract_routing_table(self, steps: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
        """Extracts routing entries from route outputs."""
        for step in reversed(steps):
            t_name = (step.get("tool") or step.get("name") or "").lower()
            if "route" in t_name:
                raw = step.get("output") or step.get("result") or {}
                if isinstance(raw, dict) and "routes" in raw and isinstance(raw["routes"], list):
                    return raw["routes"]
                text = raw.get("output") if isinstance(raw, dict) else (raw if isinstance(raw, str) else "")
                if text:
                    routes = []
                    for line in text.splitlines():
                        line_str = line.strip()
                        if not line_str or line_str.startswith("#") or line_str.startswith("Flags:"):
                            continue
                        parts = line_str.split()
                        if len(parts) >= 2:
                            dst = ""
                            gateway = ""
                            for p in parts:
                                if "/" in p and not dst:
                                    dst = p
                                elif ("." in p or ":" in p) and dst and not gateway:
                                    gateway = p
                            if dst:
                                routes.append({
                                    "dst_address": dst,
                                    "gateway": gateway or "connected",
                                    "flags": parts[0] if parts[0].isalpha() else "A S",
                                    "status": "ACTIVE" if "A" in parts[0] else "INACTIVE",
                                })
                    if routes:
                        return routes
        return None

    def compose(
        self,
        answer: str,
        steps: Optional[List[Dict[str, Any]]] = None,
        interaction_schema: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        query: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> VaePayload:
        """
        Executes full planning and composition pipeline.
        Returns a validated VaePayload adhering to Protocol v2.
        """
        steps = steps or []
        context = context or {}

        # 1. Sanitize narrative
        clean_narrative = self.sanitize_narrative(answer)

        # 2. Plan visual experience
        effective_query = query or (steps[0].get("tool", "") if steps else clean_narrative[:60])
        plan = self.planner.plan(
            query=effective_query,
            steps=steps,
            interaction_schema=interaction_schema,
            context=context,
        )

        blocks: List[VaeBlock] = []

        # 3. Block 0: Primary Narrative (Always present)
        if clean_narrative:
            blocks.append(
                VaeBlock(
                    id=f"blk_txt_{uuid.uuid4().hex[:8]}",
                    type=VaeBlockType.MARKDOWN.value,
                    data={"content": clean_narrative},
                    metadata={"layout": "full-width"},
                )
            )

        # 4. Generate Structured Visual Blocks according to Plan
        if plan.intent == VaeIntent.RESOURCE_INSPECTION:
            res_data = self.extract_system_resources(steps)
            if res_data:
                # Block: resource-gauge
                blocks.append(
                    VaeBlock(
                        id=f"blk_gauge_{uuid.uuid4().hex[:8]}",
                        type=VaeBlockType.RESOURCE_GAUGE.value,
                        data={
                            "device": res_data.get("board_name", "Router"),
                            "cpu": {
                                "value": res_data.get("cpu_load_pct", 0),
                                "unit": "%",
                                "status": res_data.get("cpu_status", "healthy"),
                            },
                            "memory": {
                                "value": res_data.get("memory_usage_pct", 0),
                                "used_mb": res_data.get("used_memory_mb", 0),
                                "total_mb": res_data.get("total_memory_mb", 0),
                                "status": res_data.get("memory_status", "healthy"),
                            },
                            "disk": {
                                "value": res_data.get("hdd_usage_pct", 0),
                                "used_mb": res_data.get("used_hdd_mb", 0),
                                "total_mb": res_data.get("total_hdd_mb", 0),
                                "status": "healthy",
                            },
                        },
                        metadata={
                            "confidence": plan.confidence,
                            "source_device": plan.primary_device,
                            "layout": "grid",
                        },
                    )
                )
                # Block: metric-grid
                blocks.append(
                    VaeBlock(
                        id=f"blk_grid_{uuid.uuid4().hex[:8]}",
                        type=VaeBlockType.METRIC_GRID.value,
                        data={
                            "items": [
                                {
                                    "title": "CPU Load",
                                    "value": res_data.get("cpu_load_pct", 0),
                                    "unit": "%",
                                    "status": res_data.get("cpu_status", "healthy"),
                                },
                                {
                                    "title": "Free RAM",
                                    "value": res_data.get("free_memory_mb", 0),
                                    "unit": "MB",
                                    "status": res_data.get("memory_status", "healthy"),
                                },
                                {
                                    "title": "Uptime",
                                    "value": res_data.get("uptime", "N/A"),
                                    "unit": "",
                                    "status": "healthy",
                                },
                                {
                                    "title": "OS Version",
                                    "value": res_data.get("version", "RouterOS"),
                                    "unit": "",
                                    "status": "healthy",
                                },
                            ]
                        },
                        metadata={"layout": "grid"},
                    )
                )

        elif plan.intent == VaeIntent.INTERFACE_INSPECTION:
            interfaces = self.extract_interface_list(steps)
            if interfaces:
                blocks.append(
                    VaeBlock(
                        id=f"blk_iface_{uuid.uuid4().hex[:8]}",
                        type=VaeBlockType.INTERFACE_STATUS.value,
                        data={
                            "device": plan.primary_device or "Router",
                            "interfaces": interfaces,
                            "total_count": len(interfaces),
                            "up_count": sum(1 for i in interfaces if i.get("status") == "UP"),
                        },
                        metadata={"confidence": plan.confidence, "layout": "full-width"},
                    )
                )

        elif plan.intent == VaeIntent.NETWORK_DIAGNOSTICS:
            trace_data = self.extract_traceroute_hops(steps)
            if trace_data:
                blocks.append(
                    VaeBlock(
                        id=f"blk_trace_{uuid.uuid4().hex[:8]}",
                        type=VaeBlockType.HOP_TRACEROUTE.value,
                        data=trace_data,
                        metadata={"confidence": plan.confidence, "layout": "full-width"},
                    )
                )

        elif plan.intent == VaeIntent.ROUTING_ANALYSIS:
            routes = self.extract_routing_table(steps)
            if routes:
                blocks.append(
                    VaeBlock(
                        id=f"blk_route_{uuid.uuid4().hex[:8]}",
                        type=VaeBlockType.ROUTE_TABLE.value,
                        data={
                            "device": plan.primary_device or "Router",
                            "routes": routes,
                            "total_routes": len(routes),
                        },
                        metadata={"confidence": plan.confidence, "layout": "full-width"},
                    )
                )

        # 5. DIO Interaction & Action Cards
        if interaction_schema and isinstance(interaction_schema, dict):
            mode = interaction_schema.get("mode", "form")
            if mode in ("action", "approval", "danger_confirm"):
                blocks.append(
                    VaeBlock(
                        id=f"blk_act_{interaction_schema.get('id', uuid.uuid4().hex[:8])}",
                        type=VaeBlockType.ACTION_CARD.value,
                        data={
                            "action_id": interaction_schema.get("id"),
                            "title": interaction_schema.get("title", "Konfirmasi Tindakan Jaringan"),
                            "description": interaction_schema.get("description", ""),
                            "target_device": plan.primary_device,
                            "command": interaction_schema.get("command"),
                            "risk_level": interaction_schema.get("risk_level", "medium"),
                            "requires_confirmation": True,
                        },
                        metadata={"mode": mode},
                    )
                )
            else:
                blocks.append(
                    VaeBlock(
                        id=f"blk_dio_{interaction_schema.get('id', uuid.uuid4().hex[:8])}",
                        type=VaeBlockType.DIO_INTERACTION.value,
                        data={"schema": interaction_schema},
                        metadata={"mode": mode},
                    )
                )

        # 6. Workflow Recovery Engine (Detect tool failures & formulate actionable recovery)
        recovery_plan = None
        for step in reversed(steps):
            is_fail = False
            out = step.get("output") or step.get("result")
            if step.get("success") is False or step.get("status") in ("failed", "error"):
                is_fail = True
            elif isinstance(out, dict) and (out.get("success") is False or out.get("error")):
                is_fail = True
            elif isinstance(out, str) and any(w in out.lower() for w in ("sudah ada", "already exists", "connection refused", "permission denied")):
                t_name = (step.get("tool") or step.get("name") or "").lower()
                if t_name in ("add_device", "create_device", "connect_device", "apply_config"):
                    is_fail = True

            t_name = (step.get("tool") or step.get("name") or "").lower()
            # Diagnostic and informational tools report observations, never triggering workflow recovery
            if t_name in ("ping", "traceroute", "web_search", "search_web", "query_database", "read_file", "view_file", "show_inventory"):
                is_fail = False

            if is_fail:
                try:
                    from core.vae.recovery import get_recovery_planner
                    rec_planner = get_recovery_planner()
                    t_name = step.get("tool") or step.get("name") or "unknown_tool"
                    t_args = step.get("args") or step.get("parameters") or {}
                    recovery_plan = rec_planner.plan_recovery(
                        tool_name=t_name,
                        tool_input=t_args,
                        error_output=out or step.get("error") or "Operation failed",
                        session_id=session_id,
                        context=context,
                    )
                except Exception as exc:
                    logger.warning("Recovery planning skipped due to error: %s", exc)
                break

        if recovery_plan:
            blocks.append(
                VaeBlock(
                    id=f"blk_rec_{recovery_plan.workflow_id}",
                    type=VaeBlockType.WORKFLOW_RECOVERY.value,
                    data=recovery_plan.to_dict(),
                    metadata={
                        "category": recovery_plan.error_classification.category.value,
                        "layout": "full-width",
                    },
                )
            )

        # 7. Assemble Payload Envelope
        payload_metadata: Dict[str, Any] = {
            "intent": plan.intent.value,
            "confidence": plan.confidence,
            "step_count": len(steps),
        }
        if session_id:
            payload_metadata["session_id"] = session_id
        if plan.primary_device:
            payload_metadata["primary_device"] = plan.primary_device

        payload = VaePayload(
            blocks=blocks,
            protocol="vae",
            version="2.0",
            created_at=time.time(),
            metadata=payload_metadata,
        )

        # Validate against protocol contract
        valid, validated_payload, issues = validate_vae_payload(payload.to_dict())
        if not valid:
            logger.warning("VAE Composition produced validation issues: %s", issues)

        return validated_payload or payload
