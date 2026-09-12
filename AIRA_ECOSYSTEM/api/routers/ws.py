"""
api/routers/ws.py — WebSocket realtime streaming untuk AIRA.
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

QUEUE_POLL_INTERVAL = 0.05


def _apply_slash_command(raw_message: str) -> str:
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
            if event_queue.empty():
                break

        if not drained_any:
            await asyncio.sleep(QUEUE_POLL_INTERVAL)


@router.websocket("/chat/{session_id}")
async def chat_ws(websocket: WebSocket, session_id: str):
    await manager.connect(session_id, websocket)

    try:
        while True:
            raw = await websocket.receive_json()
            display_message = (raw.get("message") or "").strip()

            if not display_message:
                await manager.send(session_id, {
                    "type": "error",
                    "data": {"message": "Pesan kosong.", "session_id": session_id},
                })
                continue

            llm_message = _apply_slash_command(display_message)
            memory = get_memory(session_id)
            brain = Brain(memory)

            event_queue: "queue.Queue" = queue.Queue()
            stop_flag = {"done": False}

            def on_event(event_type: str, payload: dict) -> None:
                event_queue.put({
                    "type": event_type,
                    "data": {**payload, "session_id": session_id},
                    "ts": time.time(),
                })

            await manager.send(session_id, {
                "type": "ack",
                "data": {"message": display_message, "session_id": session_id},
            })

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
                await manager.send(session_id, {
                    "type": "error",
                    "data": {"message": str(exc), "session_id": session_id},
                })
                continue

            stop_flag["done"] = True
            await drain_task

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