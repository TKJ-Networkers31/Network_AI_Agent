"""
api/main.py — entry point FastAPI untuk AIRA.

Jalankan dari root AIRA_ECOSYSTEM/:
    uvicorn api.main:app --reload --port 8000

Startup:
- Lokasi hosting dihangatkan di thread terpisah (chat pertama tidak menunggu).
- WebSocketEventBridge di-start di event loop utama (sekaligus bind_loop
  ke Event Bus).
- Interaction memory dibersihkan dari entri kedaluwarsa (purge_expired).
Shutdown:
- Bridge dihentikan rapi, semua sesi SSH APCE ditutup.

Perubahan (Sprint 2.6, Worker 1 — Global Settings Engine): mendaftarkan
api/routers/settings.py, mengikuti pola router lain di bawah — satu-satunya
perubahan pada file ini untuk fitur tersebut.

Perubahan (Sprint 2.7, Wave 1, Worker 2 — Universal Attachment): mendaftarkan
api/routers/attachments.py, mengikuti pola yang sama persis (satu baris
import + satu baris include_router, tidak ada logic baru di file ini).
"""

import asyncio
import threading
from pathlib import Path

from core.logger import setup_logging

setup_logging()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routers import chat, providers, memory, devices, sessions, tools, logs, models, persona, connections, files, location, settings, selection, attachments
from api.routers import ws
from api.ws_bridge import get_ws_bridge
from agents.akane.connection_manager import get_connection_manager
from core.dio import get_interaction_memory
from core.location import location_service


BASE_DIR = Path(__file__).resolve().parents[1]
APP_DIST = BASE_DIR / "app" / "frontend" / "dist"

app = FastAPI(title="AIRA Ecosystem API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(providers.router)
app.include_router(memory.router)
app.include_router(devices.router)
app.include_router(sessions.router)
app.include_router(tools.router)
app.include_router(logs.router)
app.include_router(models.router)
app.include_router(persona.router)
app.include_router(connections.router)
app.include_router(files.router)
app.include_router(location.router)
app.include_router(settings.router)
app.include_router(selection.router)
app.include_router(attachments.router)
app.include_router(ws.router)


def _warm_host_location() -> None:
    try:
        location_service.get_host()
    except Exception:
        pass


@app.on_event("startup")
def _startup_location():
    threading.Thread(target=_warm_host_location, daemon=True).start()


@app.on_event("startup")
def _startup_purge_interaction_memory():
    try:
        get_interaction_memory().purge_expired()
    except Exception:
        pass


@app.on_event("startup")
async def _startup_event_bridge():
    # Async supaya berjalan DI event loop utama (loop yang sama dengan
    # WebSocket) - bridge mengikat loop ini ke Event Bus.
    get_ws_bridge().start(asyncio.get_running_loop())


@app.on_event("shutdown")
async def _shutdown_event_bridge():
    await get_ws_bridge().stop()


@app.on_event("shutdown")
def _shutdown_connections():
    get_connection_manager().shutdown()


@app.get("/api/health")
def health():
    return {"status": "ok", "ecosystem": "AIRA"}


if APP_DIST.exists():
    app.mount("/", StaticFiles(directory=str(APP_DIST), html=True), name="app")