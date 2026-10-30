"""
agents/akane/config_engine.py — AKANE Safe Configuration Engine (Phase 5).

Implements the deterministic 7-stage configuration change lifecycle:
  READ -> PLAN -> VALIDATE -> PREVIEW -> APPLY (Approval Guarded) -> VERIFY -> RECOVER
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from agents.akane.connection_manager import get_connection_manager
from core.topology_models import sanitize_cli_excerpt, sanitize_untrusted_text
from mcp_servers.network.security import mask_sensitive_data

logger = logging.getLogger("aira.akane.config_engine")

SNAPSHOT_DIR_DEFAULT = Path(__file__).resolve().parents[2] / "data" / "config_snapshots"
SNAPSHOT_DIR = Path(os.getenv("AIRA_CONFIG_SNAPSHOT_DIR", str(SNAPSHOT_DIR_DEFAULT)))


DANGEROUS_PATTERNS = [
    re.compile(r"/system\s+reset-configuration", re.IGNORECASE),
    re.compile(r"/system\s+reboot", re.IGNORECASE),
    re.compile(r"/file\s+remove", re.IGNORECASE),
    re.compile(r"/user\s+remove", re.IGNORECASE),
    re.compile(r"/certificate\s+reset", re.IGNORECASE),
]


def generate_rollback_for_command(cmd: str) -> Optional[str]:
    """
    Generates exact inverse/rollback RouterOS command for common operations.
    """
    c = cmd.strip()
    c_lower = c.lower()

    # 1. IP address add -> remove
    if c_lower.startswith("/ip address add"):
        addr_m = re.search(r"address=([^\s]+)", c)
        if addr_m:
            return f"/ip address remove [find address=\"{addr_m.group(1)}\"]"

    # 2. IP route add -> remove
    if c_lower.startswith("/ip route add"):
        dst_m = re.search(r"dst-address=([^\s]+)", c)
        if dst_m:
            return f"/ip route remove [find dst-address=\"{dst_m.group(1)}\"]"

    # 3. IP firewall filter add -> remove by comment or rule params
    if c_lower.startswith("/ip firewall filter add"):
        com_m = re.search(r'comment="?([^"\s]+)"?', c)
        if com_m:
            return f'/ip firewall filter remove [find comment="{com_m.group(1)}"]'
        chain_m = re.search(r"chain=([^\s]+)", c)
        action_m = re.search(r"action=([^\s]+)", c)
        if chain_m and action_m:
            return f'/ip firewall filter remove [find chain="{chain_m.group(1)}" and action="{action_m.group(1)}"]'

    # 4. IP firewall nat add -> remove
    if c_lower.startswith("/ip firewall nat add"):
        com_m = re.search(r'comment="?([^"\s]+)"?', c)
        if com_m:
            return f'/ip firewall nat remove [find comment="{com_m.group(1)}"]'
        if "action=masquerade" in c_lower:
            return '/ip firewall nat remove [find action=masquerade]'

    # 5. Interface enable -> disable / disable -> enable
    if c_lower.startswith("/interface enable"):
        name_m = re.search(r"/interface\s+enable\s+([^\s]+)", c)
        if name_m:
            return f"/interface disable {name_m.group(1)}"
    if c_lower.startswith("/interface disable"):
        name_m = re.search(r"/interface\s+disable\s+([^\s]+)", c)
        if name_m:
            return f"/interface enable {name_m.group(1)}"

    # 6. Interface set disabled=yes -> disabled=no
    if c_lower.startswith("/interface set") and "disabled=yes" in c_lower:
        return c.replace("disabled=yes", "disabled=no")
    if c_lower.startswith("/interface set") and "disabled=no" in c_lower:
        return c.replace("disabled=no", "disabled=yes")

    return None


class SafeConfigEngine:
    """
    Orchestrates the 7-stage safe configuration lifecycle.
    """

    def __init__(self):
        pass

    def _persist_snapshot(self, operation_id: str, record: Dict[str, Any]) -> str:
        """
        Persists both a protected raw snapshot (exact unmasked data for recovery)
        and a redacted presentation copy (for audit logs, UI, and diagnostics).
        Computes SHA-256 integrity hash and sets POSIX restricted permissions.
        """
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        try:
            if os.name != "nt":
                os.chmod(SNAPSHOT_DIR, 0o700)
        except Exception:
            pass

        # 1. Canonical snapshot payload serialization for hash integrity
        raw_payload = record.get("snapshot", {})
        if not isinstance(raw_payload, dict):
            raw_payload = {}
        cmds = record.get("commands", [])
        if not isinstance(cmds, list):
            cmds = []

        canonical_snapshot_bytes = json.dumps(raw_payload, sort_keys=True, separators=(',', ':')).encode("utf-8")
        sha256_hash = hashlib.sha256(canonical_snapshot_bytes).hexdigest()

        protected_record = {
            "operation_id": operation_id,
            "device_name": str(record.get("device_name") or ""),
            "timestamp": float(record.get("timestamp") or time.time()),
            "schema_version": "1.0",
            "sha256": sha256_hash,
            "commands": [str(c) for c in cmds],
            "snapshot": raw_payload,
        }

        # 2. Write protected recovery snapshot (UNMASKED, protected storage)
        raw_file_path = SNAPSHOT_DIR / f"{operation_id}.raw.json"
        with open(raw_file_path, "w", encoding="utf-8") as f:
            json.dump(protected_record, f, indent=2)

        # Legacy alias for backward compatibility with existing tests
        legacy_path = SNAPSHOT_DIR / f"{operation_id}.json"
        try:
            with open(legacy_path, "w", encoding="utf-8") as f:
                json.dump(protected_record, f, indent=2)
        except Exception:
            pass

        # 3. Write redacted presentation copy (MASKED, for UI, diagnostics, and external logs)
        redacted_file_path = SNAPSHOT_DIR / f"{operation_id}.redacted.json"
        redacted_record = mask_sensitive_data(protected_record)
        with open(redacted_file_path, "w", encoding="utf-8") as f:
            json.dump(redacted_record, f, indent=2)

        try:
            if os.name != "nt":
                os.chmod(raw_file_path, 0o600)
                os.chmod(legacy_path, 0o600)
                os.chmod(redacted_file_path, 0o600)
        except Exception:
            pass

        return str(raw_file_path)

    def validate_snapshot_integrity(self, operation_id: str, expected_device: Optional[str] = None) -> Dict[str, Any]:
        """
        Validates the integrity, checksum, and device binding of a stored recovery snapshot.
        Distinguishes missing snapshot, truncated/corrupted snapshot, checksum mismatch, and device mismatch.
        """
        raw_file_path = SNAPSHOT_DIR / f"{operation_id}.raw.json"
        if not raw_file_path.exists():
            legacy_path = SNAPSHOT_DIR / f"{operation_id}.json"
            if legacy_path.exists():
                raw_file_path = legacy_path
            else:
                return {
                    "valid": False,
                    "error": "MISSING_SNAPSHOT",
                    "message": f"Snapshot file for operation '{operation_id}' not found.",
                }

        try:
            with open(raw_file_path, "r", encoding="utf-8") as f:
                content = f.read()
            if not content.strip():
                return {
                    "valid": False,
                    "error": "CORRUPTED_SNAPSHOT",
                    "message": "Snapshot file is empty or truncated.",
                }
            data = json.loads(content)
        except Exception as exc:
            return {
                "valid": False,
                "error": "CORRUPTED_SNAPSHOT",
                "message": f"Snapshot file failed to parse as valid JSON: {exc}",
            }

        # Check metadata binding
        op_bound = data.get("operation_id")
        if op_bound and op_bound != operation_id:
            return {
                "valid": False,
                "error": "OPERATION_MISMATCH",
                "message": f"Snapshot operation ID mismatch: expected '{operation_id}', got '{op_bound}'.",
            }

        dev_bound = data.get("device_name")
        if expected_device and dev_bound and dev_bound != expected_device:
            return {
                "valid": False,
                "error": "DEVICE_MISMATCH",
                "message": f"Snapshot device mismatch: expected '{expected_device}', got '{dev_bound}'.",
            }

        # Check SHA-256 checksum
        expected_sha = data.get("sha256")
        if expected_sha:
            raw_payload = data.get("snapshot", {})
            canonical_bytes = json.dumps(raw_payload, sort_keys=True, separators=(',', ':')).encode("utf-8")
            calculated_sha = hashlib.sha256(canonical_bytes).hexdigest()
            if calculated_sha != expected_sha:
                return {
                    "valid": False,
                    "error": "INTEGRITY_MISMATCH",
                    "message": "Snapshot integrity check failed: SHA-256 hash mismatch (possible tampering or disk corruption).",
                }

        return {
            "valid": True,
            "error": None,
            "operation_id": operation_id,
            "device_name": dev_bound,
            "timestamp": data.get("timestamp"),
            "snapshot": data.get("snapshot"),
        }

    def get_presentation_snapshot(self, operation_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves a sanitized/masked copy of the snapshot for presentation in UI,
        diagnostics, or external logs. Never returns raw sensitive secrets.
        """
        redacted_file = SNAPSHOT_DIR / f"{operation_id}.redacted.json"
        if redacted_file.exists():
            try:
                with open(redacted_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

        val = self.validate_snapshot_integrity(operation_id)
        if val.get("valid"):
            return mask_sensitive_data(val)
        return None

    # ------------------------------------------------------------------
    # Stage 1: READ (Snapshot baseline state)
    # ------------------------------------------------------------------

    def read_snapshot(self, device_name: str) -> Dict[str, Any]:
        mgr = get_connection_manager()
        res = mgr.get_configuration_snapshot(device_name)
        if not isinstance(res, dict):
            res = {}
        sections = res.get("sections", {})
        if not isinstance(sections, dict):
            sections = {}
        errors = res.get("errors", [])
        if not isinstance(errors, list):
            errors = []
        return {
            "stage": "READ",
            "success": bool(res.get("success", False)),
            "device_name": device_name,
            "timestamp": float(res.get("timestamp") or time.time()),
            "snapshot": sections,
            "errors": errors,
        }

    # ------------------------------------------------------------------
    # Stage 2: PLAN (Analyze syntax, safety, and synthesize rollbacks)
    # ------------------------------------------------------------------

    def plan_change(self, device_name: str, proposed_commands: List[str]) -> Dict[str, Any]:
        clean_cmds = [
            c.strip() for c in proposed_commands
            if c and c.strip() and not c.strip().startswith("#")
        ]

        if not clean_cmds:
            return {
                "stage": "PLAN",
                "success": False,
                "error": "No valid configuration commands proposed.",
                "commands": [],
            }

        flagged_issues = []
        rollbacks = []

        risk_flags = []
        for idx, cmd in enumerate(clean_cmds, 1):
            cmd_lower = cmd.lower()
            for pat in DANGEROUS_PATTERNS:
                if pat.search(cmd):
                    flagged_issues.append(f"Command #{idx} rejected: dangerous operation detected ('{cmd}')")

            # Check for quote balance
            if cmd.count('"') % 2 != 0:
                flagged_issues.append(f"Command #{idx} syntax warning: Unbalanced double quotes ('{cmd}')")

            # Check potential SSH lockout: e.g. disabling interface ether1 / management
            if "/interface disable" in cmd_lower and any(m in cmd_lower for m in ("ether1", "lan", "mgmt")):
                flagged_issues.append(f"Command #{idx} warning: Disabling potential management interface ('{cmd}')")

            # Risk flags evaluation
            if "/ip route" in cmd_lower and ("0.0.0.0/0" in cmd_lower or "gateway=" in cmd_lower):
                risk_flags.append(f"Command #{idx}: Modifikasi routing default/gateway berisiko mengganggu konektivitas host.")
            if any(m in cmd_lower for m in ("/user", "/password", "/certificate")):
                risk_flags.append(f"Command #{idx}: Perubahan user/kredensial/sertifikat berisiko mengunci sesi SSH.")
            if "/ip firewall" in cmd_lower and "chain=input" in cmd_lower:
                risk_flags.append(f"Command #{idx}: Modifikasi input chain filter berisiko memblokir port manajemen router.")
            if "/ip service" in cmd_lower:
                risk_flags.append(f"Command #{idx}: Perubahan service ports berisiko menutup port SSH.")

            rb = generate_rollback_for_command(cmd)
            if rb:
                rollbacks.append(rb)

        is_safe = len(flagged_issues) == 0
        rollbacks.reverse()  # Inverse execution order for clean rollback
        risk_level = "ELEVATED_MANAGEMENT_RISK" if risk_flags else "STANDARD" 

        return {
            "stage": "PLAN",
            "success": is_safe,
            "device_name": device_name,
            "commands_count": len(clean_cmds),
            "proposed_commands": clean_cmds,
            "rollback_plan": rollbacks,
            "flagged_issues": flagged_issues,
            "risk_level": risk_level,
            "risk_flags": risk_flags,
            "safety_status": "APPROVED_FOR_VALIDATION" if is_safe else "REJECTED_DANGEROUS",
            "target_binding": {
                "device_name": device_name,
                "command_count": len(clean_cmds),
                "approval_scope": "SINGLE_INVOCATION_ONLY",
                "blanket_access": False,
            },
        }

    # ------------------------------------------------------------------
    # Stage 3: VALIDATE (Verify device state & preflight readiness)
    # ------------------------------------------------------------------

    def validate_change(self, device_name: str, change_plan: Dict[str, Any]) -> Dict[str, Any]:
        mgr = get_connection_manager()
        target = mgr._resolve_target(device_name)

        if not target.get("success"):
            return {
                "stage": "VALIDATE",
                "success": False,
                "device_name": device_name,
                "error": f"Target device '{device_name}' cannot be resolved in inventory.",
            }

        # Check preflight reachability
        preflight_check = mgr.get_identity(device_name)
        if not preflight_check.get("success"):
            return {
                "stage": "VALIDATE",
                "success": False,
                "device_name": device_name,
                "error": f"Preflight connection failed for '{device_name}': {preflight_check.get('error')}",
            }

        return {
            "stage": "VALIDATE",
            "success": True,
            "device_name": device_name,
            "host": target.get("host"),
            "preflight_passed": True,
            "preflight_identity": preflight_check.get("raw_output", ""),
            "change_plan": change_plan,
        }

    # ------------------------------------------------------------------
    # Stage 4: PREVIEW (Detailed diff & rollback disclosure)
    # ------------------------------------------------------------------

    def preview_change(self, device_name: str, validation_result: Dict[str, Any]) -> Dict[str, Any]:
        plan = validation_result.get("change_plan", {})
        cmds = plan.get("proposed_commands", [])
        rollbacks = plan.get("rollback_plan", [])

        diff_lines = []
        for c in cmds:
            diff_lines.append(f"+ {c}")
        for r in rollbacks:
            diff_lines.append(f"- [Rollback plan]: {r}")

        return {
            "stage": "PREVIEW",
            "success": True,
            "device_name": device_name,
            "requires_approval": True,
            "confirmation_required": True,
            "commands_to_apply": cmds,
            "rollback_plan": rollbacks,
            "risk_level": plan.get("risk_level", "STANDARD"),
            "risk_flags": plan.get("risk_flags", []),
            "diff_preview": "\n".join(diff_lines),
            "summary": f"Ready to apply {len(cmds)} commands on '{device_name}'. Requires explicit approval=True.",
        }

    # ------------------------------------------------------------------
    # Stage 5: APPLY (Strictly Guarded Execution)
    # ------------------------------------------------------------------

    def apply_change(
        self,
        device_name: str,
        commands: List[str],
        approved: bool = False,
        operation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        op_id = operation_id or f"op_{int(time.time())}_{uuid.uuid4().hex[:8]}"

        if not approved:
            return {
                "stage": "APPLY",
                "operation_id": op_id,
                "success": False,
                "requires_approval": True,
                "status": "APPROVAL_REQUIRED",
                "device_name": device_name,
                "message": (
                    f"Pengubahan konfigurasi pada '{device_name}' adalah operasi STATE-CHANGING. "
                    "Persetujuan eksplisit user diperlukan. Panggil kembali dengan approved=True."
                ),
            }

        mgr = get_connection_manager()

        # Capture pre-change snapshot before multi-command change
        clean_commands = [c.strip() for c in commands if c and c.strip() and not c.strip().startswith("#")]
        snapshot_res = self.read_snapshot(device_name)
        if not snapshot_res.get("success") and len(clean_commands) > 1:
            return {
                "stage": "APPLY",
                "operation_id": op_id,
                "success": False,
                "device_name": device_name,
                "status": "SNAPSHOT_FAILED",
                "error": f"Gagal mengambil snapshot pre-change untuk {device_name}. Perubahan multi-command dibatalkan demi integritas perangkat.",
                "snapshot_errors": snapshot_res.get("errors", []),
                "recovery_needed": False,
            }

        snapshot_path = None
        try:
            snapshot_path = self._persist_snapshot(op_id, {
                "operation_id": op_id,
                "device_name": device_name,
                "timestamp": time.time(),
                "commands": clean_commands,
                "snapshot": snapshot_res.get("snapshot", {}),
            })
        except Exception as exc:
            logger.error("Snapshot persistence failed for op %s on %s: %s", op_id, device_name, exc)
            return {
                "stage": "APPLY",
                "operation_id": op_id,
                "success": False,
                "device_name": device_name,
                "status": "SNAPSHOT_PERSISTENCE_FAILED",
                "error": f"Gagal menyimpan snapshot ke storage: {exc}. Eksekusi konfigurasi dibatalkan demi keamanan.",
                "recovery_needed": False,
            }

        applied_results = []
        failed = False
        failed_command = ""
        error_msg = ""

        for cmd in clean_commands:
            res = mgr.execute_for_device(device_name, cmd, timeout=20.0)
            applied_results.append({
                "command": cmd,
                "success": res.get("success", False),
                "output": res.get("output", ""),
                "error": res.get("error"),
                "latency_ms": res.get("latency_ms", 0.0),
            })

            if not res.get("success"):
                failed = True
                failed_command = cmd
                error_msg = res.get("error", "Execution failed")
                break

        if failed:
            applied_so_far = max(0, len(applied_results) - 1)
            return {
                "stage": "APPLY",
                "operation_id": op_id,
                "success": False,
                "device_name": device_name,
                "status": "APPLY_FAILED",
                "partial_application": applied_so_far > 0,
                "applied_count": applied_so_far,
                "failed_command": failed_command,
                "error": error_msg,
                "details": applied_results,
                "snapshot_file": snapshot_path,
                "recovery_needed": True,
            }

        return {
            "stage": "APPLY",
            "operation_id": op_id,
            "success": True,
            "device_name": device_name,
            "status": "APPLIED_SUCCESSFULLY",
            "applied_count": len(applied_results),
            "details": applied_results,
            "snapshot_file": snapshot_path,
        }

    # ------------------------------------------------------------------
    # Stage 6: VERIFY (Post-Change Verification)
    # ------------------------------------------------------------------

    def verify_change(self, device_name: str, applied_commands: List[str]) -> Dict[str, Any]:
        mgr = get_connection_manager()
        verification_checks = []

        # Check if interfaces or IPs were added
        has_ip_changes = any("/ip address" in c.lower() for c in applied_commands)
        has_route_changes = any("/ip route" in c.lower() for c in applied_commands)
        has_firewall_changes = any("/ip firewall" in c.lower() for c in applied_commands)

        all_ok = True

        if has_ip_changes:
            res_ip = mgr.get_ip_addresses(device_name)
            ok = res_ip.get("success", False)
            raw_ip = res_ip.get("raw_output", "")
            # Semantic verification: verify added IP appears in raw table
            ip_found = True
            for c in applied_commands:
                if "/ip address add" in c.lower():
                    m = re.search(r"address=([^\s/]+)", c)
                    if m and m.group(1) not in raw_ip:
                        ip_found = False
                        break
            verified_ip = ok and ip_found
            verification_checks.append({
                "target": "ip_addresses",
                "verified": verified_ip,
                "semantic_presence": ip_found,
                "output": raw_ip[:200],
                "error": None if ip_found else "Applied IP address was not observed in running interface addresses (silent failure or conflict)."
            })
            if not verified_ip:
                all_ok = False

        if has_route_changes:
            res_r = mgr.get_routes(device_name)
            ok = res_r.get("success", False)
            raw_r = res_r.get("raw_output", "")
            route_found = True
            for c in applied_commands:
                if "/ip route add" in c.lower():
                    m = re.search(r"dst-address=([^\s/]+)", c)
                    if m and m.group(1) not in raw_r:
                        route_found = False
                        break
            verified_r = ok and route_found
            verification_checks.append({
                "target": "routes",
                "verified": verified_r,
                "semantic_presence": route_found,
                "output": raw_r[:200],
                "error": None if route_found else "Applied route destination was not observed in routing table (unreachable gateway or conflict)."
            })
            if not verified_r:
                all_ok = False

        if has_firewall_changes:
            res_fw = mgr.get_firewall_rules(device_name)
            ok = res_fw.get("success", False)
            raw_fw = res_fw.get("raw_output", "")
            fw_found = True
            for c in applied_commands:
                if "/ip firewall filter add" in c.lower():
                    m = re.search(r'comment="?([^"\s]+)"?', c)
                    if m and m.group(1) not in raw_fw:
                        fw_found = False
                        break
            verified_fw = ok and fw_found
            verification_checks.append({
                "target": "firewall",
                "verified": verified_fw,
                "semantic_presence": fw_found,
                "output": raw_fw[:200],
                "error": None if fw_found else "Applied firewall filter rule not observed in active filter chain."
            })
            if not verified_fw:
                all_ok = False

        # General sanity: check device identity responds promptly
        res_ident = mgr.get_identity(device_name)
        if not res_ident.get("success"):
            all_ok = False
            verification_checks.append({"target": "router_identity", "verified": False, "error": "Router unresponsive after config change!"})

        return {
            "stage": "VERIFY",
            "success": all_ok,
            "device_name": device_name,
            "status": "VERIFIED_OPERATIONAL" if all_ok else "VERIFICATION_FAILED",
            "lifecycle_status": "VERIFIED_SUCCESS" if all_ok else "RECOVERY_REQUIRED",
            "recovery_needed": not all_ok,
            "checks": verification_checks,
        }

    # ------------------------------------------------------------------
    # Stage 7: RECOVER (Rollback Execution)
    # ------------------------------------------------------------------

    def recover(
        self,
        device_name: str,
        rollback_commands: List[str],
        operation_id: Optional[str] = None,
        semantic_checks: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        op_id = operation_id or f"rec_{int(time.time())}_{uuid.uuid4().hex[:8]}"

        if not rollback_commands:
            return {
                "stage": "RECOVER",
                "operation_id": op_id,
                "success": True,
                "device_name": device_name,
                "status": "RECOVERY_VERIFIED",
                "recovery_status": "RECOVERY_VERIFIED",
                "lifecycle_status": "RECOVERY_VERIFIED",
                "message": "No rollback commands required.",
                "recovery_attempted": False,
                "manual_intervention_required": False,
            }

        mgr = get_connection_manager()
        rollback_results = []
        all_rb_ok = True

        for cmd in rollback_commands:
            res = mgr.execute_for_device(device_name, cmd, timeout=20.0)
            ok = res.get("success", False)
            rollback_results.append({
                "command": cmd,
                "success": ok,
                "output": res.get("output", ""),
                "error": res.get("error"),
            })
            if not ok:
                all_rb_ok = False

        # Post-recovery check 1: Device reachability
        ident_check = mgr.get_identity(device_name)
        alive = bool(ident_check.get("success", False)) if isinstance(ident_check, dict) else True

        # Failure scenarios
        if not alive:
            return {
                "stage": "RECOVER",
                "operation_id": op_id,
                "success": False,
                "device_name": device_name,
                "status": "ROLLBACK_PARTIAL_ERROR",
                "recovery_status": "RECOVERY_REQUIRED",
                "lifecycle_status": "RECOVERY_REQUIRED",
                "recovery_attempted": True,
                "recovery_mechanism": "synthesized_inverse_commands",
                "atomic_hardware_transaction": False,
                "device_responsive": False,
                "manual_intervention_required": True,
                "error": "Perangkat tidak merespons setelah eksekusi rollback! Memerlukan intervensi manual segera.",
                "disclaimer": (
                    "Rollback uses synthesized inverse RouterOS commands. "
                    "Does not guarantee atomic rollback if external dependencies or state changed."
                ),
                "results": rollback_results,
            }

        if not all_rb_ok:
            return {
                "stage": "RECOVER",
                "operation_id": op_id,
                "success": False,
                "device_name": device_name,
                "status": "ROLLBACK_PARTIAL_ERROR",
                "recovery_status": "RECOVERY_REQUIRED",
                "lifecycle_status": "RECOVERY_REQUIRED",
                "recovery_attempted": True,
                "recovery_mechanism": "synthesized_inverse_commands",
                "atomic_hardware_transaction": False,
                "device_responsive": True,
                "manual_intervention_required": True,
                "error": "Satu atau lebih perintah rollback gagal dieksekusi.",
                "disclaimer": (
                    "Rollback uses synthesized inverse RouterOS commands. "
                    "Does not guarantee atomic rollback if external dependencies or state changed."
                ),
                "results": rollback_results,
            }

        # Post-recovery check 2: Semantic verification
        # When configured semantic recovery checks are supplied, evaluate them against live state.
        semantic_details = []

        if semantic_checks:
            all_semantic_ok = True
            for chk in semantic_checks:
                target_type = chk.get("target")
                absent_val = chk.get("absent")
                present_val = chk.get("present")

                if target_type == "ip_addresses":
                    live_res = mgr.get_ip_addresses(device_name)
                elif target_type == "routes":
                    live_res = mgr.get_routes(device_name)
                elif target_type == "firewall":
                    live_res = mgr.get_firewall_rules(device_name)
                else:
                    live_res = mgr.get_identity(device_name)

                raw_out = live_res.get("raw_output", "") if isinstance(live_res, dict) else ""
                chk_passed = True
                fail_reason = None

                if absent_val and absent_val in raw_out:
                    chk_passed = False
                    fail_reason = f"Expected entity '{absent_val}' to be removed, but still observed in live {target_type}."
                if present_val and present_val not in raw_out:
                    chk_passed = False
                    fail_reason = f"Expected baseline entity '{present_val}' to be present, but missing in live {target_type}."

                if not chk_passed:
                    all_semantic_ok = False

                semantic_details.append({
                    "check": chk,
                    "passed": chk_passed,
                    "reason": fail_reason,
                })

            if not all_semantic_ok:
                return {
                    "stage": "RECOVER",
                    "operation_id": op_id,
                    "success": False,
                    "device_name": device_name,
                    "status": "ROLLBACK_STATE_MISMATCH",
                    "recovery_status": "RECOVERY_STATE_MISMATCH",
                    "lifecycle_status": "RECOVERY_REQUIRED",
                    "recovery_attempted": True,
                    "recovery_mechanism": "synthesized_inverse_commands",
                    "atomic_hardware_transaction": False,
                    "device_responsive": True,
                    "semantic_verification_passed": False,
                    "semantic_checks": semantic_details,
                    "manual_intervention_required": True,
                    "error": "Router is reachable and rollback commands executed, but live configuration differs from expected baseline state.",
                    "disclaimer": (
                        "Rollback commands executed but semantic state verification failed. "
                        "Manual inspection and intervention is required to reconcile router state."
                    ),
                    "results": rollback_results,
                }
            else:
                final_status = "RECOVERY_VERIFIED"
                return {
                    "stage": "RECOVER",
                    "operation_id": op_id,
                    "success": True,
                    "device_name": device_name,
                    "status": "ROLLBACK_SUCCESSFUL",
                    "recovery_status": final_status,
                    "lifecycle_status": final_status,
                    "recovery_attempted": True,
                    "recovery_mechanism": "synthesized_inverse_commands",
                    "atomic_hardware_transaction": False,
                    "device_responsive": True,
                    "semantic_verification_passed": True,
                    "semantic_checks": semantic_details,
                    "manual_intervention_required": False,
                    "disclaimer": (
                        "Rollback verified: inverse commands executed and semantic absence/baseline checks passed. "
                        "Note: RouterOS does not provide atomic hardware transactions."
                    ),
                    "results": rollback_results,
                }

        # If NO semantic checks were configured, return narrower status disclosing uncertainty
        narrow_status = "RECOVERY_ATTEMPTED_REACHABLE"
        return {
            "stage": "RECOVER",
            "operation_id": op_id,
            "success": True,
            "device_name": device_name,
            "status": "ROLLBACK_SUCCESSFUL",
            "recovery_status": narrow_status,
            "lifecycle_status": narrow_status,
            "recovery_attempted": True,
            "recovery_mechanism": "synthesized_inverse_commands",
            "atomic_hardware_transaction": False,
            "device_responsive": True,
            "semantic_verification_passed": None,
            "manual_intervention_required": False,
            "disclaimer": (
                "Router is reachable and inverse commands completed without error, "
                "but semantic configuration restoration was not verified against baseline state."
            ),
            "results": rollback_results,
        }


_config_engine_singleton: Optional[SafeConfigEngine] = None


def get_config_engine() -> SafeConfigEngine:
    global _config_engine_singleton
    if _config_engine_singleton is None:
        _config_engine_singleton = SafeConfigEngine()
    return _config_engine_singleton
