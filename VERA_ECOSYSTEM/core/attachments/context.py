"""
core/attachments/context.py - Context boundary for Universal Attachment.

Hanya metadata/reference dan ringkasan teks hasil OCR / ekstraksi pemrosesan file;
tidak pernah mengembalikan raw bytes file. Teks hasil ekstraksi/OCR disertakan secara aman
sehingga LLM dan reasoning model dapat langsung menganalisa isi gambar dan dokumen.
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


def _extract_text_preview(attachment: Attachment, max_chars: int = 1500) -> str:
    """Ambil ringkasan teks hasil OCR gambar atau ekstraksi dokumen jika tersedia."""
    meta = attachment.metadata if isinstance(attachment.metadata, dict) else {}
    proc = meta.get("processing")
    if not isinstance(proc, dict):
        return ""

    texts: list[str] = []
    # Ambil teks OCR dari gambar / scan
    for ocr_entry in proc.get("ocr") or []:
        t = (ocr_entry.get("extracted_text") or "").strip()
        if t:
            texts.append(t)

    # Ambil teks dari dokumen / PDF / Office
    for text_entry in proc.get("text") or []:
        t = (text_entry.get("text") or "").strip()
        if t:
            texts.append(t)

    # Ambil analisis visual / deskripsi gambar jika tersedia
    for img_entry in proc.get("images") or []:
        v = img_entry.get("vision") or {}
        if isinstance(v, dict) and v.get("status") == "available":
            desc = ((v.get("analysis") or {}).get("description") or "").strip()
            if desc:
                texts.append(f"[Deskripsi Visual: {desc}]")

    combined = "\n".join(texts).strip()
    if not combined:
        return ""

    if len(combined) > max_chars:
        return combined[:max_chars] + f"... [dipotong {len(combined) - max_chars} karakter]"
    return combined


def attachment_to_context_dict(attachment: Attachment) -> dict[str, Any]:
    """Metadata/reference dict. Tidak pernah memuat bytes biner file."""
    full = attachment.to_dict()
    data = {key: full[key] for key in _CONTEXT_SAFE_FIELDS if key in full}

    status = _processing_status(attachment)
    if status:
        data["processing_status"] = status

    preview = _extract_text_preview(attachment, max_chars=300)
    if preview:
        data["text_preview"] = preview

    return data


def attachments_context_summary_text(attachments: Iterable[Attachment], limit: int = 10) -> str:
    lines = []

    for attachment in list(attachments)[:limit]:
        if attachment.is_deleted:
            continue

        status = _processing_status(attachment)
        note = f", diproses={status}" if status else ", belum diproses"
        header = f"- {attachment.name} (id={attachment.id}, {attachment.mime_type}, {attachment.status}{note})"
        lines.append(header)

        # Sertakan hasil OCR / analisis teks dokumen agar reasoning LLM bisa menganalisanya
        preview = _extract_text_preview(attachment, max_chars=1200)
        if preview:
            lines.append(f"  [Hasil Analisis Dokumen / OCR {attachment.name}]:\n  \"\"\"\n  {preview}\n  \"\"\"")

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
