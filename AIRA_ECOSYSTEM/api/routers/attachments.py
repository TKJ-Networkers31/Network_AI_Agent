"""
api/routers/attachments.py — REST endpoint tipis untuk Universal Attachment
(Sprint 2.7 / Wave 1 / Worker 2 + Multi-file & OCR Auto-Processing).

Murni "pintu HTTP" di atas core/attachments/engine.py. Upload memakai
multipart/form-data dan DISTREAM ke file sementara (tidak dibaca penuh ke RAM),
lalu diserahkan ke AttachmentEngine.create_from_file().
Mendukung single upload maupun batch multi-file upload, dengan auto-processing
(OCR untuk gambar/scan, ekstraksi dokumen untuk PDF/Word/Excel) agar langsung
siap di-reasoning oleh AI.
"""

import logging
import os
import shutil
import tempfile
from typing import Any, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from core.attachments import AttachmentSource, get_attachment_engine

logger = logging.getLogger("aira.api.attachments")
COPY_CHUNK = 1024 * 1024

router = APIRouter(prefix="/api/attachments", tags=["attachments"])


def _try_process_attachment(engine, attachment_id: str, session_id: str) -> None:
    """Jalankan OCR/ekstraksi teks di background thread agar hasil analisis langsung tersedia."""
    try:
        from core.file_processing.service import process_attachment
        process_attachment(engine, attachment_id, session_id=session_id)
    except Exception as exc:
        logger.warning("Auto-processing attachment %s gagal (%s): %s", attachment_id, type(exc).__name__, exc)


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


def _spool_to_disk(upload: UploadFile) -> str:
    """Salin upload ke file sementara per chunk. Return path-nya."""
    with tempfile.NamedTemporaryFile(delete=False, prefix="aira_upload_") as tmp:
        shutil.copyfileobj(upload.file, tmp, COPY_CHUNK)
        return tmp.name


@router.post("")
async def upload_attachment(
    session_id: str = Form(...),
    message_id: Optional[str] = Form(None),
    file: UploadFile = File(...),
):
    name = os.path.basename((file.filename or "untitled").replace("\\", "/")) or "untitled"

    try:
        tmp_path = await run_in_threadpool(_spool_to_disk, file)
    except OSError as exc:
        raise HTTPException(status_code=507, detail=f"Gagal menyimpan upload sementara: {exc}")

    engine = get_attachment_engine()
    try:
        result = await run_in_threadpool(
            engine.create_from_file,
            temp_path=tmp_path,
            name=name,
            session_id=session_id,
            mime_type=file.content_type,
            message_id=message_id,
        )
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    if not result.success:
        _raise_for_errors(result.errors)

    # Otomatis proses OCR / analisis teks dokumen
    if result.attachment:
        await run_in_threadpool(_try_process_attachment, engine, result.attachment.id, session_id)
        # Ambil kembali attachment terbaru dengan metadata processing
        fresh = engine.get(result.attachment.id, session_id=session_id)
        if fresh:
            return {"success": True, "attachment": fresh.to_dict()}

    return result.to_dict()


@router.post("/batch")
@router.post("/upload-multiple")
async def upload_multiple_attachments(
    session_id: str = Form(...),
    message_id: Optional[str] = Form(None),
    files: list[UploadFile] = File(...),
):
    """Upload beberapa file/gambar sekaligus untuk reasoning dan analisis dokumen."""
    if not files:
        raise HTTPException(status_code=400, detail="Tidak ada file yang diunggah.")

    engine = get_attachment_engine()
    succeeded = []
    failed = []

    for f in files:
        name = os.path.basename((f.filename or "untitled").replace("\\", "/")) or "untitled"
        try:
            tmp_path = await run_in_threadpool(_spool_to_disk, f)
        except OSError as exc:
            failed.append({"name": name, "error": f"Gagal spool ke disk: {exc}"})
            continue

        try:
            result = await run_in_threadpool(
                engine.create_from_file,
                temp_path=tmp_path,
                name=name,
                session_id=session_id,
                mime_type=f.content_type,
                message_id=message_id,
            )
            if result.success and result.attachment:
                # Otomatis jalankan OCR / file processing
                await run_in_threadpool(_try_process_attachment, engine, result.attachment.id, session_id)
                fresh = engine.get(result.attachment.id, session_id=session_id)
                succeeded.append(fresh.to_dict() if fresh else result.attachment.to_dict())
            else:
                failed.append({"name": name, "error": "; ".join(result.errors)})
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    if not succeeded and failed:
        errors = [f"{item['name']}: {item['error']}" for item in failed]
        raise HTTPException(status_code=400, detail="; ".join(errors))

    return {
        "success": len(succeeded) > 0,
        "attachments": succeeded,
        "failed": failed,
        "count": len(succeeded),
    }


@router.post("/workspace")
def attach_workspace_file(payload: WorkspaceAttachmentRequest):
    engine = get_attachment_engine()
    result = engine.create_from_workspace(
        relative_path=payload.relative_path, session_id=payload.session_id,
        message_id=payload.message_id, name=payload.name, mime_type=payload.mime_type,
        metadata=payload.metadata,
    )

    if not result.success:
        _raise_for_errors(result.errors)

    if result.attachment:
        _try_process_attachment(engine, result.attachment.id, payload.session_id)

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


@router.get("/meta/sources")
def list_sources():
    """Daftar source yang valid (dipakai frontend untuk validasi form)."""
    return {"sources": sorted(item.value for item in AttachmentSource)}


@router.get("/{attachment_id}")
def get_attachment(attachment_id: str, session_id: Optional[str] = Query(default=None)):
    attachment = get_attachment_engine().get(attachment_id, session_id=session_id)

    if attachment is None:
        raise HTTPException(status_code=404, detail=f"Attachment '{attachment_id}' tidak ditemukan.")

    return attachment.to_dict()


@router.get("/{attachment_id}/reference")
def get_attachment_reference(attachment_id: str, session_id: Optional[str] = Query(default=None)):
    """Referensi eksplisit (path/URL) - BUKAN isi file."""
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
