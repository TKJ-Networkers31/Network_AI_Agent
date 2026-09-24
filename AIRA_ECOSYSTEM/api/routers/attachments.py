"""
api/routers/attachments.py — REST endpoint tipis untuk Universal Attachment
(Sprint 2.7 / Wave 1 / Worker 2).

Murni "pintu HTTP" di atas core/attachments/engine.py - tidak ada logic
lifecycle/validasi di sini, mengikuti pola api/routers/selection.py dan
api/routers/files.py. Upload memakai multipart/form-data (UploadFile);
endpoint lain menerima JSON.

Content/bytes TIDAK PERNAH dikembalikan lewat endpoint metadata - hanya
lewat GET /{id}/reference, dan itu pun hanya mengembalikan REFERENSI
(path/URL), bukan isi file (sesuai batas Context: metadata/reference,
bukan binary).
"""

from typing import Any, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from core.attachments import AttachmentSource, get_attachment_engine
from core.attachments.constants import MAX_ATTACHMENT_BYTES

router = APIRouter(prefix="/api/attachments", tags=["attachments"])


class WorkspaceAttachmentRequest(BaseModel):
    relative_path: str
    session_id: str
    message_id: Optional[str] = None
    name: Optional[str] = None
    mime_type: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class ExternalAttachmentRequest(BaseModel):
    url: str
    name: str
    session_id: str
    mime_type: Optional[str] = None
    message_id: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class AssociateRequest(BaseModel):
    message_id: str


def _raise_for_errors(errors: list[str]) -> None:
    raise HTTPException(status_code=400, detail="; ".join(errors) or "Permintaan tidak valid.")


@router.post("")
async def upload_attachment(
    session_id: str = Form(...),
    message_id: Optional[str] = Form(None),
    file: UploadFile = File(...),
):
    content = await file.read()

    if len(content) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File melebihi batas {MAX_ATTACHMENT_BYTES} byte.",
        )

    result = get_attachment_engine().create_from_upload(
        content=content,
        name=file.filename or "untitled",
        session_id=session_id,
        mime_type=file.content_type,
        message_id=message_id,
    )

    if not result.success:
        _raise_for_errors(result.errors)

    return result.to_dict()


@router.post("/workspace")
def attach_workspace_file(payload: WorkspaceAttachmentRequest):
    result = get_attachment_engine().create_from_workspace(
        relative_path=payload.relative_path, session_id=payload.session_id,
        message_id=payload.message_id, name=payload.name, mime_type=payload.mime_type,
        metadata=payload.metadata,
    )

    if not result.success:
        _raise_for_errors(result.errors)

    return result.to_dict()


@router.post("/external")
def attach_external_file(payload: ExternalAttachmentRequest):
    result = get_attachment_engine().create_external(
        url=payload.url, name=payload.name, session_id=payload.session_id,
        mime_type=payload.mime_type, message_id=payload.message_id, metadata=payload.metadata,
    )

    if not result.success:
        _raise_for_errors(result.errors)

    return result.to_dict()


@router.get("")
def list_attachments(
    session_id: Optional[str] = Query(default=None),
    message_id: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    source: Optional[str] = Query(default=None),
):
    engine = get_attachment_engine()
    items = engine.list(session_id=session_id, message_id=message_id, status=status, source=source)
    return {"attachments": [a.to_dict() for a in items]}


@router.get("/{attachment_id}")
def get_attachment(attachment_id: str, session_id: Optional[str] = Query(default=None)):
    attachment = get_attachment_engine().get(attachment_id, session_id=session_id)

    if attachment is None:
        raise HTTPException(status_code=404, detail=f"Attachment '{attachment_id}' tidak ditemukan.")

    return attachment.to_dict()


@router.get("/{attachment_id}/reference")
def get_attachment_reference(attachment_id: str, session_id: Optional[str] = Query(default=None)):
    """Referensi eksplisit (path/URL) - BUKAN isi file. Dipanggil hanya
    ketika sesuatu benar-benar butuh membaca/menyajikan kontennya."""
    reference = get_attachment_engine().get_content_reference(attachment_id, session_id=session_id)

    if reference is None:
        raise HTTPException(
            status_code=404,
            detail=f"Attachment '{attachment_id}' tidak ditemukan atau belum tersedia.",
        )

    return reference


@router.post("/{attachment_id}/associate")
def associate_attachment(attachment_id: str, payload: AssociateRequest):
    result = get_attachment_engine().associate_with_message(attachment_id, payload.message_id)

    if not result.success:
        raise HTTPException(status_code=404, detail="; ".join(result.errors))

    return result.to_dict()


@router.delete("/{attachment_id}")
def delete_attachment(attachment_id: str, session_id: Optional[str] = Query(default=None)):
    result = get_attachment_engine().delete(attachment_id, session_id=session_id)

    if not result.success:
        raise HTTPException(status_code=404, detail="; ".join(result.errors))

    return result.to_dict()


@router.get("/meta/sources")
def list_sources():
    """Daftar source yang valid (dipakai frontend untuk validasi form)."""
    return {"sources": sorted(item.value for item in AttachmentSource)}
