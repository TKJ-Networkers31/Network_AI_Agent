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
from core.vae import brain_response_to_vae_payload

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


def update_active_run_event(session_id: str, event_type: str, data: dict) -> None:
    """Updates the in-memory active run cache and logs durable event history."""
    run = _ACTIVE_RUNS.get(session_id)
    if not run:
        return

    job_id = run.get("job_id")
    if job_id:
        try:
            from core.job_store import get_job_store
            get_job_store().record_event(
                job_id=job_id,
                event_type=event_type,
                event_data=data,
                session_id=session_id,
                run_id=run.get("run_id"),
            )
        except Exception:
            pass

    if event_type == "thinking":
        run["phase"] = "thinking"
    elif event_type in ("stream_start",):
        run["phase"] = "streaming"
    elif event_type in ("stream_delta", "response_chunk"):
        run["phase"] = "streaming"
        chunk = data.get("delta") or data.get("chunk") or data.get("text") or ""
        prev_len = len(run.get("accumulated_text", ""))
        run["accumulated_text"] = run.get("accumulated_text", "") + str(chunk)
        new_len = len(run["accumulated_text"])
        # Checkpoint streaming text every ~200 characters into jobs.db
        if job_id and (new_len // 200 > prev_len // 200):
            try:
                from core.job_store import get_job_store
                get_job_store().update_job_progress(
                    job_id=job_id,
                    progress=50.0,
                    stage="streaming",
                    checkpoint_data={"accumulated_text": run["accumulated_text"]},
                )
            except Exception:
                pass
    elif event_type == "tool_start":
        run["phase"] = "tool_execution"
        tools = run.setdefault("live_tools", [])
        tools.append({
            "tool": data.get("tool"),
            "arguments": data.get("arguments"),
            "status": "running",
            "tool_call_id": data.get("tool_call_id"),
        })
    elif event_type == "tool_finish":
        tools = run.get("live_tools", [])
        call_id = data.get("tool_call_id")
        tool_name = data.get("tool")
        for t in tools:
            if (call_id and t.get("tool_call_id") == call_id) or (t.get("tool") == tool_name and t.get("status") == "running"):
                t["status"] = "error" if data.get("error") else "success"
                t["output"] = data.get("result") or data.get("output")
                break
        if job_id:
            try:
                from core.job_store import get_job_store
                get_job_store().update_job_progress(
                    job_id=job_id,
                    progress=60.0,
                    stage="tool_execution",
                    checkpoint_data={"live_tools": tools},
                )
            except Exception:
                pass


async def _emit(session_id: str, run_id, event_type: str, data: dict | None = None) -> None:
    """Event protokol milik ws.py sendiri (bukan event domain Event Bus)."""
    payload_data = {**(data or {}), "session_id": session_id, "run_id": run_id}
    update_active_run_event(session_id, event_type, payload_data)
    await manager.send(session_id, {
        "type": event_type,
        "data": payload_data,
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
        run_info = _ACTIVE_RUNS.get(session_id)
        if run_info and run_info.get("job_id"):
            try:
                from core.job_store import get_job_store
                get_job_store().fail_job(run_info["job_id"], error_message=message)
            except Exception:
                pass
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
        cancelled = dio_submission.get("cancelled", False)
        status = "CANCELLED" if cancelled else "SUBMITTED"
        schema_id = dio_submission.get("schema_id")
        store.resolve_turn_interaction(session_id, schema_id=schema_id, status=status)
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

        # Opsional (Selection "Tanya AIRA"): klien boleh mengirim instruksi LLM
        # yang lebih kaya (kutipan + konteks sekitar) sementara bubble user
        # tetap menampilkan display_message yang ringkas. Tanpa field ini
        # perilaku SAMA seperti sebelumnya.
        selection_llm = raw.get("llm_message")
        if isinstance(selection_llm, str) and selection_llm.strip() and not is_voice_turn:
            llm_message = selection_llm.strip()[:8000]

    # --------------------------------------------------
    # PROSES: satu jalur reasoning (Brain.think()) untuk teks/suara/DIO.
    # Event realtime dipublish ke Event Bus dan sampai ke client lewat
    # WS bridge.
    # --------------------------------------------------
    brain = Brain(memory)
    use_stream = stream_enabled_for_turn(raw, is_voice_turn)

    await emit("ack", {"message": display_message})

    # Persist user prompt immediately to SQLite before execution begins
    # (Guarantees zero prompt loss across network drops, refreshes, or server errors)
    if replace_from is not None:
        store.truncate_turns_from(session_id, replace_from)

    user_turn_id = store.add_turn(session_id, "user", display_message)
    store.maybe_autotitle(session_id, display_message)

    run_info = _ACTIVE_RUNS.get(session_id)
    if run_info:
        run_info["user_turn_id"] = user_turn_id

    s_row = store.get_session_row(session_id)
    turn_user_id = s_row.get("user_id") if s_row else None

    def _run_think():
        from core.events import event_scope
        with event_scope(session_id=session_id, user_id=turn_user_id):
            return brain.think(llm_message, cancel_event, use_stream)

    try:
        result = await asyncio.to_thread(_run_think)
    except Exception as exc:
        logger.exception("WS think() gagal | session=%s", session_id)
        memory.history = backup_history
        try:
            store.add_turn(session_id, "assistant", f"[Gagal memproses giliran: {exc}]")
        except Exception:
            pass
        await fail(str(exc))  # fail() sudah flush bridge dulu
        return

    # Semua event tool/thinking yang sudah dipublish harus tiba di client
    # SEBELUM response/cancelled dikirim.
    await bridge.flush()

    # --------------------------------------------------
    # DIHENTIKAN USER: buang hasil, kembalikan memory, catat status di DB.
    # --------------------------------------------------
    if result.cancelled or cancel_event.is_set():
        memory.history = backup_history
        run_info = _ACTIVE_RUNS.get(session_id)
        if run_info and run_info.get("job_id"):
            try:
                from core.job_store import get_job_store
                get_job_store().cancel_job(run_info["job_id"], reason="Dibatalkan pengguna")
            except Exception:
                pass
        try:
            store.add_turn(session_id, "assistant", "[Dibatalkan pengguna]")
        except Exception:
            pass
        await emit("cancelled")
        return

    if not store.get_session_row(session_id):
        drop_cache(session_id)
        await emit("cancelled")
        return

    # --------------------------------------------------
    # SUKSES: baru sekarang memory & usage diperbarui, dan turn asisten disimpan.
    # --------------------------------------------------
    persist_memory(session_id, memory)
    add_global_usage(result.token_usage)

    # User turn was already saved before think(); now save assistant response
    assistant_turn_id = store.add_turn(
        session_id, "assistant", result.answer,
        steps=result.steps, interaction_schema=result.interaction_schema,
    )

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

    # VERA Adaptive Experience (VAE) Protocol v2 payload generation
    vae_payload_obj = brain_response_to_vae_payload(
        answer=result.answer,
        interaction_schema=result.interaction_schema,
        steps=result.steps,
        session_id=session_id,
        query=display_message,
    )

    run_info = _ACTIVE_RUNS.get(session_id)
    if run_info and run_info.get("job_id"):
        try:
            from core.job_store import get_job_store
            get_job_store().complete_job(
                run_info["job_id"],
                result_data={
                    "answer": result.answer,
                    "duration": result.duration,
                    "vae_payload": vae_payload_obj.to_dict() if vae_payload_obj else None,
                    "user_turn_id": user_turn_id,
                    "assistant_turn_id": assistant_turn_id,
                },
            )
        except Exception:
            pass

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
        "vae_payload": vae_payload_obj.to_dict(),
        "user_turn_id": user_turn_id,
        "assistant_turn_id": assistant_turn_id,
    })


async def _run_turn(session_id: str, raw: dict, cancel_event: threading.Event) -> None:
    run_id = raw.get("run_id") or uuid.uuid4().hex[:12]

    try:
        # Resolve user_id from session for strict user-isolated memory context
        user_id = None
        sess = store.get_session_row(session_id)
        if sess and sess.get("user_id"):
            user_id = sess.get("user_id")

        # Semua event yang dipublish selama giliran ini (termasuk dari thread
        # pekerja) otomatis tertandai sesi + run + correlation_id + user_id yang sama.
        with event_scope(
            correlation_id=new_correlation_id(),
            session_id=session_id,
            run_id=run_id,
            user_id=user_id,
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

@router.websocket("/nms")
async def nms_ws(websocket: WebSocket):
    token = websocket.query_params.get("token") or websocket.headers.get("authorization")
    if token and token.startswith("Bearer "):
        token = token.split(" ", 1)[1].strip()
    if token:
        try:
            from core.tenant.manager import IdentityManager
            ctx = IdentityManager().validate_session_token(token)
            if not ctx:
                await websocket.close(code=1008, reason="Sesi tidak valid.")
                return
        except Exception:
            pass

    await manager.connect("nms", websocket)
    get_ws_bridge().ensure_started(asyncio.get_running_loop())

    try:
        from core.nms_engine import get_nms_engine
        engine = get_nms_engine()
        # Kirim initial snapshot langsung saat connect
        await websocket.send_json({
            "type": "nms_snapshot",
            "data": {
                "overview": engine.get_overview(),
                "is_running": engine.is_running(),
                "timestamp": time.time(),
            },
            "ts": time.time(),
        })

        while True:
            raw = await websocket.receive_json()
            msg_type = raw.get("type", "ping")
            if msg_type == "ping":
                await websocket.send_json({"type": "pong", "ts": time.time()})
    except WebSocketDisconnect:
        await manager.disconnect("nms", websocket)
    except Exception:
        await manager.disconnect("nms", websocket)


@router.websocket("/models")
async def models_ws(websocket: WebSocket):
    token = websocket.query_params.get("token") or websocket.headers.get("authorization")
    if token and token.startswith("Bearer "):
        token = token.split(" ", 1)[1].strip()
    if token:
        try:
            from core.tenant.manager import IdentityManager
            ctx = IdentityManager().validate_session_token(token)
            if not ctx:
                await websocket.close(code=1008, reason="Sesi tidak valid.")
                return
        except Exception:
            pass

    await manager.connect("models", websocket)
    get_ws_bridge().ensure_started(asyncio.get_running_loop())

    try:
        from core.model_store import get_model_store
        from core.provider_health import get_provider_health_manager
        store = get_model_store()
        health_mgr = get_provider_health_manager()
        # Kirim snapshot awal model dan provider health saat koneksi terbuka
        await websocket.send_json({
            "type": "model_registry_snapshot",
            "data": {
                "models": store.list_models(),
                "routing": store.get_routing(),
                "policy": store.get_policy(),
                "provider_health": health_mgr.get_all_records(),
                "timestamp": time.time(),
            },
            "ts": time.time(),
        })

        while True:
            raw = await websocket.receive_json()
            msg_type = raw.get("type", "ping")
            if msg_type == "ping":
                await websocket.send_json({"type": "pong", "ts": time.time()})
    except WebSocketDisconnect:
        await manager.disconnect("models", websocket)
    except Exception:
        await manager.disconnect("models", websocket)


@router.websocket("/chat/{session_id}")
async def chat_ws(websocket: WebSocket, session_id: str):
    token = websocket.query_params.get("token") or websocket.headers.get("authorization")
    if token and token.startswith("Bearer "):
        token = token.split(" ", 1)[1].strip()
    user_id_scope = None
    if token:
        try:
            from core.tenant.manager import IdentityManager
            ctx = IdentityManager().validate_session_token(token)
            if not ctx:
                await websocket.close(code=1008, reason="Sesi kedaluwarsa atau tidak valid.")
                return
            user_id_scope = ctx.user_id
        except Exception:
            pass

    await manager.connect(session_id, websocket)

    # Idempotent: pastikan bridge Event Bus -> WebSocket aktif di loop ini
    # (normalnya sudah di-start di startup api/main.py).
    get_ws_bridge().ensure_started(asyncio.get_running_loop())

    # State Restoration on Reconnect: check for ongoing background task in this session
    active_run = _ACTIVE_RUNS.get(session_id)
    if active_run and not active_run["task"].done():
        try:
            await websocket.send_json({
                "type": "active_run_resumed",
                "data": {
                    "session_id": session_id,
                    "run_id": active_run.get("run_id"),
                    "job_id": active_run.get("job_id"),
                    "phase": active_run.get("phase", "thinking"),
                    "accumulated_text": active_run.get("accumulated_text", ""),
                    "live_tools": active_run.get("live_tools", []),
                    "created_at": active_run.get("created_at"),
                    "ts": time.time(),
                },
                "ts": time.time(),
            })
        except Exception as exc:
            logger.warning("Failed to emit active_run_resumed on WS connect for session %s: %s", session_id, exc)

    try:
        while True:
            raw = await websocket.receive_json()
            msg_type = raw.get("type", "text")

            # ---- PING / HEARTBEAT ----
            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            # ---- REPLAY REQUEST ----
            if msg_type == "request_replay":
                run = _ACTIVE_RUNS.get(session_id)
                job_id = raw.get("job_id") or (run.get("job_id") if run else None)
                if job_id:
                    try:
                        from core.job_store import get_job_store
                        since_id = int(raw.get("since_id") or 0)
                        events = get_job_store().get_events_for_job(job_id, since_id=since_id)
                        await websocket.send_json({
                            "type": "replay_events",
                            "data": {
                                "session_id": session_id,
                                "job_id": job_id,
                                "events": [e.to_dict() for e in events],
                            },
                            "ts": time.time(),
                        })
                    except Exception as exc:
                        logger.warning("Error replaying events for job %s: %s", job_id, exc)
                continue

            # ---- STOP ----
            if msg_type == "cancel":
                run = _ACTIVE_RUNS.get(session_id)
                if run:
                    run["cancel"].set()
                continue

            # ---- PAUSE TASK ----
            if msg_type == "pause":
                run = _ACTIVE_RUNS.get(session_id)
                job_id = raw.get("job_id") or (run.get("job_id") if run else None)
                if job_id:
                    try:
                        from core.job_store import get_job_store
                        checkpoint = {
                            "accumulated_text": run.get("accumulated_text", "") if run else "",
                            "live_tools": run.get("live_tools", []) if run else [],
                            "phase": run.get("phase", "running") if run else "running",
                        }
                        get_job_store().pause_job(job_id, checkpoint_data=checkpoint)
                        if run:
                            run["phase"] = "paused"
                            run["is_paused"] = True
                        await websocket.send_json({
                            "type": "job_paused",
                            "data": {
                                "session_id": session_id,
                                "job_id": job_id,
                                "checkpoint": checkpoint,
                            },
                            "ts": time.time(),
                        })
                    except Exception as exc:
                        logger.warning("Error pausing job %s: %s", job_id, exc)
                continue

            # ---- RESUME TASK ----
            if msg_type == "resume":
                run = _ACTIVE_RUNS.get(session_id)
                instruction = raw.get("instruction") or raw.get("message")
                job_id = raw.get("job_id") or (run.get("job_id") if run else None)
                if job_id:
                    try:
                        from core.job_store import get_job_store
                        get_job_store().resume_job(job_id, additional_instructions=instruction)
                        if run:
                            run["phase"] = "running"
                            run["is_paused"] = False
                        await websocket.send_json({
                            "type": "job_resumed",
                            "data": {
                                "session_id": session_id,
                                "job_id": job_id,
                                "instruction": instruction,
                            },
                            "ts": time.time(),
                        })
                    except Exception as exc:
                        logger.warning("Error resuming job %s: %s", job_id, exc)
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
            run_id = raw.get("run_id") or uuid.uuid4().hex[:12]
            raw["run_id"] = run_id

            # Initialize durable job for this execution
            job_id = None
            try:
                from core.job_store import get_job_store
                user_id_turn = None
                s_row = store.get_session_row(session_id)
                if s_row and s_row.get("user_id"):
                    user_id_turn = s_row.get("user_id")

                job = get_job_store().create_job(
                    job_type="chat_turn",
                    title=(raw.get("message") or "Permintaan Chat")[:60],
                    session_id=session_id,
                    run_id=run_id,
                    user_id=user_id_turn,
                    stage="thinking",
                )
                job_id = job.job_id
            except Exception as exc:
                logger.warning("Could not initialize durable job for session %s: %s", session_id, exc)

            task = asyncio.create_task(_run_turn(session_id, raw, cancel_event))
            _ACTIVE_RUNS[session_id] = {
                "task": task,
                "cancel": cancel_event,
                "run_id": run_id,
                "job_id": job_id,
                "phase": "thinking",
                "accumulated_text": "",
                "live_tools": [],
                "created_at": time.time(),
            }
            task.add_done_callback(lambda t, sid=session_id: _cleanup_run(sid, t))

    except WebSocketDisconnect:
        # Task yang sedang berjalan SENGAJA tidak dibatalkan: hasilnya tetap
        # disimpan ke database dan dikirim ke socket baru bila ada.
        await manager.disconnect(session_id, websocket)
    except Exception:
        logger.exception("WS loop error tak terduga | session=%s", session_id)
        await manager.disconnect(session_id, websocket)