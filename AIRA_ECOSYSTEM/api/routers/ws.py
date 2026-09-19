"""
api/routers/ws.py — WebSocket realtime streaming untuk AIRA.

FIX (Optimalisasi DIO):
Pesan client sekarang boleh menyertakan field "dio_submission" (di luar
"type": "voice_audio") - dipakai untuk hasil submit form/pilihan
interaktif DIO. Efek sampingnya dijalankan lewat
agents.rei.dio_tools.submit_structured_input() sebelum Brain.think(),
dan interaction_schema hasil giliran ini disertakan di event "response"
+ disimpan ke chat_turns, sama seperti jalur REST (chat.py).

PERUBAHAN (Chat Session: stop / edit prompt / regenerate / multi-sesi):

1. RECEIVE-LOOP KONKUREN. Sebelumnya satu giliran diproses DI DALAM loop
   receive (await think_task), sehingga selama AI bekerja server tidak
   membaca pesan apa pun dari client. Sekarang tiap giliran dijalankan
   sebagai asyncio.Task terpisah (_run_turn), dan loop receive tetap
   membaca - inilah yang memungkinkan pesan {"type": "cancel"} sampai
   ke server saat proses masih berjalan. Task TIDAK dibatalkan saat
   socket putus (mis. user pindah sesi/reload): hasil tetap disimpan ke
   database, sama seperti perilaku sebelumnya.

2. run_id. Client mengirim "run_id" per giliran; server menyertakannya di
   SEMUA event giliran itu (ack/thinking/tool_*/response/error/cancelled).
   Client memakainya untuk membuang event basi dari proses yang sudah
   di-stop, supaya tidak "bocor" ke giliran berikutnya.

3. STOP: {"type": "cancel"} men-set threading.Event yang dicek Planner di
   titik-titik aman. Hasil giliran yang dihentikan DIBUANG: memory
   dikembalikan ke kondisi sebelum giliran, tidak ada yang ditulis ke
   database. Kalau user langsung kirim pesan baru sementara proses lama
   masih menyelesaikan panggilan LLM/tool terakhirnya, pesan baru
   menunggu proses lama selesai dulu.

4. EDIT PROMPT: {"message": "...", "replace_from_turn_id": <id>} -
   REGENERATE: {"type": "regenerate", "replace_from_turn_id": <id user turn>}
   Riwayat dipotong mulai turn itu, lalu giliran baru dijalankan. Pemotongan
   di DATABASE baru dilakukan SETELAH giliran pengganti sukses - kalau
   di-stop atau error, percakapan lama tetap utuh.

5. Event "response" sekarang membawa "user_turn_id" & "assistant_turn_id"
   (id baris chat_turns) - dipakai frontend sebagai identitas pesan untuk
   edit/regenerate. Error yang berasal dari server sendiri (bukan dari
   planner) diberi "fatal": true.

Sisanya (voice call mode, slash command teks biasa) TIDAK BERUBAH.
"""

import asyncio
import base64
import logging
import queue
import threading
import time
import uuid

import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from agents.yuki.stt import transcribe
from agents.yuki.tts import synthesize_bytes
from agents.rei.dio_tools import submit_structured_input, build_submission_message
from api.state import get_memory, persist_memory, add_global_usage, drop_cache
from api.ws_manager import manager
from core.brain import Brain
from core import chat_sessions as store
from core.orchestrator import AGENT_TOOL_MAP

logger = logging.getLogger("aira.ws")

router = APIRouter(prefix="/ws", tags=["websocket"])

QUEUE_POLL_INTERVAL = 0.05

# session_id -> {"task": asyncio.Task, "cancel": threading.Event}
# Per SESI (bukan per koneksi) supaya cancel tetap menemukan proses yang
# berjalan walau socket sempat putus-nyambung.
_ACTIVE_RUNS: dict[str, dict] = {}


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


async def _emit(session_id: str, run_id, event_type: str, data: dict | None = None) -> None:
    await manager.send(session_id, {
        "type": event_type,
        "data": {**(data or {}), "session_id": session_id, "run_id": run_id},
        "ts": time.time(),
    })


# ============================================================
# SATU GILIRAN (dijalankan sebagai asyncio.Task terpisah)
# ============================================================

async def _process_turn(session_id: str, raw: dict, cancel_event: threading.Event) -> None:
    msg_type = raw.get("type", "text")
    run_id = raw.get("run_id") or uuid.uuid4().hex[:12]
    is_regenerate = msg_type == "regenerate"
    is_voice_turn = False
    display_message = ""

    async def emit(event_type: str, data: dict | None = None) -> None:
        await _emit(session_id, run_id, event_type, data)

    async def fail(message: str) -> None:
        await emit("error", {"message": message, "fatal": True})

    replace_from = None
    if raw.get("replace_from_turn_id") is not None:
        try:
            replace_from = int(raw["replace_from_turn_id"])
        except (TypeError, ValueError):
            await fail("replace_from_turn_id tidak valid.")
            return

    if is_regenerate and replace_from is None:
        await fail("Regenerate butuh replace_from_turn_id.")
        return

    # --------------------------------------------------
    # SUMBER PESAN: audio (voice call mode) / teks biasa / regenerate
    # --------------------------------------------------
    if msg_type == "voice_audio":
        audio_int16 = _decode_voice_audio(raw)

        if audio_int16 is None or audio_int16.size == 0:
            await fail("Audio tidak valid atau kosong.")
            return

        sample_rate = int(raw.get("sample_rate") or 16000)

        text = await asyncio.to_thread(transcribe, audio_int16, sample_rate)

        if not text:
            await emit("transcript_empty", {
                "message": "Tidak terdengar ucapan yang jelas, coba lagi.",
            })
            return

        display_message = text
        is_voice_turn = True

        await emit("transcript", {"text": display_message})

    elif is_regenerate:
        pass  # display_message diambil dari turn asli di bawah

    else:
        display_message = (raw.get("message") or "").strip()

        if not display_message:
            await fail("Pesan kosong.")
            return

    if cancel_event.is_set():
        await emit("cancelled")
        return

    if not store.get_session_row(session_id):
        # Sesi dihapus user selagi proses berjalan / sebelum dimulai.
        drop_cache(session_id)
        await emit("cancelled")
        return

    # --------------------------------------------------
    # EDIT / REGENERATE: siapkan memory (TANPA menyentuh database dulu)
    # --------------------------------------------------
    memory = get_memory(session_id)
    backup_history = list(memory.history)  # dikembalikan kalau di-stop / error
    regenerated_llm_message = None

    if replace_from is not None:
        target = store.get_turn(session_id, replace_from)

        if not target:
            await fail("Pesan yang ingin diubah tidak ditemukan (mungkin sudah dihapus).")
            return

        removed_user_turns = store.count_user_turns_from(session_id, replace_from)

        if is_regenerate:
            if target["role"] != "user":
                await fail("Regenerate hanya bisa dimulai dari pesan user.")
                return

            display_message = target["content"]
            regenerated_llm_message = store.find_user_message_from_end(
                backup_history, removed_user_turns,
            )

        memory.history = store.truncate_history_by_user_turns(backup_history, removed_user_turns)

    # --------------------------------------------------
    # DIO SUBMISSION: efek samping dulu, lalu bangun
    # instruksi LLM dari data form - alih-alih slash command.
    # --------------------------------------------------
    dio_submission = None if (msg_type == "voice_audio" or is_regenerate) else raw.get("dio_submission")

    if dio_submission:
        submission_result = submit_structured_input(
            schema_id=dio_submission.get("schema_id", ""),
            action_id=dio_submission.get("action_id", ""),
            values=dio_submission.get("values"),
            cancelled=bool(dio_submission.get("cancelled")),
        )
        _, llm_message = build_submission_message(
            dio_submission,
            pending_location=submission_result.get("pending_location"),
            location_result=submission_result.get("location_result"),
        )
    elif regenerated_llm_message:
        llm_message = regenerated_llm_message
    else:
        llm_message = _apply_slash_command(display_message)

    # --------------------------------------------------
    # PROSES: SAMA PERSIS untuk teks/suara/dio_submission -
    # satu jalur reasoning (Brain.think()).
    # --------------------------------------------------
    brain = Brain(memory)

    event_queue: "queue.Queue" = queue.Queue()
    stop_flag = {"done": False}

    def on_event(event_type: str, payload: dict) -> None:
        event_queue.put({
            "type": event_type,
            "data": {**payload, "session_id": session_id, "run_id": run_id},
            "ts": time.time(),
        })

    await emit("ack", {"message": display_message})

    think_task = asyncio.create_task(
        asyncio.to_thread(brain.think, llm_message, on_event, cancel_event)
    )
    drain_task = asyncio.create_task(
        _drain_queue_to_socket(session_id, event_queue, stop_flag)
    )

    try:
        result = await think_task
    except Exception as exc:
        logger.exception("WS think() gagal | session=%s", session_id)
        memory.history = backup_history
        stop_flag["done"] = True
        await drain_task
        await fail(str(exc))
        return

    stop_flag["done"] = True
    await drain_task

    # --------------------------------------------------
    # DIHENTIKAN USER: buang hasil, kembalikan memory, JANGAN tulis DB.
    # --------------------------------------------------
    if result.cancelled or cancel_event.is_set():
        memory.history = backup_history
        await emit("cancelled")
        return

    if not store.get_session_row(session_id):
        drop_cache(session_id)
        await emit("cancelled")
        return

    # --------------------------------------------------
    # SUKSES: baru sekarang database boleh diubah.
    # --------------------------------------------------
    if replace_from is not None:
        store.truncate_turns_from(session_id, replace_from)

    persist_memory(session_id, memory)
    add_global_usage(result.token_usage)

    user_turn_id = store.add_turn(session_id, "user", display_message)
    assistant_turn_id = store.add_turn(
        session_id, "assistant", result.answer,
        steps=result.steps, interaction_schema=result.interaction_schema,
    )
    store.maybe_autotitle(session_id, display_message)

    row = store.get_session_row(session_id)

    # --------------------------------------------------
    # SINTESIS SUARA BALASAN: HANYA kalau giliran ini
    # berasal dari audio DAN jawaban sukses.
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

    await emit("response", {
        "answer": result.answer,
        "steps": result.steps,
        "duration": result.duration,
        "token_usage": result.token_usage,
        "error": result.error,
        "session_title": row["title"] if row else "Chat baru",
        "audio_base64": audio_b64_out,
        "interaction_schema": result.interaction_schema,
        "user_turn_id": user_turn_id,
        "assistant_turn_id": assistant_turn_id,
    })


async def _run_turn(session_id: str, raw: dict, cancel_event: threading.Event) -> None:
    try:
        await _process_turn(session_id, raw, cancel_event)
    except Exception:
        logger.exception("WS turn error tak terduga | session=%s", session_id)
        try:
            await _emit(session_id, raw.get("run_id"), "error", {
                "message": "Terjadi kesalahan tak terduga di server.",
                "fatal": True,
            })
        except Exception:
            pass


def _cleanup_run(session_id: str, task: "asyncio.Task") -> None:
    run = _ACTIVE_RUNS.get(session_id)
    if run and run["task"] is task:
        _ACTIVE_RUNS.pop(session_id, None)


# ============================================================
# ENDPOINT
# ============================================================

@router.websocket("/chat/{session_id}")
async def chat_ws(websocket: WebSocket, session_id: str):
    await manager.connect(session_id, websocket)

    try:
        while True:
            raw = await websocket.receive_json()
            msg_type = raw.get("type", "text")

            # ---- STOP ----
            if msg_type == "cancel":
                run = _ACTIVE_RUNS.get(session_id)
                if run:
                    run["cancel"].set()
                continue

            # ---- masih ada proses berjalan di sesi ini? ----
            run = _ACTIVE_RUNS.get(session_id)

            if run and not run["task"].done():
                if run["cancel"].is_set():
                    # Proses lama sudah di-stop tapi masih menyelesaikan
                    # panggilan LLM/tool terakhirnya - tunggu sebentar.
                    await run["task"]
                else:
                    await _emit(session_id, raw.get("run_id"), "error", {
                        "message": "Chat ini masih memproses permintaan sebelumnya. Tekan Stop dulu atau tunggu selesai.",
                        "fatal": True,
                        "busy": True,
                    })
                    continue

            cancel_event = threading.Event()
            task = asyncio.create_task(_run_turn(session_id, raw, cancel_event))
            _ACTIVE_RUNS[session_id] = {"task": task, "cancel": cancel_event}
            task.add_done_callback(lambda t, sid=session_id: _cleanup_run(sid, t))

    except WebSocketDisconnect:
        # Task yang sedang berjalan SENGAJA tidak dibatalkan: hasilnya tetap
        # disimpan ke database dan dikirim ke socket baru bila ada.
        await manager.disconnect(session_id, websocket)
    except Exception:
        logger.exception("WS loop error tak terduga | session=%s", session_id)
        await manager.disconnect(session_id, websocket)