"""
core/attachments/context.py - Context boundary for Universal Attachment.

Hanya metadata/reference; tidak pernah isi file. Status pemrosesan
(metadata["processing"]) ditampilkan sebagai catatan singkat; isi hasilnya
diambil AIRA lewat tool read_attachment (dengan paginasi).
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from core.attachments.models import Attachment

_CONTEXT_SAFE_FIELDS = (
    "id", "session_id", "message_id", "name", "mime_type", "size",
    "storage_reference", "source", "status", "created_at",
)


def _processing_status(attachment: Attachment) -> Optional[str]:
    meta = attachment.metadata if isinstance(attachment.metadata, dict) else {}
    proc = meta.get("processing")
    if isinstance(proc, dict):
        status = proc.get("status")
        return str(status) if status else None
    return None


def attachment_to_context_dict(attachment: Attachment) -> dict[str, Any]:
    """Metadata/reference dict. Tidak pernah memuat isi file."""
    full = attachment.to_dict()
    data = {key: full[key] for key in _CONTEXT_SAFE_FIELDS if key in full}

    status = _processing_status(attachment)
    if status:
        data["processing_status"] = status

    return data


def attachments_context_summary_text(attachments: Iterable[Attachment], limit: int = 10) -> str:
    lines = []

    for attachment in list(attachments)[:limit]:
        if attachment.is_deleted:
            continue

        status = _processing_status(attachment)
        note = f", diproses={status}" if status else ", belum diproses (pakai read_attachment)"
        lines.append(
            f"- {attachment.name} (id={attachment.id}, {attachment.mime_type}, {attachment.status}{note})"
        )

    return "\n".join(lines)


def attachments_context_section(
    attachments: Iterable[Attachment],
    *,
    include_text: bool = False,
    limit: int = 10,
) -> Optional[dict[str, Any]]:
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