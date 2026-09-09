"""
Entry point FastAPI.

Jalankan dari ROOT PROJECT (D:\\data\\agent_ai\\), sama seperti
konvensi agent/main.py yang sudah kamu pakai, supaya import
`agent.*` dan `tools.*` bekerja:

    uvicorn backend.main:app --reload --port 8000

Kalau frontend sudah di-build (npm run build di folder frontend/,
hasilnya folder frontend/dist), file itu akan otomatis di-serve
di "/" oleh FastAPI juga - jadi di production kamu cukup jalankan
satu proses backend ini saja, tanpa perlu server terpisah untuk
frontend.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.routers import chat, providers, memory, devices, sessions, tools


BASE_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"


app = FastAPI(title="Network AI Agent - Web API")

# Dev: Vite dev server jalan di port 5173 (default), origin beda
# dari backend (8000) jadi butuh CORS. Di production (serve dari
# StaticFiles di bawah) origin-nya sama, CORS tidak lagi relevan
# tapi tidak masalah tetap aktif.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
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


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Serve build hasil `npm run build` (frontend/dist) sebagai static
# site di root "/". Kalau folder belum ada (misal kamu baru jalan
# dev server Vite terpisah), FastAPI tetap jalan normal untuk API
# saja - baris ini di-skip.
if FRONTEND_DIST.exists():
    app.mount(
        "/",
        StaticFiles(directory=str(FRONTEND_DIST), html=True),
        name="frontend",
    )
