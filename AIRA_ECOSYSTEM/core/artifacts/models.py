"""
core/artifacts/models.py - data contract for the Artifact & Document Engine
(Sprint 2.7 / W5).

    Capability  = WHAT AIRA can do        (core/capability)
    Artifact    = a generated FILE - deterministic output of a structured
                  spec run through a generator (core/artifacts/generators/*)

HANYA bentuk data + serialisasi (dataclass murni), mengikuti pola
core/dio/models.py dan core/selection/models.py: tanpa I/O, tanpa database,
tanpa reasoning. Penyimpanan ada di core/artifacts/store.py; generator ada di
core/artifacts/generators/*.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Optional


def new_artifact_id() -> str:
    return f"artifact_{uuid.uuid4().hex[:16]}"


class ArtifactType(str, Enum):
    DOCX = "docx"
    PDF = "pdf"
    XLSX = "xlsx"
    PPTX = "pptx"
    MARKDOWN = "markdown"
    TXT = "txt"
    CSV = "csv"

    @classmethod
    def coerce(cls, value: Any) -> "ArtifactType":
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            try:
                return cls(value.strip().lower())
            except ValueError:
                pass
        valid = ", ".join(item.value for item in cls)
        raise ValueError(f"artifact_type '{value}' tidak valid. Pilihan: {valid}.")


MIME_TYPES: dict[str, str] = {
    ArtifactType.DOCX.value: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ArtifactType.PDF.value: "application/pdf",
    ArtifactType.XLSX.value: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ArtifactType.PPTX.value: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ArtifactType.MARKDOWN.value: "text/markdown",
    ArtifactType.TXT.value: "text/plain",
    ArtifactType.CSV.value: "text/csv",
}

EXTENSIONS: dict[str, str] = {
    ArtifactType.DOCX.value: ".docx",
    ArtifactType.PDF.value: ".pdf",
    ArtifactType.XLSX.value: ".xlsx",
    ArtifactType.PPTX.value: ".pptx",
    ArtifactType.MARKDOWN.value: ".md",
    ArtifactType.TXT.value: ".txt",
    ArtifactType.CSV.value: ".csv",
}

# Which family of spec each artifact_type accepts - used for validator/engine
# dispatch. A "document" here covers every text-flow format (real word
# processing formats AND the plain-text renderings of the same DocumentSpec).
DOCUMENT_TYPES = frozenset({
    ArtifactType.DOCX.value, ArtifactType.PDF.value,
    ArtifactType.MARKDOWN.value, ArtifactType.TXT.value,
})
SPREADSHEET_TYPES = frozenset({ArtifactType.XLSX.value, ArtifactType.CSV.value})
PRESENTATION_TYPES = frozenset({ArtifactType.PPTX.value})


class ArtifactStatus(str, Enum):
    PENDING = "pending"
    GENERATING = "generating"
    READY = "ready"
    FAILED = "failed"


VALID_STATUSES = frozenset(item.value for item in ArtifactStatus)


@dataclass
class Artifact:
    """
    One generated file. `storage_reference` is a path RELATIVE to the AIRA
    Workspace root (resolved via core.filesystem.WorkspaceManager) - the
    engine never stores an absolute path, so artifacts stay portable across
    hosts (same convention as core/filesystem/models.py::FileEntry.path).
    """

    id: str = field(default_factory=new_artifact_id)
    session_id: Optional[str] = None
    name: str = "untitled"
    artifact_type: str = ArtifactType.TXT.value
    mime_type: str = ""
    size: int = 0
    storage_reference: Optional[str] = None
    source: str = "generated"
    status: str = ArtifactStatus.PENDING.value
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.artifact_type = ArtifactType.coerce(self.artifact_type).value
        self.mime_type = self.mime_type or MIME_TYPES.get(self.artifact_type, "application/octet-stream")

        if self.status not in VALID_STATUSES:
            self.status = ArtifactStatus.PENDING.value

        if not isinstance(self.metadata, dict):
            self.metadata = {}

        if not isinstance(self.name, str) or not self.name.strip():
            self.name = "untitled"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Artifact":
        data = data if isinstance(data, dict) else {}
        known = {
            "id", "session_id", "name", "artifact_type", "mime_type", "size",
            "storage_reference", "source", "status", "created_at", "metadata",
        }
        kwargs = {k: v for k, v in data.items() if k in known and v is not None}
        return cls(**kwargs)


@dataclass
class ArtifactResult:
    """Return value of every ArtifactEngine.create_*() call - never raises
    (same tolerant-result pattern as core/dio/models.py::ValidationResult /
    core/model_store.py's {"success": ...} dicts, but typed)."""

    success: bool
    artifact: Optional[Artifact] = None
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "artifact": self.artifact.to_dict() if self.artifact else None,
            "errors": list(self.errors),
        }