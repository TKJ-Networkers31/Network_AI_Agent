"""
api/routers/ws.py — WebSocket realtime streaming untuk AIRA.

FIX (Voice Call Mode - PWA):
Menambahkan dukungan pesan bertipe "voice_audio" selain "text" (default,
untuk kompatibilitas mundur dengan client yang cuma kirim {"message": "..."}
tanpa field "type" sama sekali).

Alur voice_audio:
  1. Client kirim {"type": "voice_audio", "audio_base64": "...", "sample_rate": 16000}
     - audio adalah PCM 16-bit mono, hasil VAD di browser (satu utterance utuh).
  2. Server decode base64 -> numpy int16 -> agents/yuki/stt.py::transcribe()
     (faster-whisper, LOKAL, tidak butuh internet).
  3. Kalau transkrip kosong -> kirim event "transcript_empty", lanjut loop
     (TIDAK memanggil Brain.think() untuk teks kosong).
  4. Kalau ada teks -> kirim event "transcript" (supaya UI bisa tampilkan
     bubble "kamu bilang: ...") lalu diproses PERSIS SAMA seperti pesan teks
     biasa lewat Brain.think() - tidak ada chatbot kedua, cuma sumber input
     yang beda (lihat docs/constitution.md aturan #5).
  5. Kalau giliran ini berasal dari suara DAN jawaban berhasil -> sintesis
     balasan lewat agents/yuki/tts.py::synthesize_bytes() (Kokoro, LOKAL),
     lalu disisipkan sebagai "audio_base64" di event "response" supaya
     browser client yang memutarnya (BUKAN speaker server).

Pesan bertipe "text" (atau tanpa "type" sama sekali) berjalan identik
seperti sebelumnya - tidak ada perubahan perilaku untuk chat teks biasa.
"""

import asyncio
import base64
import logging
import queue
import time

import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from agents.yuki.stt import transcribe
from agents.yuki.tts import synthesize_bytes
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


def _decode_voice_audio(raw: dict) -> "np.ndarray | None":
    """
    Decode field audio_base64 (PCM16 mono, little-endian) jadi numpy
    int16 array. Return None kalau field kosong/rusak - pemanggil
    bertanggung jawab mengirim event error ke client.
    """
    audio_b64 = raw.get("audio_base64")

    if not audio_b64:
        return None

    try:
        raw_bytes = base64.b64decode(audio_b64)
        return np.frombuffer(raw_bytes, dtype=np.int16)
    except Exception:
        logger.exception("Gagal decode audio_base64 dari client")
        return None


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
            msg_type = raw.get("type", "text")

            is_voice_turn = False

            # --------------------------------------------------
            # SUMBER PESAN: audio (voice call mode) vs teks biasa
            # --------------------------------------------------
            if msg_type == "voice_audio":
                audio_int16 = _decode_voice_audio(raw)

                if audio_int16 is None or audio_int16.size == 0:
                    await manager.send(session_id, {
                        "type": "error",
                        "data": {"message": "Audio tidak valid atau kosong.", "session_id": session_id},
                    })
                    continue

                sample_rate = int(raw.get("sample_rate") or 16000)

                # faster-whisper (LOKAL) - tidak menyentuh internet sama sekali.
                text = await asyncio.to_thread(transcribe, audio_int16, sample_rate)

                if not text:
                    await manager.send(session_id, {
                        "type": "transcript_empty",
                        "data": {
                            "message": "Tidak terdengar ucapan yang jelas, coba lagi.",
                            "session_id": session_id,
                        },
                    })
                    continue

                display_message = text
                is_voice_turn = True

                # Kirim transkrip duluan supaya UI bisa langsung menampilkan
                # bubble "kamu bilang: ..." sebelum jawaban AI datang.
                await manager.send(session_id, {
                    "type": "transcript",
                    "data": {"text": display_message, "session_id": session_id},
                })

            else:
                display_message = (raw.get("message") or "").strip()

                if not display_message:
                    await manager.send(session_id, {
                        "type": "error",
                        "data": {"message": "Pesan kosong.", "session_id": session_id},
                    })
                    continue

            # --------------------------------------------------
            # PROSES: SAMA PERSIS untuk teks maupun suara - satu
            # jalur reasoning (Brain.think()), tidak ada percabangan
            # logic bisnis di sini.
            # --------------------------------------------------
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

            # --------------------------------------------------
            # SINTESIS SUARA BALASAN: HANYA kalau giliran ini berasal
            # dari audio DAN jawaban sukses. Giliran teks biasa TIDAK
            # pernah memicu TTS (audio_base64 = None), supaya chat teks
            # murni tidak berubah perilaku sama sekali.
            # --------------------------------------------------
            audio_b64_out = None

            if is_voice_turn and not result.error and result.answer:
                tts_bytes = await asyncio.to_thread(synthesize_bytes, result.answer)

                if tts_bytes:
                    audio_b64_out = base64.b64encode(tts_bytes).decode("ascii")
                else:
                    logger.warning(
                        "TTS gagal/tidak tersedia untuk session=%s - jawaban tetap "
                        "dikirim sebagai teks tanpa audio.", session_id,
                    )

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
                    "audio_base64": audio_b64_out,
                },
            })

    except WebSocketDisconnect:
        await manager.disconnect(session_id, websocket)
    except Exception:
        logger.exception("WS loop error tak terduga | session=%s", session_id)
        await manager.disconnect(session_id, websocket)