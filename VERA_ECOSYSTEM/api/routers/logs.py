import time
from typing import Optional
from fastapi import APIRouter, Depends, Query
from core.tenant.auth_deps import require_permission

from core import log_store

router = APIRouter(prefix="/api/logs", tags=["logs"], dependencies=[Depends(require_permission("audit.read"))])


@router.get("")
def list_logs(
    category: Optional[str] = None,
    level: Optional[str] = None,
    search: Optional[str] = None,
    since_minutes: Optional[int] = None,
    limit: int = Query(100, le=500),
    offset: int = 0,
):
    since = time.time() - (since_minutes * 60) if since_minutes else None

    logs = log_store.query_logs(
        category=category, level=level, search=search,
        since=since, limit=limit, offset=offset,
    )
    total = log_store.count_logs(
        category=category, level=level, search=search, since=since,
    )

    return {"logs": logs, "total": total, "limit": limit, "offset": offset}


@router.get("/categories")
def categories():
    return {"categories": log_store.get_categories_with_counts()}


@router.get("/stats")
def stats(since_minutes: Optional[int] = None):
    since = time.time() - (since_minutes * 60) if since_minutes else None
    return {"stats": log_store.get_stats(since=since)}


@router.get("/{log_id}")
def get_log_detail(log_id: int):
    from fastapi import HTTPException

    log_entry = log_store.get_log_by_id(log_id)
    if not log_entry:
        raise HTTPException(status_code=404, detail="Log tidak ditemukan.")

    return log_entry


@router.delete("")
def clear(category: Optional[str] = None, older_than_days: Optional[int] = None):
    older_than = time.time() - (older_than_days * 86400) if older_than_days else None
    deleted = log_store.clear_logs(category=category, older_than=older_than)
    return {"success": True, "deleted": deleted}