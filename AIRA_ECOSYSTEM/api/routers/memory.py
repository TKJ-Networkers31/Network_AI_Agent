from fastapi import APIRouter, HTTPException

from api.schemas import MemoryFactRequest
from core.memory import get_all_facts, remember_fact, forget_fact, get_recent_events

router = APIRouter(prefix="/api/memory", tags=["memory"])


@router.get("/facts")
def facts():
    return {"facts": get_all_facts()}


@router.post("/facts")
def add_fact(payload: MemoryFactRequest):
    return remember_fact(payload.key, payload.value)


@router.delete("/facts/{key}")
def delete_fact(key: str):
    result = forget_fact(key)

    if not result.get("success"):
        raise HTTPException(status_code=404, detail="Key tidak ditemukan.")

    return result


@router.get("/events")
def events(limit: int = 20):
    return {"events": get_recent_events(limit=limit)}
