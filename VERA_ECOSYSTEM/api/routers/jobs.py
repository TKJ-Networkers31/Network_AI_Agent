"""
api/routers/jobs.py — Durable Background Jobs & Task Execution API for VERA.

Provides endpoints for inspecting, tracking, resuming, and managing persistent background
execution tasks, diagnostics, and long-running operations.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from core.job_store import DurableJob, JobEvent, JobState, get_job_store
from core.tenant.manager import IdentityManager

logger = logging.getLogger("vera.api.jobs")

router = APIRouter(prefix="/api/v1/jobs", tags=["durable-jobs"])


async def get_optional_user(request: Request) -> Optional[Any]:
    auth_header = request.headers.get("Authorization") or request.cookies.get("vera_token")
    if not auth_header:
        return None
    token = auth_header.replace("Bearer ", "").strip()
    try:
        return IdentityManager().validate_session_token(token)
    except Exception:
        return None


class JobCreateRequest(BaseModel):
    job_type: str = Field(..., description="Type of background job, e.g. network_diagnostic, topology_scan")
    title: str = Field(..., description="Human readable title")
    session_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    checkpoint_data: Optional[Dict[str, Any]] = None


class JobCancelRequest(BaseModel):
    reason: str = Field(default="Cancelled by user", description="Reason for cancellation")


@router.get("", response_model=Dict[str, Any])
def list_jobs(
    session_id: Optional[str] = Query(None, description="Filter by chat session ID"),
    state: Optional[str] = Query(None, description="Filter by job state (RUNNING, SUCCEEDED, etc.)"),
    limit: int = Query(50, ge=1, le=200),
    user_ctx: Optional[Any] = Depends(get_optional_user),
):
    """List recent durable background jobs."""
    store = get_job_store()
    user_id = user_ctx.user_id if user_ctx and hasattr(user_ctx, "user_id") else None
    jobs = store.list_jobs(session_id=session_id, user_id=user_id, state=state, limit=limit)
    return {
        "status": "success",
        "total": len(jobs),
        "jobs": [job.to_dict() for job in jobs],
    }


@router.get("/active", response_model=Dict[str, Any])
def get_active_job(
    session_id: str = Query(..., description="Session ID to inspect for active job"),
):
    """Retrieve the currently active background job for a given session, if any."""
    store = get_job_store()
    job = store.get_active_job_for_session(session_id)
    if not job:
        return {"status": "idle", "active_job": None}
    return {
        "status": "active",
        "active_job": job.to_dict(),
    }


@router.get("/{job_id}", response_model=Dict[str, Any])
def get_job_details(job_id: str):
    """Get details of a specific durable job."""
    store = get_job_store()
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "status": "success",
        "job": job.to_dict(),
    }


@router.get("/{job_id}/events", response_model=Dict[str, Any])
def get_job_events(
    job_id: str,
    since_id: int = Query(0, ge=0, description="Retrieve events with id greater than since_id"),
    limit: int = Query(100, ge=1, le=500),
):
    """Retrieve the event replay stream for a durable job."""
    store = get_job_store()
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    events = store.get_events_for_job(job_id, since_id=since_id, limit=limit)
    return {
        "status": "success",
        "job_id": job_id,
        "total_events": len(events),
        "events": [e.to_dict() for e in events],
    }


@router.post("", response_model=Dict[str, Any])
def create_job(
    payload: JobCreateRequest,
    user_ctx: Optional[Any] = Depends(get_optional_user),
):
    """Create a new durable background job."""
    store = get_job_store()
    user_id = user_ctx.user_id if user_ctx and hasattr(user_ctx, "user_id") else None
    tenant_id = user_ctx.tenant_id if user_ctx and hasattr(user_ctx, "tenant_id") else None

    job = store.create_job(
        job_type=payload.job_type,
        title=payload.title,
        session_id=payload.session_id,
        user_id=user_id,
        tenant_id=tenant_id,
        idempotency_key=payload.idempotency_key,
        checkpoint_data=payload.checkpoint_data,
    )
    return {
        "status": "success",
        "job": job.to_dict(),
    }


@router.post("/{job_id}/cancel", response_model=Dict[str, Any])
def cancel_job(job_id: str, payload: JobCancelRequest = JobCancelRequest()):
    """Cancel a running or queued job."""
    store = get_job_store()
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    cancelled = store.cancel_job(job_id, reason=payload.reason)
    return {
        "status": "success",
        "job": cancelled.to_dict() if cancelled else None,
    }
