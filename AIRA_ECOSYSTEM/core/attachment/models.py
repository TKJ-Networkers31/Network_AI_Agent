"""
core/attachments/models.py - Universal Attachment data contract
(Sprint 2.7 / Wave 1 / Worker 2).

    Capability  = WHAT AIRA can do            (core/capability)
    Artifact    = a generated FILE             (core/artifacts)
    Attachment  = METADATA + a REFERENCE to a file that already exists in
                  storage - user uploads, workspace files, generated
                  artifacts, or external files. An Attachment never carries
                  binary content itself; it only points at it.

HANYA bentuk data + serialisasi (dataclass murni + str-Enum), mengikuti pola
yang SAMA dengan core/artifacts/models.py, core/dio/models.py, dan
core/selection/models.py: tanpa I/O, tanpa database, tanpa reasoning.
Penyimpanan ada di core/attachments/store.py; validasi di
core/attachments/validator.py; lifecycle di core/attachments/engine.py.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


def new_attachment_id() -> str:
    return f"att_{uuid.uuid4().hex[:16]}"


class AttachmentSource(str, Enum):
    """Where an attachment's underlying bytes came from."""

    USER_UPLOAD = "user_upload"
    WORKSPACE = "workspace"
    GENERATED = "generated"
    EXTERNAL = "external"

    @classmethod
    def coerce(cls, value: Any) -> "AttachmentSource":
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            try:
                return cls(value.strip().lower())
            except ValueError:
                pass
        valid = ", ".join(item.value for item in cls)
        raise ValueError(f"source '{value}' tidak valid. Pilihan: {valid}.")


class AttachmentStatus(str, Enum):
    """Lifecycle state of one attachment record."""

    PENDING = "pending"
    AVAILABLE = "available"
    FAILED = "failed"
    DELETED = "deleted"

    @classmethod
    def coerce(cls, value: Any) -> "AttachmentStatus":
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            try:
                return cls(value.strip().lower())
            except ValueError:
                pass
        return cls.PENDING


VALID_SOURCES = frozenset(item.value for item in AttachmentSource)
VALID_STATUSES = frozenset(item.value for item in AttachmentStatus)


@dataclass
class Attachment:
    """
    One attachment record: metadata + a reference to existing storage.

    storage_reference : path RELATIVE to the AIRA Workspace root (resolved
                         via core.filesystem.WorkspaceManager), same
                         convention as core/artifacts/models.py::Artifact
                         and core/filesystem/models.py::FileEntry.path.
                         None while status == "pending" (reference not yet
                         assigned/known, e.g. an external file not fetched
                         into the workspace) or after status == "deleted".
    session_id         : chat session this attachment belongs to. Required
                          for ownership/access checks (an attachment is only
                          readable/deletable within the session that owns it).
    message_id         : chat_turns.id this attachment is associated with,
                          if any. May be set later via associate_with_message
                          (e.g. upload happens before the turn is persisted).
    source             : AttachmentSource value - where the bytes came from.
    status              : AttachmentStatus value - current lifecycle state.
    metadata            : free-form extension bag (original filename,
                          extension, checksum, error message on failure,
                          external URL, etc.). Never interpreted by callers
                          other than to display/debug.
    """

    id: str = field(default_factory=new_attachment_id)
    session_id: Optional[str] = None
    message_id: Optional[str] = None
    name: str = "untitled"
    mime_type: str = "application/octet-stream"
    size: int = 0
    storage_reference: Optional[str] = None
    source: str = AttachmentSource.USER_UPLOAD.value
    status: str = AttachmentStatus.PENDING.value
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.source = AttachmentSource.coerce(self.source).value
        self.status = AttachmentStatus.coerce(self.status).value

        if not isinstance(self.name, str) or not self.name.strip():
            self.name = "untitled"

        if not isinstance(self.mime_type, str) or not self.mime_type.strip():
            self.mime_type = "application/octet-stream"

        try:
            self.size = max(0, int(self.size))
        except (TypeError, ValueError):
            self.size = 0

        if not isinstance(self.metadata, dict):
            self.metadata = {}

    # ------------------------------------------------------------ derived

    @property
    def is_available(self) -> bool:
        return self.status == AttachmentStatus.AVAILABLE.value

    @property
    def is_deleted(self) -> bool:
        return self.status == AttachmentStatus.DELETED.value

    def owned_by_session(self, session_id: Optional[str]) -> bool:
        """Ownership check: an attachment with no session_id is only
        "owned" by an equally sessionless caller (terminal/global context),
        never silently matched to an arbitrary session."""
        return self.session_id == session_id

    # ------------------------------------------------------------ serialize

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Attachment":
        data = data if isinstance(data, dict) else {}
        known = {
            "id", "session_id", "message_id", "name", "mime_type", "size",
            "storage_reference", "source", "status", "created_at",
            "updated_at", "metadata",
        }
        kwargs = {k: v for k, v in data.items() if k in known and v is not None}
        return cls(**kwargs)


# ============================================================ VALIDATION

@dataclass
class ValidationIssue:
    field: str
    message: str

    def to_dict(self) -> dict:
        return {"field": self.field, "message": self.message}

    def __repr__(self) -> str:
        return f"{self.field}: {self.message}"


@dataclass
class ValidationResult:
    is_valid: bool
    issues: list[ValidationIssue] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"is_valid": self.is_valid, "issues": [i.to_dict() for i in self.issues]}

    def messages(self) -> list[str]:
        return [str(i) for i in self.issues]


@dataclass
class AttachmentResult:
    """Return value of every AttachmentEngine lifecycle call - never raises
    (same tolerant-result pattern as core/artifacts/models.py::ArtifactResult
    / core/dio/models.py::ValidationResult)."""

    success: bool
    attachment: Optional[Attachment] = None
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "attachment": self.attachment.to_dict() if self.attachment else None,
            "errors": list(self.errors),
        }
