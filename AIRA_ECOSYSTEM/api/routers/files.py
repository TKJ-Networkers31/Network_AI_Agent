"""
api/routers/files.py — REST endpoint untuk Host Abstraction Layer (HAL)
dan File System Engine (FSE), Sprint 02.

Murni "pintu HTTP" tipis di atas core/host/* dan core/filesystem/* -
tidak ada logic bisnis di sini, sesuai aturan "API hanya menjadi
adapter" pada spesifikasi Sprint 02.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from core.host import get_host_info
from core.filesystem.workspace import get_workspace_manager, PathTraversalError
from core.filesystem.operations import FileOperations
from core.filesystem.trash import TrashEngine
from core.filesystem.history import HistoryEngine
from core.filesystem.permissions import get_permission_engine, PermissionLevel

router = APIRouter(tags=["files", "host"])


def _operations() -> FileOperations:
    return FileOperations()


class WriteRequest(BaseModel):
    path: str
    content: str
    encoding: str = "utf-8"


class MkdirRequest(BaseModel):
    path: str


class MoveRequest(BaseModel):
    source: str
    destination: str


class CopyRequest(BaseModel):
    source: str
    destination: str


class RenameRequest(BaseModel):
    source: str
    destination: str


class DeleteRequest(BaseModel):
    path: str


class RestoreRequest(BaseModel):
    trash_id: str


class GrantPermissionRequest(BaseModel):
    folder: str
    level: PermissionLevel


# ------------------------------------------------------------------
# HOST
# ------------------------------------------------------------------

@router.get("/host/info")
def host_info():
    return get_host_info().to_dict()


# ------------------------------------------------------------------
# FILES: READ-ONLY
# ------------------------------------------------------------------

@router.get("/files/tree")
def files_tree(path: str = Query(default=""), max_depth: int = Query(default=6, ge=1, le=20)):
    workspace = get_workspace_manager()

    try:
        node = workspace.tree(path, max_depth=max_depth)
    except PathTraversalError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return node


@router.get("/files/read")
def files_read(path: str = Query(...)):
    result = _operations().read_text(path)

    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)

    return result


# ------------------------------------------------------------------
# FILES: WRITE / MUTATE
# ------------------------------------------------------------------

@router.post("/files/write")
def files_write(payload: WriteRequest):
    result = _operations().write_text(payload.path, payload.content, encoding=payload.encoding)

    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)

    return result


@router.post("/files/mkdir")
def files_mkdir(payload: MkdirRequest):
    result = _operations().mkdir(payload.path)

    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)

    return result


@router.post("/files/move")
def files_move(payload: MoveRequest):
    result = _operations().move(payload.source, payload.destination)

    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)

    return result


@router.post("/files/copy")
def files_copy(payload: CopyRequest):
    result = _operations().copy(payload.source, payload.destination)

    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)

    return result


@router.post("/files/rename")
def files_rename(payload: RenameRequest):
    result = _operations().rename(payload.source, payload.destination)

    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)

    return result


@router.delete("/files/delete")
def files_delete(payload: DeleteRequest):
    result = _operations().delete(payload.path)

    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)

    return result


@router.post("/files/restore")
def files_restore(payload: RestoreRequest):
    result = _operations().restore(payload.trash_id)

    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)

    return result


# ------------------------------------------------------------------
# TRASH
# ------------------------------------------------------------------

@router.get("/files/trash")
def files_trash_list():
    workspace = get_workspace_manager()
    return {"entries": TrashEngine(workspace.root).list_trash()}


@router.post("/files/trash/empty")
def files_trash_empty():
    workspace = get_workspace_manager()
    deleted = TrashEngine(workspace.root).empty_trash()
    return {"success": True, "deleted": deleted}


# ------------------------------------------------------------------
# HISTORY
# ------------------------------------------------------------------

@router.get("/files/history")
def files_history(path: Optional[str] = Query(default=None)):
    workspace = get_workspace_manager()
    return {"entries": HistoryEngine(workspace.root).list_history(path)}


@router.post("/files/history/{snapshot_id}/restore")
def files_history_restore(snapshot_id: str):
    workspace = get_workspace_manager()
    ok = HistoryEngine(workspace.root).restore(snapshot_id)

    if not ok:
        raise HTTPException(status_code=404, detail=f"Snapshot '{snapshot_id}' tidak ditemukan.")

    return {"success": True, "snapshot_id": snapshot_id}


# ------------------------------------------------------------------
# PERMISSIONS
# ------------------------------------------------------------------

@router.get("/files/permissions")
def files_permissions():
    return {"rules": get_permission_engine().list_rules()}


@router.post("/files/permissions/grant")
def files_permissions_grant(payload: GrantPermissionRequest):
    get_permission_engine().grant(payload.folder, payload.level)
    return {"success": True, "folder": payload.folder, "level": payload.level.value}


@router.post("/files/permissions/revoke")
def files_permissions_revoke(payload: MkdirRequest):
    get_permission_engine().revoke(payload.path)
    return {"success": True, "folder": payload.path}