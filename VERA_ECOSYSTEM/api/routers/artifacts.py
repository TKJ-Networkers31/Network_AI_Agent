"""
api/routers/artifacts.py — REST endpoint tipis untuk Artifact & Document
Engine (Sprint 2.7 W5 / Sprint 2.7.1 P0 recovery).

Murni pintu HTTP di atas core/artifacts/engine.py yang SUDAH ADA (7 format:
docx/pdf/xlsx/pptx/csv/markdown/txt) - tidak ada generator/spec baru di
sini. Sebelum file ini ada, ArtifactEngine tidak pernah dipanggil dari
manapun (root cause flow D di audit Sprint 2.5-2.8).

Trigger via LLM tool-call (Brain/Orchestrator) SENGAJA tidak
diimplementasikan di sini - itu keputusan desain (skema tool + prompt
instruksi) yang butuh diskusi produk terpisah. Endpoint ini memberi jalur
EKSPLISIT: user memicu lewat UI, bukan lewat percakapan bebas - jalur
paling rendah risiko untuk P0.
"""

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.artifacts import ArtifactType, DocumentSpec, PresentationSpec, SpreadsheetSpec, CsvSpec
from core.artifacts.engine import get_artifact_engine
from core.artifacts.models import DOCUMENT_TYPES, PRESENTATION_TYPES, SPREADSHEET_TYPES

router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])


class CreateArtifactRequest(BaseModel):
    artifact_type: str
    spec: dict[str, Any]
    session_id: Optional[str] = None
    name: Optional[str] = None
    source: str = "generated"
    metadata: Optional[dict[str, Any]] = None


@router.post("")
def create_artifact(payload: CreateArtifactRequest):
    engine = get_artifact_engine()

    try:
        artifact_type = ArtifactType.coerce(payload.artifact_type).value
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if artifact_type in DOCUMENT_TYPES:
        spec = DocumentSpec.from_dict(payload.spec)
        result = engine.create_document(
            spec, artifact_type, session_id=payload.session_id,
            name=payload.name, source=payload.source, metadata=payload.metadata,
        )
    elif artifact_type in SPREADSHEET_TYPES:
        if artifact_type == ArtifactType.CSV.value and "worksheets" not in payload.spec:
            spec = CsvSpec.from_dict(payload.spec)
        else:
            spec = SpreadsheetSpec.from_dict(payload.spec)
        result = engine.create_spreadsheet(
            spec, artifact_type, session_id=payload.session_id,
            name=payload.name, source=payload.source, metadata=payload.metadata,
        )
    elif artifact_type in PRESENTATION_TYPES:
        spec = PresentationSpec.from_dict(payload.spec)
        result = engine.create_presentation(
            spec, artifact_type, session_id=payload.session_id,
            name=payload.name, source=payload.source, metadata=payload.metadata,
        )
    else:
        raise HTTPException(status_code=400, detail=f"artifact_type '{artifact_type}' tidak didukung.")

    if not result.success:
        raise HTTPException(status_code=400, detail="; ".join(result.errors) or "Gagal membuat artifact.")

    return result.to_dict()


@router.get("")
def list_artifacts(session_id: Optional[str] = None):
    return {"artifacts": [a.to_dict() for a in get_artifact_engine().list(session_id=session_id)]}


@router.get("/{artifact_id}")
def get_artifact(artifact_id: str):
    artifact = get_artifact_engine().get(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail=f"Artifact '{artifact_id}' tidak ditemukan.")
    return artifact.to_dict()


@router.get("/{artifact_id}/download")
def download_artifact(artifact_id: str):
    from fastapi.responses import FileResponse
    from core.filesystem import get_workspace_manager

    artifact = get_artifact_engine().get(artifact_id)
    if artifact is None or not artifact.storage_reference:
        raise HTTPException(status_code=404, detail=f"Artifact '{artifact_id}' tidak ditemukan atau belum siap.")

    try:
        absolute_path = get_workspace_manager().resolve(artifact.storage_reference)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"File artifact tidak dapat diakses: {exc}")

    if not absolute_path.exists():
        raise HTTPException(status_code=404, detail="File artifact tidak ditemukan di disk.")

    return FileResponse(path=str(absolute_path), filename=artifact.name, media_type=artifact.mime_type)


@router.delete("/{artifact_id}")
def delete_artifact(artifact_id: str):
    ok = get_artifact_engine().delete(artifact_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Artifact '{artifact_id}' tidak ditemukan.")
    return {"success": True}
