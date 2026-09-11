from typing import Any, Optional
from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = "default"


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