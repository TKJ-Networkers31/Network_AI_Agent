"""
api/main.py — entry point FastAPI untuk AIRA.

Jalankan dari root AIRA_ECOSYSTEM/:
    uvicorn api.main:app --reload --port 8000
"""

from pathlib import Path

from core.logger import setup_logging

# WAJIB dipanggil SEBELUM import lain yang bisa melakukan logging
# (agents/*, core/orchestrator, dst) - supaya handler sudah terpasang
# begitu request pertama masuk.
setup_logging()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routers import chat, providers, memory, devices, sessions, tools, logs



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


@app.get("/api/health")
def health():
    return {"status": "ok", "ecosystem": "AIRA"}


if APP_DIST.exists():
    app.mount("/", StaticFiles(directory=str(APP_DIST), html=True), name="app")


