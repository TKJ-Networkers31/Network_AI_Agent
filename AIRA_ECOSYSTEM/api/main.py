"""
api/main.py — entry point FastAPI untuk AIRA.

Jalankan dari root AIRA_ECOSYSTEM/:
    uvicorn api.main:app --reload --port 8000

FIX (Optimalisasi APCE):
Menambahkan shutdown event yang memanggil ConnectionManager.shutdown() -
sebelumnya method ini sudah ada tapi tidak pernah dipanggil siapa pun,
sehingga channel SSH APCE tidak ditutup rapi saat server di-restart/
reload (mis. lewat --reload saat development).
"""

from pathlib import Path

from core.logger import setup_logging

setup_logging()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routers import chat, providers, memory, devices, sessions, tools, logs, models, persona, connections, files
from api.routers import ws
from agents.akane.connection_manager import get_connection_manager


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
app.include_router(ws.router)


@app.on_event("shutdown")
def _shutdown_connections():
    get_connection_manager().shutdown()


@app.get("/api/health")
def health():
    return {"status": "ok", "ecosystem": "AIRA"}


if APP_DIST.exists():
    app.mount("/", StaticFiles(directory=str(APP_DIST), html=True), name="app")