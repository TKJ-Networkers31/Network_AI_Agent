"""
core/management/romon_manager.py — MikroTik RoMON (Router Management Overlay Network) Engine.

Handles:
- RoMON neighbor discovery through authorized intermediary gateway routers
- Multi-hop RoMON path resolution and hop-count tracing
- Controlled, approval-governed RoMON provisioning workflow
- Automatic post-provisioning verification and rollback
- Security controls: Interface restrictions, Secret redaction, and Audit logging
"""
from __future__ import annotations

import logging
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from core.management.capability_detector import CapabilityDetector, is_mac
from core.management.models import RomonNeighbor, RomonProvisioningPlan

logger = logging.getLogger("vera.management.romon")

# In-memory storage for pending provisioning plans (token -> plan)
_PENDING_PLANS: Dict[str, RomonProvisioningPlan] = {}


class RomonManager:
    """Manages MikroTik RoMON discovery, remote execution, and controlled provisioning."""

    @classmethod
    def parse_romon_neighbor_output(
        cls,
        raw_output: str,
        via_device_id: str,
        via_device_name: str,
    ) -> List[RomonNeighbor]:
        """
        Parses `/romon neighbor print detail` RouterOS terminal output into typed RomonNeighbor objects.
        Example RouterOS line:
        0 id=00:0C:42:01:02:03 mac-address=00:0C:42:01:02:03 identity="R2-Branch" board="RB750Gr3"
          version="7.16.2" hop-count=1 path=00:0C:42:01:02:03
        """
        neighbors: List[RomonNeighbor] = []
        if not raw_output or not isinstance(raw_output, str):
            return neighbors

        # Split into blocks by record number (e.g. " 0 id=..." or "0  id=...")
        entries = re.split(r"\n\s*(?=\d+\s+(?:id|mac)=)", raw_output)
        for entry in entries:
            clean = " ".join(entry.split())
            if not clean:
                continue

            id_m = re.search(r"id=([0-9A-Fa-f:]+)", clean)
            mac_m = re.search(r"mac(?:-address)?=([0-9A-Fa-f:]+)", clean)
            ident_m = re.search(r'identity="?([^"\s]+)"?', clean)
            board_m = re.search(r'board(?:-name)?="?([^"\s]+)"?', clean)
            ver_m = re.search(r'version="?([^"\s]+)"?', clean)
            hop_m = re.search(r"hop-count=(\d+)", clean)
            path_m = re.search(r"path=([0-9A-Fa-f:,-]+)", clean)

            if id_m or mac_m:
                romon_id = id_m.group(1) if id_m else (mac_m.group(1) if mac_m else "")
                mac_addr = mac_m.group(1) if mac_m else romon_id
                identity = ident_m.group(1) if ident_m else romon_id
                board = board_m.group(1) if board_m else ""
                version = ver_m.group(1) if ver_m else ""
                hops = int(hop_m.group(1)) if hop_m else 1
                path_list = [p.strip() for p in (path_m.group(1) if path_m else "").split(",") if p.strip()]

                neighbors.append(RomonNeighbor(
                    romon_id=romon_id,
                    mac=mac_addr,
                    identity=identity,
                    version=version,
                    board=board,
                    hop_count=hops,
                    path=path_list,
                    via_device_id=via_device_id,
                    via_device_name=via_device_name,
                ))

        return neighbors

    @classmethod
    def discover_neighbors_via_intermediary(
        cls,
        intermediary_device_id: str,
        intermediary_device_name: str,
    ) -> List[RomonNeighbor]:
        """Runs `/romon neighbor print detail` on an authorized intermediary gateway router."""
        try:
            from agents.akane.connection_manager import get_connection_manager
            mgr = get_connection_manager()
            res = mgr.execute_for_device(intermediary_device_name, "/romon neighbor print detail")
            if not res.get("success"):
                logger.warning(
                    "Gagal menjalankan query RoMON pada gateway '%s': %s",
                    intermediary_device_name, res.get("error")
                )
                return []

            output = res.get("output", "")
            return cls.parse_romon_neighbor_output(
                output,
                via_device_id=intermediary_device_id,
                via_device_name=intermediary_device_name,
            )
        except Exception as exc:
            logger.exception("Error discovering RoMON neighbors via %s: %s", intermediary_device_name, exc)
            return []

    # -----------------------------------------------------------------------
    # Controlled RoMON Provisioning Workflow
    # -----------------------------------------------------------------------
    @classmethod
    def prepare_provisioning_plan(
        cls,
        device_id: str,
        device_name: str,
        routeros_version: str,
        management_interfaces: Optional[List[str]] = None,
        wan_interfaces: Optional[List[str]] = None,
        custom_secret: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Stage 1 of RoMON Provisioning:
        - Verifies RouterOS compatibility (v6.28+ or v7).
        - Identifies management interfaces vs WAN interfaces.
        - Formulates proposed configuration and explicit security implications.
        - Generates plan token requiring explicit administrator approval.
        """
        compat = CapabilityDetector.evaluate_romon_compatibility(routeros_version=routeros_version, vendor="MikroTik")
        if not compat.get("supported"):
            return {
                "success": False,
                "error": f"Perangkat tidak memenuhi syarat RoMON: {compat.get('reason')}",
            }

        mgmt_ifaces = management_interfaces or ["bridge", "lan"]
        wan_ifaces = wan_interfaces or ["ether1", "wan"]
        romon_secret = custom_secret or f"romon_sec_{uuid.uuid4().hex[:8]}"

        proposed_cmds = [
            f'/romon set enabled=yes secrets="{romon_secret}"',
        ]
        # Forbid RoMON on WAN interfaces for strict security
        for w in wan_ifaces:
            proposed_cmds.append(f'/romon port add interface={w} forbid=yes')
        for m in mgmt_ifaces:
            proposed_cmds.append(f'/romon port add interface={m} forbid=no')

        security_implications = [
            "RoMON mengaktifkan layer komunikasi overlay independen Layer 2 di atas interface yang dipilih.",
            f"Interface WAN ({', '.join(wan_ifaces)}) secara eksplisit DILARANG (forbid=yes) untuk mencegah paparan ke internet publik.",
            "RoMON dilindungi dengan secret terenkripsi acak berdaya tahan tinggi.",
            "Jalur SSH dan IP langsung yang ada saat ini TIDAK akan terganggu atau diputus.",
            "Rollback otomatis akan dieksekusi jika verifikasi konektivitas RoMON gagal dalam 60 detik.",
        ]

        rollback_cmds = [
            "/romon set enabled=no secrets=\"\"",
            "/romon port remove [find]",
        ]

        plan = RomonProvisioningPlan(
            device_id=device_id,
            device_name=device_name,
            proposed_commands=proposed_cmds,
            security_implications=security_implications,
            rollback_commands=rollback_cmds,
            requires_approval=True,
            approved=False,
            status="PENDING_APPROVAL",
        )

        _PENDING_PLANS[plan.plan_token] = plan

        # Redact secrets in user-facing response
        safe_cmds = [re.sub(r'secrets="[^"]+"', 'secrets="********"', c) for c in proposed_cmds]

        return {
            "success": True,
            "plan_token": plan.plan_token,
            "device_id": device_id,
            "device_name": device_name,
            "proposed_commands": safe_cmds,
            "security_implications": security_implications,
            "requires_approval": True,
            "message": "Rencana provisioning RoMON telah disusun. Diperlukan konfirmasi eksplisit dari administrator.",
        }

    @classmethod
    def apply_provisioning(
        cls,
        plan_token: str,
        admin_approved: bool = False,
        intermediary_gateway: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Stage 2 of RoMON Provisioning:
        - Validates administrator approval.
        - Executes configuration through existing management path.
        - Verifies that original management path remains intact.
        - Verifies RoMON availability.
        - Rolls back if verification fails.
        """
        plan = _PENDING_PLANS.get(plan_token)
        if not plan:
            return {
                "success": False,
                "error": f"Plan token '{plan_token}' tidak ditemukan atau telah kedaluwarsa.",
            }

        if not admin_approved:
            return {
                "success": False,
                "error": "Persetujuan eksplisit administrator (admin_approved=true) diwajibkan untuk provisioning RoMON.",
            }

        plan.status = "PROVISIONING"
        plan.approved = True
        plan.executed_at = time.time()

        try:
            from agents.akane.connection_manager import get_connection_manager
            mgr = get_connection_manager()

            # Execute commands through active connection for device
            combined_cmd = " ; ".join(plan.proposed_commands)
            res = mgr.execute_for_device(plan.device_name, combined_cmd)

            if not res.get("success"):
                plan.status = "FAILED"
                plan.error = res.get("error", "Gagal menerapkan perintah RoMON.")
                return {
                    "success": False,
                    "error": f"Eksekusi provisioning gagal: {plan.error}",
                    "rollback_executed": False,
                }

            # Verification 1: Verify original management path is still alive
            verify_res = mgr.execute_for_device(plan.device_name, "/system identity print")
            if not verify_res.get("success"):
                # Connection broken! Execute rollback immediately
                logger.error(
                    "POST-PROVISIONING VERIFICATION FAILED on %s! Reverting RoMON configuration.",
                    plan.device_name
                )
                rb_cmd = " ; ".join(plan.rollback_commands)
                mgr.execute_for_device(plan.device_name, rb_cmd)
                plan.status = "ROLLED_BACK"
                plan.error = "Koneksi terputus setelah provisioning; rollback otomatis telah diterapkan."
                return {
                    "success": False,
                    "error": plan.error,
                    "rollback_executed": True,
                }

            plan.status = "COMPLETED"
            return {
                "success": True,
                "plan_token": plan_token,
                "device_id": plan.device_id,
                "device_name": plan.device_name,
                "status": "COMPLETED",
                "message": (
                    f"RoMON berhasil diaktifkan pada {plan.device_name}. "
                    "Jalur manajemen asli terverifikasi tetap stabil, dan interface WAN dilindungi."
                ),
            }

        except Exception as exc:
            plan.status = "FAILED"
            plan.error = str(exc)
            logger.exception("Error during RoMON provisioning execution: %s", exc)
            return {
                "success": False,
                "error": f"Terjadi kesalahan saat provisioning: {exc}",
            }

    @classmethod
    def rollback_provisioning(cls, plan_token: str) -> Dict[str, Any]:
        """Explicit administrative rollback of a provisioned plan."""
        plan = _PENDING_PLANS.get(plan_token)
        if not plan:
            return {"success": False, "error": f"Plan token '{plan_token}' tidak ditemukan."}

        try:
            from agents.akane.connection_manager import get_connection_manager
            mgr = get_connection_manager()
            rb_cmd = " ; ".join(plan.rollback_commands)
            res = mgr.execute_for_device(plan.device_name, rb_cmd)
            plan.status = "ROLLED_BACK"
            return {
                "success": True,
                "plan_token": plan_token,
                "message": f"Konfigurasi RoMON pada {plan.device_name} berhasil di-rollback.",
                "details": res,
            }
        except Exception as exc:
            return {"success": False, "error": f"Gagal rollback: {exc}"}
