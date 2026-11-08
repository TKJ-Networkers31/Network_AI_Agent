"""
core/workspace_links/models.py - data contract for Workspace Integration
(Sprint 2.7 / Wave 2 / W6).

A WorkspaceLink is a small piece of OWNERSHIP metadata: which chat session
(and optionally which turn/message) a file living in the AIRA Workspace
belongs to, when that file was NOT already created through
core/artifacts (Artifact.session_id) or core/attachments
(Attachment.session_id) - e.g. a plain file a session asked to be saved
straight into the Workspace, or a pre-existing Workspace file a
conversation later "adopts".

This module never stores bytes and never duplicates core/filesystem's
sandboxing - `relative_path` is always a path already resolved/validated
by core.filesystem.WorkspaceManager. It only answers: "whose is this
path, conversationally speaking?"
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Optional


def new_link_id() -> str:
    return f"wlink_{uuid.uuid4().hex[:16]}"


class LinkKind(str, Enum):
    """Where a workspace item's ownership record originates from."""

    CONVERSATION = "conversation"  # explicit session <-> path link (this module's own table)
    ARTIFACT = "artifact"          # derived from core.artifacts (Artifact.session_id)
    ATTACHMENT = "attachment"      # derived from core.attachments (Attachment.session_id)

    @classmethod
    def coerce(cls, value: Any) -> "LinkKind":
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            try:
                return cls(value.strip().lower())
            except ValueError:
                pass
        raise ValueError(f"kind '{value}' tidak valid. Pilihan: {[k.value for k in cls]}.")


@dataclass
class WorkspaceLink:
    """
    One ownership record: `relative_path` (Workspace-sandboxed path) belongs
    to `session_id`, optionally scoped to one turn (`message_id`) and/or
    referencing a ref_id in another store (artifact_id/attachment_id - only
    ever set for kind ARTIFACT/ATTACHMENT records materialized by
    core/workspace_links/service.py::WorkspaceIntegrationService.resolve_owner,
    never persisted for kind CONVERSATION rows, which have no ref_id).
    """

    id: str = field(default_factory=new_link_id)
    relative_path: str = ""
    session_id: str = ""
    message_id: Optional[str] = None
    kind: str = LinkKind.CONVERSATION.value
    ref_id: Optional[str] = None
    note: Optional[str] = None
    created_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        self.kind = LinkKind.coerce(self.kind).value
        self.relative_path = (self.relative_path or "").replace("\\", "/").strip("/")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "WorkspaceLink":
        data = data if isinstance(data, dict) else {}
        known = {
            "id", "relative_path", "session_id", "message_id",
            "kind", "ref_id", "note", "created_at",
        }
        kwargs = {k: v for k, v in data.items() if k in known and v is not None}
        return cls(**kwargs)


@dataclass
class LinkResult:
    """Return value of every WorkspaceIntegrationService mutation call -
    never raises (same tolerant-result pattern as
    core/artifacts/models.py::ArtifactResult / core/attachments/models.py::AttachmentResult)."""

    success: bool
    link: Optional[WorkspaceLink] = None
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "link": self.link.to_dict() if self.link else None,
            "errors": list(self.errors),
        }