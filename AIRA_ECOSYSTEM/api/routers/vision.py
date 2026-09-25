"""
api/routers/vision.py — REST endpoint tipis untuk Image & Visual Input
(Sprint 2.7 / Wave 2 / Worker 3).

Murni "pintu HTTP" di atas core/vision/engine.py, mengikuti pola
api/routers/attachments.py. Tidak ada logic lifecycle/validasi di sini.
"""

from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from core.attachments.constants import MAX_ATTACHMENT_BYTES
from core.vision.engine import get_image_vision_engine

router = APIRouter(prefix="/api/vision", tags=["vision"])


def _raise_for_errors(errors: list[str]) -> None:
    raise HTTPException(status_code=400, detail="; ".join(errors) or "Permintaan tidak valid.")


async def _upload(
    session_id: str, message_id: Optional[str], file: UploadFile, is_screenshot: bool,
):
    content = await file.read()

    if len(content) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(status_code=413, detail=f"File melebihi batas {MAX_ATTACHMENT_BYTES} byte.")

    result = get_image_vision_engine().create_image_attachment(
        content=content, name=file.filename or "untitled", session_id=session_id,
        mime_type=file.content_type, message_id=message_id, is_screenshot=is_screenshot,
    )

    if not result.success:
        _raise_for_errors(result.errors)

    return result.to_dict()


@router.post("/images")
async def upload_image(
    session_id: str = Form(...),
    message_id: Optional[str] = Form(None),
    file: UploadFile = File(...),
):
    return await _upload(session_id, message_id, file, is_screenshot=False)


@router.post("/screenshots")
async def upload_screenshot(
    session_id: str = Form(...),
    message_id: Optional[str] = Form(None),
    file: UploadFile = File(...),
):
    return await _upload(session_id, message_id, file, is_screenshot=True)


@router.get("/{attachment_id}/context")
def get_visual_context(
    attachment_id: str,
    session_id: Optional[str] = Query(default=None),
    invoke_provider: bool = Query(default=True),
):
    packet = get_image_vision_engine().get_visual_context(
        attachment_id, session_id=session_id, invoke_provider=invoke_provider,
    )

    if packet is None:
        raise HTTPException(
            status_code=404,
            detail=f"Attachment gambar '{attachment_id}' tidak ditemukan atau belum tersedia.",
        )

    return packet