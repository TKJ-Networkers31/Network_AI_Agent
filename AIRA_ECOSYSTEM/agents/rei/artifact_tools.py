"""agents/rei/artifact_tools.py — tool LLM untuk ArtifactEngine & Attachment."""
import json
from typing import Any, Optional

from core.artifacts import (
    ArtifactType, DocumentSpec, SpreadsheetSpec, PresentationSpec, CsvSpec, get_artifact_engine,
)
from core.artifacts.models import DOCUMENT_TYPES, SPREADSHEET_TYPES, PRESENTATION_TYPES
from core.attachments import get_attachment_engine
from core.file_processing.service import process_attachment
from core.file_processing.context import processing_context_text

# Ukuran SATU halaman context (bukan batas ukuran file; file selalu diproses penuh).
DEFAULT_READ_CHARS = 20000
MIN_READ_CHARS = 1000
MAX_READ_CHARS = 200000


def create_artifact(artifact_type: str, spec: Any, name: Optional[str] = None,
                    session_id: Optional[str] = None, **_ignored) -> dict:
    if isinstance(spec, str):
        try:
            spec = json.loads(spec)
        except ValueError:
            return {"success": False, "tool": "create_artifact", "error": "spec harus JSON object."}
    if not isinstance(spec, dict):
        return {"success": False, "tool": "create_artifact", "error": "spec harus object."}

    try:
        kind = ArtifactType.coerce(artifact_type).value
    except ValueError as exc:
        return {"success": False, "tool": "create_artifact", "error": str(exc)}

    engine = get_artifact_engine()
    kw = dict(session_id=session_id, name=name, source="ai_agent")

    if kind in DOCUMENT_TYPES:
        result = engine.create_document(DocumentSpec.from_dict(spec), kind, **kw)
    elif kind in SPREADSHEET_TYPES:
        s = CsvSpec.from_dict(spec) if kind == "csv" and "worksheets" not in spec else SpreadsheetSpec.from_dict(spec)
        result = engine.create_spreadsheet(s, kind, **kw)
    elif kind in PRESENTATION_TYPES:
        result = engine.create_presentation(PresentationSpec.from_dict(spec), kind, **kw)
    else:
        return {"success": False, "tool": "create_artifact", "error": f"Tipe '{kind}' tidak didukung."}

    if not result.success:
        return {"success": False, "tool": "create_artifact", "error": "; ".join(result.errors)}

    a = result.artifact
    return {
        "success": True, "tool": "create_artifact",
        "artifact_id": a.id, "name": a.name, "type": a.artifact_type, "size": a.size,
        "download_url": f"/api/artifacts/{a.id}/download",
        "note": "Beri user link Markdown [nama](download_url) PERSIS seperti ini.",
    }


def list_attachments(session_id: Optional[str] = None, **_ignored) -> dict:
    items = get_attachment_engine().list(session_id=session_id) if session_id else []
    out = []
    for a in items:
        proc = (a.metadata or {}).get("processing")
        out.append({
            "id": a.id, "name": a.name, "mime_type": a.mime_type, "size": a.size,
            "processing_status": proc.get("status") if isinstance(proc, dict) else None,
        })
    return {"success": True, "tool": "list_attachments", "count": len(out), "attachments": out}


def read_attachment(attachment: str, max_chars: Any = DEFAULT_READ_CHARS, offset: Any = 0,
                    reprocess: Any = False, session_id: Optional[str] = None, **_ignored) -> dict:
    engine = get_attachment_engine()
    items = engine.list(session_id=session_id) if session_id else []
    key = (attachment or "").strip().lower()
    match = next((a for a in items if a.id.lower() == key or a.name.lower() == key), None)
    if match is None:
        names = ", ".join(a.name for a in items) or "(belum ada)"
        return {"success": False, "tool": "read_attachment",
                "error": f"Attachment '{attachment}' tidak ditemukan. Yang ada: {names}."}

    try:
        limit = max(MIN_READ_CHARS, min(int(max_chars), MAX_READ_CHARS))
    except (TypeError, ValueError):
        limit = DEFAULT_READ_CHARS
    try:
        start = max(0, int(offset))
    except (TypeError, ValueError):
        start = 0
    if isinstance(reprocess, str):
        reprocess = reprocess.strip().lower() in ("true", "1", "yes", "ya")

    cached = (match.metadata or {}).get("processing")
    force = bool(reprocess) or (isinstance(cached, dict) and cached.get("status") == "failed")

    try:
        proc = process_attachment(engine, match.id, session_id=session_id, force=force)
    except Exception as exc:
        return {"success": False, "tool": "read_attachment",
                "error": f"Pemrosesan gagal: {type(exc).__name__}: {exc}"}

    if proc is None:
        return {"success": False, "tool": "read_attachment",
                "error": "File tidak tersedia untuk diproses (referensi eksternal / belum tersimpan)."}

    text = processing_context_text(proc)
    chunk = text[start:start + limit]
    end = start + len(chunk)

    return {
        "success": proc["status"] != "failed",
        "tool": "read_attachment",
        "name": match.name,
        "status": proc["status"],  # completed | partial | failed
        "files": [{"path": f["path"], "type": f["type"], "status": f["status"]} for f in proc["files"][:50]],
        "files_total": len(proc["files"]),
        "errors": proc["errors"][:10],
        "errors_total": len(proc["errors"]),
        "content": chunk,
        "offset": start,
        "total_chars": len(text),
        "truncated": end < len(text),
        "next_offset": end if end < len(text) else None,
    }


ARTIFACT_TOOLS = {"create_artifact": create_artifact, "list_attachments": list_attachments,
                  "read_attachment": read_attachment}
ARTIFACT_TOOL_CATEGORY = {"create_artifact": "filesystem", "list_attachments": "filesystem",
                          "read_attachment": "filesystem"}

ARTIFACT_TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "create_artifact",
        "description": (
            "Membuat FILE dokumen nyata yang bisa diunduh user: docx, pdf, xlsx, pptx, csv, markdown, txt. "
            "Pakai saat user minta 'buatkan laporan/dokumen/spreadsheet/presentasi'. "
            "Bentuk spec: docx/pdf/markdown/txt -> {\"title\":\"..\",\"blocks\":[{\"type\":\"heading\",\"text\":\"..\",\"level\":1},"
            "{\"type\":\"paragraph\",\"text\":\"..\"},{\"type\":\"list\",\"items\":[..]},{\"type\":\"table\",\"headers\":[..],\"rows\":[[..]]}]}; "
            "xlsx/csv -> {\"worksheets\":[{\"name\":\"Sheet1\",\"headers\":[..],\"rows\":[[..]]}]}; "
            "pptx -> {\"title\":\"..\",\"sections\":[{\"heading\":\"..\",\"content\":[\"poin\"]}],\"conclusion\":\"..\"}. "
            "Jumlah kolom tiap row HARUS sama dengan headers."),
        "parameters": {"type": "object", "properties": {
            "artifact_type": {"type": "string", "description": "docx|pdf|xlsx|pptx|csv|markdown|txt"},
            "spec": {"type": "object", "description": "Struktur konten sesuai tipe."},
            "name": {"type": "string", "description": "Judul/nama file (opsional)."}},
            "required": ["artifact_type", "spec"]}}},
    {"type": "function", "function": {
        "name": "list_attachments",
        "description": "Melihat file yang di-upload user ke chat ini (beserta status pemrosesannya).",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "read_attachment",
        "description": (
            "Membaca/memproses ISI file yang di-upload user: gambar (OCR + analisis visual bila tersedia), "
            "PDF (teks & hasil scan), docx/xlsx/pptx, teks/config (.rsc/.conf/.log/dst), dan archive "
            "zip/tar/tgz/gz/bz2/xz (diekstrak aman, rekursif). WAJIB dipakai kalau user bertanya soal file "
            "yang dilampirkan - jangan mengarang isinya. Hasil punya status completed/partial/failed + errors "
            "per file: sampaikan jujur bagian yang berhasil dan yang gagal. Seluruh file diproses; hasil "
            "dibagi per halaman context. Kalau 'truncated' true, panggil lagi dengan offset=next_offset "
            "sampai habis."),
        "parameters": {"type": "object", "properties": {
            "attachment": {"type": "string", "description": "id atau nama file."},
            "max_chars": {"type": "integer", "description": "Ukuran satu halaman context.", "default": 20000},
            "offset": {"type": "integer", "description": "Posisi mulai (pakai next_offset).", "default": 0},
            "reprocess": {"type": "boolean", "description": "Paksa proses ulang.", "default": False}},
            "required": ["attachment"]}}},
]