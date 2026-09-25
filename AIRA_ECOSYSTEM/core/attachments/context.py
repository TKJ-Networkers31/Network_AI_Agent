"""
core/attachments/context.py - Context boundary for Universal Attachment
(Sprint 2.7 / Wave 1 / Worker 2).

Per the brief: "Attachment context must contain metadata/reference, not
binary content." This module is the ONLY place that turns an Attachment
into something meant for a prompt/Context payload, and it is structurally
incapable of carrying bytes - there is no code path here that reads a
file's content.

This does NOT create a second Context Builder. It produces plain
dict/str data in the exact shape core/context/models.py::ContextSection
already accepts (`data=` for structured, non-prompt data; `text=` only
when a caller decides attachment awareness belongs in the prompt itself).
Wiring `attachments_context_section()` into
core/context/builder.py::ContextBuilder is an integration step for
whichever worker connects Brain to attachments (mirrors how
core/capability/integration.py and core/selection/builder.py are also
usable standalone, wired in by their caller, not by core/context itself -
this avoids touching the Sprint 2.5/2.6 Context Builder contract here).
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from core.attachments.models import Attachment

# Fields deliberately EXCLUDED from context: none currently - every field
# on Attachment is already metadata/reference (storage_reference is a
# relative WORKSPACE PATH, never the bytes at that path). This list exists
# so a future field added to Attachment doesn't silently leak something
# binary-adjacent without a conscious decision here.
_CONTEXT_SAFE_FIELDS = (
    "id", "session_id", "message_id", "name", "mime_type", "size",
    "storage_reference", "source", "status", "created_at",
)


def attachment_to_context_dict(attachment: Attachment) -> dict[str, Any]:
    """Attachment -> metadata/reference dict, safe to place in a
    ContextSection's `data`. Never includes file content."""
    full = attachment.to_dict()
    return {key: full[key] for key in _CONTEXT_SAFE_FIELDS if key in full}


def attachments_context_summary_text(attachments: Iterable[Attachment], limit: int = 10) -> str:
    """Optional short human-readable line per attachment (name + type +
    status) - for callers that want attachment awareness IN the prompt
    text itself. Still never touches file content."""
    lines = []

    for attachment in list(attachments)[:limit]:
        if attachment.is_deleted:
            continue
        lines.append(f"- {attachment.name} ({attachment.mime_type}, {attachment.status})")

    return "\n".join(lines)


def attachments_context_section(
    attachments: Iterable[Attachment],
    *,
    include_text: bool = False,
    limit: int = 10,
) -> Optional[dict[str, Any]]:
    """
    Ready-to-use payload for a ContextSection: {"data": {...}, "text": "..."}.
    Callers wiring this into core/context/builder.py::ContextBuilder pass
    `data` into ContextSection(data=...) (never injected into the prompt)
    and, only if include_text=True, `text` into ContextSection(text=...)
    (which DOES reach the system prompt via PROMPT_SECTIONS - the caller's
    conscious choice, not this module's default).

    Returns None for an empty/all-deleted attachment list, so callers can
    skip creating a section entirely (same "no section for nothing" pattern
    as core/context/builder.py::_tool_section).
    """
    items = [a for a in attachments if not a.is_deleted]

    if not items:
        return None

    payload: dict[str, Any] = {
        "data": {
            "count": len(items),
            "items": [attachment_to_context_dict(a) for a in items[:limit]],
        },
    }

    if include_text:
        payload["text"] = attachments_context_summary_text(items, limit=limit)

    return payload
