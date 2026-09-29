"""
api/main.py — entry point FastAPI untuk AIRA.

Jalankan dari root AIRA_ECOSYSTEM/:
    uvicorn api.main:app --reload --port 8000

Startup:
- Lokasi hosting dihangatkan di thread terpisah (chat pertama tidak menunggu).
- WebSocketEventBridge di-start di event loop utama (sekaligus bind_loop
  ke Event Bus).
- Interaction memory dibersihkan dari entri kedaluwarsa (purge_expired).
- (SPRINT 2.7.1 P0) Capability Registry dipopulasi dari tool schemas
  (AGENT_TOOL_SCHEMAS) dan dari External Context provider (Google Maps).
  Kedua fungsi register_* SUDAH ADA sejak Sprint 2.7
  (core/capability/integration.py, core/external_context/capability_bridge.py)
  tapi tidak pernah dipanggil sebelumnya.
Shutdown:
- Bridge dihentikan rapi, semua sesi SSH APCE ditutup.

SPRINT 2.7.1 (P0 Recovery): file ini sekarang juga mendaftarkan
api/routers/vision.py dan api/routers/workspace_links.py (sudah ada sejak
Sprint 2.7 tapi tidak pernah di-include_router - 404 di production), serta
api/routers/capabilities.py dan api/routers/artifacts.py (baru, thin HTTP
adapter di atas core/capability dan core/artifacts yang sudah ada -
BUKAN subsistem baru).
"""

import asyncio
import logging
import threading
from pathlib import Path

from core.logger import setup_logging

setup_logging()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routers import (
    chat, providers, memory, devices, sessions, tools, logs, models, persona,
    connections, files, location, settings, selection, attachments,
    vision, workspace_links, capabilities, artifacts,
)
from api.routers import ws
from api.ws_bridge import get_ws_bridge
from agents.akane.connection_manager import get_connection_manager
from core.dio import get_interaction_memory
from core.location import location_service
from core.capability import Capability, CapabilityUIMetadata, get_capability_registry


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
app.include_router(vision.router)          # === SPRINT 2.7.1 P0 FIX ===
app.include_router(workspace_links.router)  # === SPRINT 2.7.1 P0 FIX ===
app.include_router(capabilities.router)     # === SPRINT 2.7.1 P0 FIX (baru) ===
app.include_router(artifacts.router)        # === SPRINT 2.7.1 P0 FIX (baru) ===
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
def register_ui_capabilities():
    reg = get_capability_registry()
    defs = [
        ("ui.health_check", "Health check router", "tool", "hero",
         "Cek health check semua router: identity, resource (CPU/RAM/uptime), dan status interface. Buka koneksi dulu kalau perlu."),
        ("ui.network_report", "Laporan jaringan", "folder", "capability_dock",
         "Buatkan laporan status jaringan dalam file docx yang bisa saya unduh."),
        ("ui.list_connections", "Koneksi aktif", "link", "capability_dock",
         "Tampilkan semua koneksi SSH yang sedang aktif."),
    ]
    for cid, label, icon, group, prompt in defs:
        try:
            reg.register(Capability(
                id=cid, name=label, ui=CapabilityUIMetadata(label=label, icon=icon, group=group),
                metadata={"action": {"type": "prompt", "prompt": prompt}},
            ), overwrite=True)
        except Exception:
            pass

def _startup_capability_registry():
    """
    (SPRINT 2.7.1 P0.1) Populate the Capability Registry so GET
    /api/capabilities (and every frontend area reading from it - Hero,
    Composer Cockpit dock, chat input slot, message actions) actually has
    something to return. Both register_* functions already existed since
    Sprint 2.7 but were never invoked anywhere in the app.
    """
    logger = logging.getLogger("aira.startup.capability")

    try:
        from core.orchestrator import AGENT_TOOL_SCHEMAS, AGENT_TOOL_CATEGORY, DANGEROUS_TOOLS
        from core.capability.integration import register_tool_capabilities

        result = register_tool_capabilities(AGENT_TOOL_SCHEMAS, AGENT_TOOL_CATEGORY, DANGEROUS_TOOLS)
        logger.info(
            "CAPABILITY | tool bridge: %d registered, %d skipped, %d error.",
            len(result["registered"]), len(result["skipped"]), len(result["errors"]),
        )
    except Exception:
        logger.exception("Gagal registrasi tool capabilities saat startup.")

    try:
        from core.external_context.factory import get_google_maps_provider
        from core.external_context.capability_bridge import register_provider_capabilities

        result = register_provider_capabilities(get_google_maps_provider())
        logger.info("CAPABILITY | provider bridge: %d registered.", len(result["registered"]))
    except Exception:
        logger.exception("Gagal registrasi provider capabilities saat startup.")
    try:
        register_ui_capabilities()
    except Exception:
        logger.exception("Gagal registrasi UI capabilities.")


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
