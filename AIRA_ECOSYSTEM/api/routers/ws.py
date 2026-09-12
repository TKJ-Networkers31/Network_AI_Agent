"""
api/routers/ws.py — WebSocket realtime streaming untuk AIRA (Phase 0.5).

WAJIB TERPISAH dari REST /api/chat (chat.py TIDAK diubah). Endpoint ini
memanggil Brain.think() yang SAMA PERSIS dengan yang dipakai REST, jadi
tidak ada logic ganda / tidak ada "chatbot kedua" - cuma jalur transport
berbeda untuk event realtime (thinking/tool_start/.../response).

Brain.think() masih sepenuhnya SYNC (call_model pakai requests, SSH pakai
paramiko) - supaya tidak menghentikan event loop FastAPI, eksekusinya
didorong ke thread terpisah lewat asyncio.to_thread(), dan progress
di-relay balik lewat queue.Queue thread-safe yang di-drain oleh loop
asyncio di endpoint ini.
"""

import asyncio
import logging
import queue
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.state import get_memory, persist_memory, add_global_usage
from api.ws_manager import manager
from core.brain import Brain
from core import chat_sessions as store
from core.orchestrator import AGENT_TOOL_MAP

logger = logging.getLogger("aira.ws")

router = APIRouter(prefix="/ws", tags=["websocket"])

QUEUE_POLL_INTERVAL = 0.05  # detik, kecepatan drain queue -> socket


def _apply_slash_command(raw_message: str) -> str:
    """Duplikat kecil dari chat.py::_apply_slash_command - dipertahankan
    identik supaya perilaku '/tool ...' sama persis di WS maupun REST."""
    if not raw_message.startswith("/"):
        return raw_message

    parts = raw_message[1:].split(" ", 1)
    tool_name = parts[0].strip()
    rest = parts[1].strip() if len(parts) > 1 else ""

    if not tool_name or tool_name not in AGENT_TOOL_MAP:
        return raw_message

    instruction = rest or f"Jalankan tool {tool_name}."

    return (
        f"[Instruksi eksplisit dari user: WAJIB gunakan tool "
        f"'{tool_name}' untuk memenuhi permintaan berikut. Ambil "
        f"argumen yang diperlukan dari konteks kalimat ini.]\n"
        f"{instruction}"
    )


async def _drain_queue_to_socket(session_id: str, event_queue: "queue.Queue", stop_flag: dict) -> None:
    """
    Loop async yang membaca event_queue (diisi dari thread lain oleh
    on_event callback sync) dan mengirimkannya ke websocket, sampai
    stop_flag['done'] diset True DAN queue sudah kosong.
    """
    while True:
        drained_any = False

        while True:
            try:
                event = event_queue.get_nowait()
            except queue.Empty:
                break
            drained_any = True
            await manager.send(session_id, event)

        if stop_flag.get("done") and not drained_any:
            # pastikan tidak ada event yang datang tepat setelah flag
            # di-set tapi sebelum drain terakhir - cek sekali lagi.
            if event_queue.empty():
                break

        if not drained_any:
            await asyncio.sleep(QUEUE_POLL_INTERVAL)


@router.websocket("/chat/{session_id}")
async def chat_ws(websocket: WebSocket, session_id: str):
    await manager.connect(session_id, websocket)

    # Pastikan sesi ada di storage (sama seperti chat.py membuat sesi
    # kalau belum ada) - kalau belum ada, biarkan seperti apa adanya;
    # frontend selalu kirim session_id yang sudah dibuat lewat REST
    # POST /api/sessions atau hasil chat REST sebelumnya. Kalau belum
    # ada baris sesi di DB, chat_turns tetap tidak akan gagal karena
    # add_turn tidak melakukan foreign-key check.
    try:
        while True:
            raw = await websocket.receive_json()
            display_message = (raw.get("message") or "").strip()

            if not display_message:
                await manager.send(session_id, {"type": "error", "data": {"message": "Pesan kosong."}})
                continue

            llm_message = _apply_slash_command(display_message)
            memory = get_memory(session_id)
            brain = Brain(memory)

            event_queue: "queue.Queue" = queue.Queue()
            stop_flag = {"done": False}

            def on_event(event_type: str, payload: dict) -> None:
                # Dipanggil dari THREAD LAIN (worker asyncio.to_thread) -
                # queue.Queue thread-safe, aman dipanggil langsung tanpa
                # loop.call_soon_threadsafe.
                event_queue.put({
                    "type": event_type,
                    "data": payload,
                    "ts": time.time(),
                })

            await manager.send(session_id, {"type": "ack", "data": {"message": display_message}})

            think_task = asyncio.create_task(
                asyncio.to_thread(brain.think, llm_message, on_event)
            )
            drain_task = asyncio.create_task(
                _drain_queue_to_socket(session_id, event_queue, stop_flag)
            )

            try:
                result = await think_task
            except Exception as exc:
                logger.exception("WS think() gagal | session=%s", session_id)
                stop_flag["done"] = True
                await drain_task
                await manager.send(session_id, {"type": "error", "data": {"message": str(exc)}})
                continue

            stop_flag["done"] = True
            await drain_task  # pastikan semua event sudah terkirim sebelum "response"

            persist_memory(session_id, memory)
            add_global_usage(result.token_usage)

            store.add_turn(session_id, "user", display_message)
            store.add_turn(session_id, "assistant", result.answer, steps=result.steps)
            store.maybe_autotitle(session_id, display_message)

            row = store.get_session_row(session_id)

            await manager.send(session_id, {
                "type": "response",
                "data": {
                    "answer": result.answer,
                    "steps": result.steps,
                    "duration": result.duration,
                    "token_usage": result.token_usage,
                    "error": result.error,
                    "session_id": session_id,
                    "session_title": row["title"] if row else "Chat baru",
                },
            })

    except WebSocketDisconnect:
        await manager.disconnect(session_id, websocket)
    except Exception:
        logger.exception("WS loop error tak terduga | session=%s", session_id)
        await manager.disconnect(session_id, websocket)