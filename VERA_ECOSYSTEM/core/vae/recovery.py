"""
core/vae/recovery.py — VERA Universal Workflow Recovery Engine.

Evaluates operational failures across network automation, inventory,
configuration, and administration workflows. Transforms dead-end tool errors
(e.g., duplicate device registration) into actionable, context-preserving
recovery routes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import time
from typing import Any, Dict, List, Optional
import uuid

from core.vae.interaction import ErrorClassification, ErrorTaxonomy, classify_operational_error

logger = logging.getLogger("vera.vae.recovery")


@dataclass
class RecoveryAction:
    action_id: str
    action_type: str  # e.g., "UPDATE_EXISTING", "EDIT_FORM", "INSPECT_RESOURCE", "RETRY", "CANCEL"
    label: str
    description: str
    target_tool: str  # Tool to invoke upon selection
    prefilled_data: Dict[str, Any] = field(default_factory=dict)
    schema: Optional[Dict[str, Any]] = None  # Pre-filled interactive form schema if applicable
    is_primary: bool = False
    requires_confirmation: bool = False


@dataclass
class RecoveryPlan:
    workflow_id: str
    error_classification: ErrorClassification
    summary: str
    original_tool: str
    original_input: Dict[str, Any]
    recovery_actions: List[RecoveryAction]
    existing_resource: Optional[Dict[str, Any]] = None
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "category": self.error_classification.category.value,
            "user_message": self.error_classification.user_message,
            "summary": self.summary,
            "original_tool": self.original_tool,
            "original_input": self.original_input,
            "recovery_actions": [
                {
                    "action_id": a.action_id,
                    "action_type": a.action_type,
                    "label": a.label,
                    "description": a.description,
                    "target_tool": a.target_tool,
                    "prefilled_data": a.prefilled_data,
                    "schema": a.schema,
                    "is_primary": a.is_primary,
                    "requires_confirmation": a.requires_confirmation,
                }
                for a in self.recovery_actions
            ],
            "existing_resource": self.existing_resource,
            "created_at": self.created_at,
        }


class UniversalRecoveryPlanner:
    """
    Evaluates failed tool execution and formulates deterministic, safe recovery paths.
    """

    def plan_recovery(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        error_output: Any,
        session_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> RecoveryPlan:
        workflow_id = f"rec_{uuid.uuid4().hex[:8]}"
        err_str = str(error_output.get("error") if isinstance(error_output, dict) else error_output)
        classification = classify_operational_error(err_str, tool_name=tool_name, context=context)

        # -------------------------------------------------------------
        # DOMAIN SPECIFIC HANDLERS
        # -------------------------------------------------------------

        # Case 1: Device Registration Conflict (DUPLICATE_RESOURCE)
        if classification.category == ErrorTaxonomy.DUPLICATE_RESOURCE and tool_name in ("add_device", "create_device"):
            return self._plan_device_duplicate_recovery(
                workflow_id=workflow_id,
                classification=classification,
                tool_name=tool_name,
                tool_input=tool_input,
                session_id=session_id,
            )

        # Case 2: Connection failure (CONNECTION_FAILED / TIMEOUT)
        if classification.category in (ErrorTaxonomy.CONNECTION_FAILED, ErrorTaxonomy.TIMEOUT):
            return self._plan_connection_failure_recovery(
                workflow_id=workflow_id,
                classification=classification,
                tool_name=tool_name,
                tool_input=tool_input,
            )

        # Case 3: Generic failure with edit & retry capabilities
        actions: List[RecoveryAction] = []
        if classification.can_retry:
            actions.append(
                RecoveryAction(
                    action_id=f"act_retry_{uuid.uuid4().hex[:6]}",
                    action_type="RETRY",
                    label="Coba Lagi Operasi",
                    description="Jalankan kembali operasi dengan parameter yang sama.",
                    target_tool=tool_name,
                    prefilled_data=tool_input,
                    is_primary=True,
                )
            )

        if classification.can_edit:
            actions.append(
                RecoveryAction(
                    action_id=f"act_edit_{uuid.uuid4().hex[:6]}",
                    action_type="EDIT_FORM",
                    label="Ubah Parameter Input",
                    description="Buka kembali formulir untuk mengoreksi nilai yang salah.",
                    target_tool=tool_name,
                    prefilled_data=tool_input,
                    is_primary=not classification.can_retry,
                )
            )

        actions.append(
            RecoveryAction(
                action_id=f"act_cancel_{uuid.uuid4().hex[:6]}",
                action_type="CANCEL",
                label="Batalkan Alur Kerja",
                description="Tutup sesi interaksi ini dan kembali ke obrolan normal.",
                target_tool="cancel",
                is_primary=False,
            )
        )

        return RecoveryPlan(
            workflow_id=workflow_id,
            error_classification=classification,
            summary=f"Operasi '{tool_name}' tidak dapat diselesaikan: {classification.user_message}",
            original_tool=tool_name,
            original_input=tool_input,
            recovery_actions=actions,
        )

    def _plan_device_duplicate_recovery(
        self,
        workflow_id: str,
        classification: ErrorClassification,
        tool_name: str,
        tool_input: Dict[str, Any],
        session_id: Optional[str] = None,
    ) -> RecoveryPlan:
        """
        Specialized recovery for duplicate router/device registration.
        Offers:
          1. Update existing device (prefilled update form)
          2. Edit registration (reopen add form with original input)
          3. Inspect existing device details
        """
        dev_name = classification.target_resource or tool_input.get("name") or "Perangkat"

        # Safely attempt to lookup existing device from InventoryStore
        existing_info = None
        try:
            from core.inventory_store import get_inventory_store
            store = get_inventory_store()
            res = store.get_device(dev_name)
            if isinstance(res, dict) and res.get("success"):
                existing_info = res.get("device")
            elif isinstance(res, dict) and "name" in res:
                existing_info = res
        except Exception as exc:
            logger.debug("Recovery planner: could not lookup existing device '%s': %s", dev_name, exc)

        actions: List[RecoveryAction] = []

        # Route A: Update Existing Device
        update_prefill = {
            "name": dev_name,
            "host": tool_input.get("host") or (existing_info.get("host") if existing_info else ""),
            "port": tool_input.get("port") or (existing_info.get("port") if existing_info else 22),
            "username": tool_input.get("username") or (existing_info.get("username") if existing_info else "admin"),
            "device_type": tool_input.get("device_type") or (existing_info.get("device_type") if existing_info else "mikrotik"),
            "note": tool_input.get("note") or (existing_info.get("note") if existing_info else ""),
        }
        update_schema = {
            "id": f"form_update_{uuid.uuid4().hex[:6]}",
            "title": f"Perbarui Konfigurasi Perangkat '{dev_name}'",
            "description": "Perangkat ini sudah ada di inventaris. Anda dapat memperbarui alamat IP, port, atau kredensialnya.",
            "mode": "form",
            "sections": [
                {
                    "title": "Parameter Pembaruan",
                    "fields": [
                        {"name": "name", "label": "Nama Device (Kunci)", "type": "text", "default": dev_name, "readonly": True},
                        {"name": "host", "label": "Alamat IP / Host Baru", "type": "text", "default": update_prefill["host"], "required": True},
                        {"name": "port", "label": "Port SSH", "type": "number", "default": update_prefill["port"]},
                        {"name": "username", "label": "Username Baru", "type": "text", "default": update_prefill["username"]},
                        {"name": "note", "label": "Catatan", "type": "text", "default": update_prefill["note"]},
                    ],
                }
            ],
            "actions": [
                {"id": "submit_update", "label": "Simpan Pembaruan", "primary": True, "target_tool": "update_device"}
            ],
        }
        actions.append(
            RecoveryAction(
                action_id=f"act_update_{uuid.uuid4().hex[:6]}",
                action_type="UPDATE_EXISTING",
                label=f"Perbarui Perangkat '{dev_name}'",
                description="Ubah konfigurasi perangkat yang sudah ada menggunakan nilai baru.",
                target_tool="update_device",
                prefilled_data=update_prefill,
                schema=update_schema,
                is_primary=True,
            )
        )

        # Route B: Edit Registration Details (Change Name / IP)
        edit_schema = {
            "id": f"form_edit_{uuid.uuid4().hex[:6]}",
            "title": "Ubah Rincian Pendaftaran Baru",
            "description": f"Ganti nama perangkat (karena nama '{dev_name}' sudah dipakai) untuk mendaftarkannya sebagai unit berbeda.",
            "mode": "form",
            "sections": [
                {
                    "title": "Identitas & Jaringan",
                    "fields": [
                        {"name": "name", "label": "Nama Device Baru", "type": "text", "default": f"{dev_name}-New", "required": True},
                        {"name": "host", "label": "Alamat IP Host", "type": "text", "default": tool_input.get("host", ""), "required": True},
                        {"name": "port", "label": "Port SSH", "type": "number", "default": tool_input.get("port", 22)},
                        {"name": "username", "label": "Username", "type": "text", "default": tool_input.get("username", "admin")},
                    ],
                }
            ],
            "actions": [
                {"id": "submit_add", "label": "Daftarkan dengan Nama Baru", "primary": True, "target_tool": "add_device"}
            ],
        }
        actions.append(
            RecoveryAction(
                action_id=f"act_edit_{uuid.uuid4().hex[:6]}",
                action_type="EDIT_FORM",
                label="Ubah Nama Pendaftaran",
                description="Gunakan nama baru untuk mendaftarkan unit ini sebagai router baru.",
                target_tool="add_device",
                prefilled_data=tool_input,
                schema=edit_schema,
                is_primary=False,
            )
        )

        # Route C: Inspect Existing Device
        if existing_info:
            actions.append(
                RecoveryAction(
                    action_id=f"act_inspect_{uuid.uuid4().hex[:6]}",
                    action_type="INSPECT_RESOURCE",
                    label=f"Lihat Rincian '{dev_name}'",
                    description="Periksa data perangkat yang saat ini tersimpan di inventaris.",
                    target_tool="get_device",
                    prefilled_data={"name": dev_name},
                    is_primary=False,
                )
            )

        # Route D: Cancel
        actions.append(
            RecoveryAction(
                action_id=f"act_cancel_{uuid.uuid4().hex[:6]}",
                action_type="CANCEL",
                label="Batalkan Pendaftaran",
                description="Tutup formulir dan batalkan pendaftaran perangkat ini.",
                target_tool="cancel",
                is_primary=False,
            )
        )

        return RecoveryPlan(
            workflow_id=workflow_id,
            error_classification=classification,
            summary=f"Konflik Pendaftaran: Perangkat dengan nama '{dev_name}' sudah terdaftar dalam inventaris.",
            original_tool=tool_name,
            original_input=tool_input,
            recovery_actions=actions,
            existing_resource=existing_info,
        )

    def _plan_connection_failure_recovery(
        self,
        workflow_id: str,
        classification: ErrorClassification,
        tool_name: str,
        tool_input: Dict[str, Any],
    ) -> RecoveryPlan:
        target_host = tool_input.get("host") or tool_input.get("target") or "target"
        actions = [
            RecoveryAction(
                action_id=f"act_ping_{uuid.uuid4().hex[:6]}",
                action_type="DIAGNOSTIC_PROBE",
                label=f"Uji Ping ke {target_host}",
                description="Periksa apakah host merespons probe ICMP di layer network.",
                target_tool="network_ping",
                prefilled_data={"target": target_host, "count": 4},
                is_primary=True,
            ),
            RecoveryAction(
                action_id=f"act_retry_{uuid.uuid4().hex[:6]}",
                action_type="RETRY",
                label="Coba Lagi Sambungan",
                description="Kirim ulang permintaan koneksi ke perangkat setelah memeriksa konektivitas fisik.",
                target_tool=tool_name,
                prefilled_data=tool_input,
                is_primary=False,
            ),
            RecoveryAction(
                action_id=f"act_edit_conn_{uuid.uuid4().hex[:6]}",
                action_type="EDIT_FORM",
                label="Koreksi IP / Port",
                description="Buka formulir untuk memastikan IP target dan nomor port sudah benar.",
                target_tool=tool_name,
                prefilled_data=tool_input,
                is_primary=False,
            ),
            RecoveryAction(
                action_id=f"act_cancel_{uuid.uuid4().hex[:6]}",
                action_type="CANCEL",
                label="Batalkan Alur Kerja",
                description="Tutup sesi interaksi ini.",
                target_tool="cancel",
                is_primary=False,
            ),
        ]
        return RecoveryPlan(
            workflow_id=workflow_id,
            error_classification=classification,
            summary=f"Koneksi ke '{target_host}' gagal. Host mungkin offline atau firewall memblokir port.",
            original_tool=tool_name,
            original_input=tool_input,
            recovery_actions=actions,
        )


_default_recovery_planner = UniversalRecoveryPlanner()


def get_recovery_planner() -> UniversalRecoveryPlanner:
    return _default_recovery_planner
