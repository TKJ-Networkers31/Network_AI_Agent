"""agents/rei/artifact_tools.py — tool LLM untuk ArtifactEngine & Attachment."""
import json
from typing import Any, Optional

from core.artifacts import (
    ArtifactType, DocumentSpec, SpreadsheetSpec, PresentationSpec, CsvSpec,
    VisualizationSpec, VisualizationNode, VisualizationEdge, get_artifact_engine,
)
from core.artifacts.models import DOCUMENT_TYPES, SPREADSHEET_TYPES, PRESENTATION_TYPES, VISUALIZATION_TYPES
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
    elif kind in VISUALIZATION_TYPES:
        result = engine.create_visualization(VisualizationSpec.from_dict(spec), kind, **kw)
    else:
        return {"success": False, "tool": "create_artifact", "error": f"Tipe '{kind}' tidak didukung."}

    if not result.success:
        return {"success": False, "tool": "create_artifact", "error": "; ".join(result.errors)}

    a = result.artifact
    view_url = f"/api/artifacts/{a.id}/view"
    download_url = f"/api/artifacts/{a.id}/download"
    return {
        "success": True, "tool": "create_artifact",
        "artifact_id": a.id, "name": a.name, "type": a.artifact_type, "size": a.size,
        "download_url": download_url,
        "view_url": view_url,
        "note": f"Beri user link Markdown [{a.name}]({view_url if a.artifact_type == 'html' else download_url}).",
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


def create_interactive_artifact(title: str, description: str = "", nodes: Optional[list] = None,
                                edges: Optional[list] = None, raw_svg: Optional[str] = None,
                                name: Optional[str] = None, session_id: Optional[str] = None,
                                **_ignored) -> dict:
    """
    Membuat file HTML artifact visualisasi mandiri di disk yang interaktif.
    Memiliki fitur: drag-and-drop nodes, dynamic curved edges, node inspection drawer,
    search/filter, pan/zoom, serta SVG & PNG export.
    """
    if not title or not isinstance(title, str):
        return {"success": False, "tool": "create_interactive_artifact", "error": "title wajib diisi (string)."}

    nodes_list = nodes if isinstance(nodes, list) else []
    edges_list = edges if isinstance(edges, list) else []

    if not nodes_list and not raw_svg:
        return {
            "success": False,
            "tool": "create_interactive_artifact",
            "error": "Harus menyertakan minimal satu node dalam 'nodes' atau 'raw_svg' untuk visualisasi.",
        }

    spec = VisualizationSpec(
        title=title,
        description=description or "",
        nodes=[VisualizationNode.from_dict(n) for n in nodes_list],
        edges=[VisualizationEdge.from_dict(e) for e in edges_list],
        raw_svg=raw_svg if isinstance(raw_svg, str) else None,
    )

    engine = get_artifact_engine()
    result = engine.create_visualization(
        spec,
        session_id=session_id,
        name=name or title,
        source="ai_agent",
    )

    if not result.success:
        return {"success": False, "tool": "create_interactive_artifact", "error": "; ".join(result.errors)}

    a = result.artifact
    view_url = f"/api/artifacts/{a.id}/view"
    download_url = f"/api/artifacts/{a.id}/download"

    return {
        "success": True,
        "tool": "create_interactive_artifact",
        "artifact_id": a.id,
        "name": a.name,
        "type": a.artifact_type,
        "size": a.size,
        "file_path": a.storage_reference,
        "view_url": view_url,
        "download_url": download_url,
        "note": (
            f"Artifact interaktif nyata berhasil disimpan di disk ({a.storage_reference}, {a.size} bytes). "
            f"Beri user link Markdown [{a.name}]({view_url}) dan jelaskan fitur interaktifnya (drag, detail click, search, export)."
        ),
    }


ARTIFACT_TOOLS = {
    "create_artifact": create_artifact,
    "create_interactive_artifact": create_interactive_artifact,
    "list_attachments": list_attachments,
    "read_attachment": read_attachment,
}
ARTIFACT_TOOL_CATEGORY = {
    "create_artifact": "filesystem",
    "create_interactive_artifact": "filesystem",
    "list_attachments": "filesystem",
    "read_attachment": "filesystem",
}

ARTIFACT_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "create_interactive_artifact",
            "description": (
                "Membuat STANDALONE INTERACTIVE VISUALIZATION ARTIFACT (HTML file mandiri di disk). "
                "Pakai saat user meminta visualisasi interaktif mandiri, topologi interaktif yang dapat diunduh/dibuka, "
                "atau diagram dengan manipulasi drag-and-drop, zoom/pan, dan inspeksi detail. "
                "Hasilnya adalah file nyata di disk (.html) yang memiliki fitur: klik node untuk detail, drag-and-drop node, "
                "pan & zoom canvas, pencarian/filter node, dan tombol ekspor SVG & PNG. "
                "PENTING: Jangan pernah klaim file dibuat jika belum memanggil tool ini!"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Judul visualisasi/topologi (misal: 'Topologi Jaringan Kantor Pusat').",
                    },
                    "description": {
                        "type": "string",
                        "description": "Deskripsi singkat tentang diagram atau topologi.",
                    },
                    "nodes": {
                        "type": "array",
                        "description": "Daftar node jaringan/komponen. Tiap node berupa objek: {id, label, type, ip, status, details, x, y}.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string", "description": "ID unik node (misal 'r-core', 'sw-dist1')."},
                                "label": {"type": "string", "description": "Nama tampilan perangkat (misal 'Core Router CCR2004')."},
                                "type": {"type": "string", "description": "Tipe perangkat: 'router', 'switch', 'firewall', 'server', 'access_point', 'pc', 'internet'."},
                                "ip": {"type": "string", "description": "Alamat IP perangkat (misal '10.0.0.1')."},
                                "status": {"type": "string", "description": "Status: 'online', 'warning', 'offline'."},
                                "details": {"type": "object", "description": "Metadata tambahan seperti vendor, model, ports, uptime."},
                                "x": {"type": "number", "description": "Koordinat horizontal awal (opsional)."},
                                "y": {"type": "number", "description": "Koordinat vertikal awal (opsional)."},
                            },
                            "required": ["id", "label"],
                        },
                    },
                    "edges": {
                        "type": "array",
                        "description": "Daftar koneksi antar perangkat. Tiap edge: {id, source, target, label, status, speed}.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string", "description": "ID unik edge (opsional)."},
                                "source": {"type": "string", "description": "ID node asal."},
                                "target": {"type": "string", "description": "ID node tujuan."},
                                "label": {"type": "string", "description": "Label koneksi (misal 'Trunk VLAN 10,20')."},
                                "status": {"type": "string", "description": "Status link: 'active', 'warning', 'down'."},
                                "speed": {"type": "string", "description": "Kecepatan link (misal '10 Gbps', '1 Gbps')."},
                            },
                            "required": ["source", "target"],
                        },
                    },
                    "raw_svg": {
                        "type": "string",
                        "description": "Kode SVG dasar opsional jika ingin menyematkan SVG yang ada ke dalam artifact interaktif.",
                    },
                    "name": {
                        "type": "string",
                        "description": "Nama file artifact (opsional, default memakai title).",
                    },
                },
                "required": ["title"],
            },
        },
    },
    {"type": "function", "function": {
        "name": "create_artifact",
        "description": (
            "Membuat FILE dokumen nyata yang bisa diunduh user: docx, pdf, xlsx, pptx, csv, markdown, txt, html. "
            "Pakai saat user minta 'buatkan laporan/dokumen/spreadsheet/presentasi/visualisasi'. "
            "Bentuk spec: docx/pdf/markdown/txt -> {\"title\":\"..\",\"blocks\":[{\"type\":\"heading\",\"text\":\"..\",\"level\":1},"
            "{\"type\":\"paragraph\",\"text\":\"..\"},{\"type\":\"list\",\"items\":[..]},{\"type\":\"table\",\"headers\":[..],\"rows\":[[..]]}]}; "
            "xlsx/csv -> {\"worksheets\":[{\"name\":\"Sheet1\",\"headers\":[..],\"rows\":[[..]]}]}; "
            "pptx -> {\"title\":\"..\",\"sections\":[{\"heading\":\"..\",\"content\":[\"poin\"]}],\"conclusion\":\"..\"}; "
            "html -> {\"title\":\"..\",\"nodes\":[..],\"edges\":[..]}. "
            "Jumlah kolom tiap row HARUS sama dengan headers."),
        "parameters": {"type": "object", "properties": {
            "artifact_type": {"type": "string", "description": "docx|pdf|xlsx|pptx|csv|markdown|txt|html"},
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