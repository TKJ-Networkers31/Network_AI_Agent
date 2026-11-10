"""
core/vae/interaction.py — VERA Adaptive Experience Interaction Lifecycle & Error Taxonomy.

Defines the formal finite state machine for all interactive workflows
(device onboarding, configuration changes, user management, automation)
and provides structured error classification to prevent dead ends and
misleading success messages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re
import time
from typing import Any, Dict, List, Optional, Set


class InteractionState(str, Enum):
    IDLE = "IDLE"
    DRAFT = "DRAFT"
    VALIDATING = "VALIDATING"
    READY = "READY"
    SUBMITTING = "SUBMITTING"
    SUBMITTED = "SUBMITTED"
    PROCESSING = "PROCESSING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    NEEDS_INPUT = "NEEDS_INPUT"
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
    RECOVERY_AVAILABLE = "RECOVERY_AVAILABLE"
    CANCELLED = "CANCELLED"


# Valid state transitions graph
PERMITTED_TRANSITIONS: Dict[InteractionState, Set[InteractionState]] = {
    InteractionState.IDLE: {InteractionState.DRAFT, InteractionState.READY, InteractionState.SUBMITTING},
    InteractionState.DRAFT: {InteractionState.VALIDATING, InteractionState.CANCELLED},
    InteractionState.VALIDATING: {InteractionState.READY, InteractionState.NEEDS_INPUT, InteractionState.FAILED},
    InteractionState.READY: {InteractionState.SUBMITTING, InteractionState.CONFIRMATION_REQUIRED, InteractionState.CANCELLED},
    InteractionState.SUBMITTING: {InteractionState.SUBMITTED, InteractionState.PROCESSING, InteractionState.FAILED},
    InteractionState.SUBMITTED: {InteractionState.PROCESSING, InteractionState.FAILED, InteractionState.SUCCEEDED},
    InteractionState.PROCESSING: {
        InteractionState.SUCCEEDED,
        InteractionState.FAILED,
        InteractionState.PARTIAL_SUCCESS,
        InteractionState.RECOVERY_AVAILABLE,
        InteractionState.CONFIRMATION_REQUIRED,
    },
    InteractionState.FAILED: {InteractionState.RECOVERY_AVAILABLE, InteractionState.DRAFT, InteractionState.CANCELLED},
    InteractionState.RECOVERY_AVAILABLE: {
        InteractionState.DRAFT,
        InteractionState.READY,
        InteractionState.SUBMITTING,
        InteractionState.CANCELLED,
    },
    InteractionState.NEEDS_INPUT: {InteractionState.DRAFT, InteractionState.VALIDATING, InteractionState.CANCELLED},
    InteractionState.CONFIRMATION_REQUIRED: {InteractionState.SUBMITTING, InteractionState.CANCELLED, InteractionState.RECOVERY_AVAILABLE},
    InteractionState.PARTIAL_SUCCESS: {InteractionState.RECOVERY_AVAILABLE, InteractionState.SUCCEEDED, InteractionState.CANCELLED},
    InteractionState.SUCCEEDED: {InteractionState.IDLE, InteractionState.DRAFT},
    InteractionState.CANCELLED: {InteractionState.IDLE, InteractionState.DRAFT},
}


class ErrorTaxonomy(str, Enum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    DUPLICATE_RESOURCE = "DUPLICATE_RESOURCE"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"
    CONNECTION_FAILED = "CONNECTION_FAILED"
    DEVICE_OFFLINE = "DEVICE_OFFLINE"
    TIMEOUT = "TIMEOUT"
    UNSUPPORTED_OPERATION = "UNSUPPORTED_OPERATION"
    CONFLICT = "CONFLICT"
    RATE_LIMITED = "RATE_LIMITED"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass
class ErrorClassification:
    category: ErrorTaxonomy
    user_message: str
    can_retry: bool
    can_edit: bool
    requires_authorization: bool
    target_resource: Optional[str] = None
    conflicting_field: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


def classify_operational_error(error_str: str, tool_name: str = "", context: Optional[dict] = None) -> ErrorClassification:
    """
    Analyzes error strings and execution context to produce an authoritative ErrorClassification.
    """
    err = (error_str or "").strip()
    err_lower = err.lower()
    tool_lower = (tool_name or "").lower()

    # 1. Duplicate resource conflict (e.g., Device 'CHR' sudah ada)
    dup_match = re.search(r"device\s+['\"]?([^'\"\s]+)['\"]?\s+sudah\s+ada", err, re.IGNORECASE)
    if not dup_match:
        dup_match = re.search(r"['\"]?([^'\"\s]+)['\"]?\s+(?:sudah\s+ada|already\s+exists|duplicate)", err, re.IGNORECASE)

    if dup_match or "sudah ada" in err_lower or "already exists" in err_lower or "unique constraint" in err_lower:
        res_name = dup_match.group(1) if dup_match else ""
        return ErrorClassification(
            category=ErrorTaxonomy.DUPLICATE_RESOURCE,
            user_message=f"Perangkat atau sumber daya '{res_name or 'terkait'}' sudah terdaftar dalam sistem.",
            can_retry=False,
            can_edit=True,
            requires_authorization=False,
            target_resource=res_name,
            conflicting_field="name" if "device" in err_lower or "name" in err_lower else "identity",
            details={"raw_error": err},
        )

    # 2. Authentication required (check before generic validation or permission)
    if any(k in err_lower for k in ("authentication failed", "auth failed", "invalid password", "bad password", "kredensial salah", "password salah", "login failed")):
        return ErrorClassification(
            category=ErrorTaxonomy.AUTHENTICATION_REQUIRED,
            user_message="Autentikasi gagal. Kredensial username atau password perangkat tidak sesuai.",
            can_retry=False,
            can_edit=True,
            requires_authorization=False,
            details={"raw_error": err},
        )

    # 3. Device offline / unreachable
    if any(k in err_lower for k in ("offline", "unreachable", "tidak dapat dijangkau")):
        dev_match = re.search(r"(?:device|perangkat|host)\s+['\"]?([^'\"\s]+)['\"]?\s+(?:is\s+)?offline", err, re.IGNORECASE)
        res_name = dev_match.group(1) if dev_match else None
        return ErrorClassification(
            category=ErrorTaxonomy.DEVICE_OFFLINE,
            user_message=f"Perangkat '{res_name or 'target'}' sedang offline atau tidak dapat dijangkau.",
            can_retry=True,
            can_edit=False,
            requires_authorization=False,
            target_resource=res_name,
            details={"raw_error": err},
        )

    # 4. Connection failure
    if any(k in err_lower for k in ("connection refused", "network unreachable", "no route to host", "host is down", "koneksi gagal", "cannot connect", "unable to connect")):
        return ErrorClassification(
            category=ErrorTaxonomy.CONNECTION_FAILED,
            user_message="Gagal membuka koneksi ke target jaringan. Periksa IP host dan port manajemen.",
            can_retry=True,
            can_edit=True,
            requires_authorization=False,
            details={"raw_error": err},
        )

    # 5. Timeout
    if any(k in err_lower for k in ("timed out", "timeout", "timedout", "waktu habis")):
        return ErrorClassification(
            category=ErrorTaxonomy.TIMEOUT,
            user_message="Waktu tunggu koneksi atau eksekusi habis (timeout).",
            can_retry=True,
            can_edit=False,
            requires_authorization=False,
            details={"raw_error": err},
        )

    # 6. Permission denied / unauthorized
    if any(k in err_lower for k in ("permission denied", "unauthorized", "akses ditolak", "401", "403", "forbidden", "tidak memiliki hak akses")):
        return ErrorClassification(
            category=ErrorTaxonomy.PERMISSION_DENIED,
            user_message="Akses ditolak atau otorisasi tidak mencukupi untuk menjalankan tindakan ini.",
            can_retry=False,
            can_edit=False,
            requires_authorization=True,
            details={"raw_error": err},
        )

    # 7. Resource not found
    if any(k in err_lower for k in ("not found", "tidak ditemukan", "tidak ada")):
        nf_match = re.search(r"(?:device|perangkat|router)\s+['\"]?([^'\"\s]+)['\"]?\s+tidak\s+ditemukan", err, re.IGNORECASE)
        if not nf_match:
            nf_match = re.search(r"['\"]?([^'\"\s]+)['\"]?\s+tidak\s+ditemukan", err, re.IGNORECASE)
        res_name = nf_match.group(1) if nf_match else None
        return ErrorClassification(
            category=ErrorTaxonomy.RESOURCE_NOT_FOUND,
            user_message=f"Sumber daya '{res_name or 'target'}' tidak ditemukan dalam inventaris atau topologi.",
            can_retry=False,
            can_edit=True,
            requires_authorization=False,
            target_resource=res_name,
            details={"raw_error": err},
        )

    # 8. Validation error
    if any(k in err_lower for k in ("invalid", "validation", "wajib diisi", "tidak valid", "format")):
        return ErrorClassification(
            category=ErrorTaxonomy.VALIDATION_ERROR,
            user_message="Parameter input tidak valid atau format salah.",
            can_retry=False,
            can_edit=True,
            requires_authorization=False,
            details={"raw_error": err},
        )

    # Default fallback: Execution failure
    return ErrorClassification(
        category=ErrorTaxonomy.EXECUTION_FAILED,
        user_message=f"Operasi gagal dijalankan: {err}",
        can_retry=True,
        can_edit=True,
        requires_authorization=False,
        details={"raw_error": err},
    )


class InteractionStateMachine:
    """
    Enforces valid state transitions and audit logging for interactive workflows.
    """

    def __init__(self, workflow_id: str, initial_state: InteractionState = InteractionState.IDLE):
        self.workflow_id = workflow_id
        self.current_state = initial_state
        self.history: List[Dict[str, Any]] = [
            {"from": None, "to": initial_state.value, "timestamp": time.time(), "event": "INIT"}
        ]

    @property
    def state(self) -> InteractionState:
        return self.current_state

    def transition(self, target_state: InteractionState, event: str = "", metadata: Optional[dict] = None) -> bool:
        allowed = PERMITTED_TRANSITIONS.get(self.current_state, set())
        if target_state not in allowed:
            return False

        old_state = self.current_state
        self.current_state = target_state
        self.history.append({
            "from": old_state.value,
            "to": target_state.value,
            "timestamp": time.time(),
            "event": event,
            "metadata": metadata or {},
        })
        return True

    def transition_to(self, target_state: InteractionState, reason: str = "", metadata: Optional[dict] = None) -> bool:
        allowed = PERMITTED_TRANSITIONS.get(self.current_state, set())
        if target_state not in allowed:
            raise ValueError(f"Illegal transition from {self.current_state} to {target_state}")
        return self.transition(target_state, event=reason, metadata=metadata)
