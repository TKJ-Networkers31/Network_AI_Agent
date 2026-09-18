from typing import Any, Optional
from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = "default"
    # FIX (Optimalisasi DIO): payload submission dari form/pilihan
    # interaktif. Bentuk: {"schema_id": str, "action_id": str,
    # "values": dict, "cancelled": bool}. Kalau diisi, backend
    # membangun instruksi LLM dari data ini alih-alih memakai
    # `message` mentah - lihat api/routers/chat.py.
    dio_submission: Optional[dict] = None


class ChatStep(BaseModel):
    type: str
    name: Optional[str] = None
    category: Optional[str] = None
    arguments: Optional[dict] = None
    success: Optional[bool] = None
    duration: Optional[float] = None
    result_preview: Optional[str] = None
    message: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    steps: list[ChatStep]
    duration: float
    token_usage: Optional[dict] = None
    error: bool = False
    session_id: str
    session_title: str
    # FIX (Optimalisasi DIO): Universal Interaction Schema (dict) kalau
    # giliran ini memanggil request_structured_input - None kalau tidak.
    interaction_schema: Optional[dict] = None


class ResetRequest(BaseModel):
    session_id: Optional[str] = "default"


class ProviderSelectRequest(BaseModel):
    key: str


class MemoryFactRequest(BaseModel):
    key: str
    value: str


class MemoryFactDelete(BaseModel):
    key: str


class SessionRenameRequest(BaseModel):
    title: Optional[str] = None