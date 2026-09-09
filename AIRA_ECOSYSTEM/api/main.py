"""
api/main.py — entry point FastAPI + WebSocket untuk AIRA.

Pengganti backend/main.py lama. Perbedaan utama dari versi lama: router
TIDAK BOLEH lagi import `tools.registry`/`agent.core.engine` langsung -
semua chat masuk lewat `core.brain.Brain`, yang di baliknya baru
memanggil orchestrator -> REI -> AKANE/HIKARI/YUKI.

WebSocket ditambahkan di sini (belum ada di backend/main.py lama yang
masih pure REST) untuk streaming step-by-step tool call ke frontend
secara real-time, sesuai spesifikasi "FastAPI + WebSocket" di master
prompt.

Jalankan dari root AIRA_ECOSYSTEM/:
    uvicorn api.main:app --reload --port 8000
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# TODO: aktifkan setelah router dipindah & disesuaikan (Tahap 2 migrasi)
# from api.routers import chat, providers, memory, devices, sessions, tools, ws

BASE_DIR = Path(__file__).resolve().parents[1]
APP_DIST = BASE_DIR / "app" / "dist"

app = FastAPI(title="AIRA Ecosystem API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# TODO: app.include_router(chat.router)  dst - lihat MIGRATION_PLAN.md Tahap 2


@app.get("/api/health")
def health():
    return {"status": "ok", "ecosystem": "AIRA"}


if APP_DIST.exists():
    app.mount("/", StaticFiles(directory=str(APP_DIST), html=True), name="app")
