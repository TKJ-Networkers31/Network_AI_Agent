"""
api/routers/ws.py — WebSocket realtime streaming untuk AIRA.

Menjalankan Brain.think() yang SAMA dengan REST - hanya transport-nya beda.

Ringkasan desain:
- Tiap giliran berjalan sebagai asyncio.Task terpisah (_run_turn), sementara
  loop receive tetap membaca pesan, sehingga {"type": "cancel"} bisa masuk
  saat proses berjalan. Task TIDAK dibatalkan saat socket putus: hasil tetap
  disimpan ke database.
- run_id per giliran ada di SEMUA event giliran itu; client memakainya untuk
  membuang event basi dari proses yang sudah di-stop.
- STOP: threading.Event dicek Planner di titik aman. Hasil giliran yang
  dihentikan dibuang (memory dikembalikan, tidak ada tulis ke database).
- EDIT PROMPT / REGENERATE: riwayat dipotong mulai turn tertentu; database
  baru dipotong SETELAH giliran pengganti sukses.
- Event realtime (thinking, tool_*, error non-fatal) mengalir:
  Planner/Brain -> Event Bus -> api/ws_bridge.py -> client. Event protokol
  milik ws.py sendiri (ack, transcript, response, cancelled, error fatal)
  dikirim langsung lewat _emit(); sebelum response/error/cancelled,
  bridge.flush() memastikan semua event tool tiba lebih dulu.
- STREAMING (Sprint 2.5): giliran teks/DIO/regenerate meminta provider
  streaming (stream_enabled_for_turn). Chunk sampai ke client sebagai
  stream_start / stream_delta lewat jalur bridge yang sama; "response" tetap
  menjadi event COMPLETE (answer utuh, + "streamed"). Kontrak lengkap:
  docs/api_guideline.md.

DIO submission (form/izin lokasi):
  Diproses lewat resolve_submission() (agents/rei/dio_tools.py) - helper
  yang SAMA dengan REST (chat.py). Karena resolve_submission() sinkron dan
  bisa melakukan HTTP (reverse_geocode, timeout hingga 4 detik), ia
  dijalankan lewat asyncio.to_thread supaya event loop (dan semua
  WebSocket lain) tidak macet.
"""

import asyncio
import base64
import logging
import threading
import time
import uuid

import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from agents.yuki.stt import transcribe
from agents.yuki.tts import synthesize_bytes
from agents.rei.dio_tools import resolve_submission
from api.state import get_memory, persist_memory, add_global_usage, drop_cache
from api.ws_bridge import get_ws_bridge, stream_enabled_for_turn
from api.ws_manager import manager
from core.brain import Brain
from core.events import event_scope, new_correlation_id
from core import chat_sessions as store
from core.orchestrator import AGENT_TOOL_MAP
from core.slash_commands import apply_slash_command

logger = logging.getLogger("aira.ws")

router = APIRouter(prefix="/ws", tags=["websocket"])

# session_id -> {"task": asyncio.Task, "cancel": threading.Event}
# Per SESI (bukan per koneksi) supaya cancel tetap menemukan proses yang
# berjalan walau socket sempat putus-nyambung.
_ACTIVE_RUNS: dict[str, dict] = {}


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


async def _emit(session_id: str, run_id, event_type: str, data: dict | None = None) -> None:
    """Event protokol milik ws.py sendiri (bukan event domain Event Bus)."""
    await manager.send(session_id, {
        "type": event_type,
        "data": {**(data or {}), "session_id": session_id, "run_id": run_id},
        "ts": time.time(),
    })


# ============================================================
# SATU GILIRAN (dijalankan sebagai asyncio.Task terpisah)
# ============================================================

async def _process_turn(session_id: str, raw: dict, cancel_event: threading.Event, run_id: str) -> None:
    msg_type = raw.get("type", "text")
    is_regenerate = msg_type == "regenerate"
    is_voice_turn = False
    display_message = ""

    bridge = get_ws_bridge()

    async def emit(event_type: str, data: dict | None = None) -> None:
        await _emit(session_id, run_id, event_type, data)

    async def fail(message: str) -> None:
        await bridge.flush()
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
    # DIO SUBMISSION: efek samping + instruksi LLM lewat SATU helper
    # (sama dengan REST). Sinkron + bisa HTTP -> jangan blok event loop.
    # --------------------------------------------------
    dio_submission = None if (msg_type == "voice_audio" or is_regenerate) else raw.get("dio_submission")

    if dio_submission:
        try:
            _, llm_message = await asyncio.to_thread(resolve_submission, dio_submission)
        except Exception as exc:
            logger.exception("WS resolve_submission gagal | session=%s", session_id)
            memory.history = backup_history
            await fail(str(exc))
            return
    elif regenerated_llm_message:
        llm_message = regenerated_llm_message
    else:
        llm_message = apply_slash_command(display_message, AGENT_TOOL_MAP)

    # --------------------------------------------------
    # PROSES: satu jalur reasoning (Brain.think()) untuk teks/suara/DIO.
    # Event realtime dipublish ke Event Bus dan sampai ke client lewat
    # WS bridge.
    # --------------------------------------------------
    brain = Brain(memory)
    use_stream = stream_enabled_for_turn(raw, is_voice_turn)

    await emit("ack", {"message": display_message})

    try:
        result = await asyncio.to_thread(brain.think, llm_message, cancel_event, use_stream)
    except Exception as exc:
        logger.exception("WS think() gagal | session=%s", session_id)
        memory.history = backup_history
        await fail(str(exc))  # fail() sudah flush bridge dulu
        return

    # Semua event tool/thinking yang sudah dipublish harus tiba di client
    # SEBELUM response/cancelled dikirim.
    await bridge.flush()

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
        "streamed": result.streamed,
        "session_title": row["title"] if row else "Chat baru",
        "audio_base64": audio_b64_out,
        "interaction_schema": result.interaction_schema,
        "user_turn_id": user_turn_id,
        "assistant_turn_id": assistant_turn_id,
    })


async def _run_turn(session_id: str, raw: dict, cancel_event: threading.Event) -> None:
    run_id = raw.get("run_id") or uuid.uuid4().hex[:12]

    try:
        # Semua event yang dipublish selama giliran ini (termasuk dari thread
        # pekerja) otomatis tertandai sesi + run + correlation_id yang sama.
        with event_scope(
            correlation_id=new_correlation_id(),
            session_id=session_id,
            run_id=run_id,
        ):
            await _process_turn(session_id, raw, cancel_event, run_id)
    except Exception:
        logger.exception("WS turn error tak terduga | session=%s", session_id)
        try:
            await _emit(session_id, run_id, "error", {
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

    # Idempotent: pastikan bridge Event Bus -> WebSocket aktif di loop ini
    # (normalnya sudah di-start di startup api/main.py).
    get_ws_bridge().ensure_started(asyncio.get_running_loop())

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