"""
agents/rei/dio_tools.py — wrapper tipis REI di atas Dynamic Interaction
Orchestrator (core/dio/*), Phase 2.0 -> Integrasi Phase 2.6 -> Sprint
Optimalisasi DIO (submit round-trip).

request_structured_input() TIDAK BERUBAH dari sebelumnya - itu yang
dipanggil LLM untuk MEMBUAT schema.

FIX (Optimalisasi DIO - jalur submit yang sebelumnya tidak ada sama
sekali):
1. submit_structured_input() - dipanggil dari api/routers/chat.py dan
   api/routers/ws.py (BUKAN oleh LLM) begitu user menekan aksi pada form
   interaktif di frontend. Efeknya:
     a. Menulis setiap field yang diisi user ke InteractionMemory
        (core/dio/interaction_memory.py) - inilah yang membuat
        DIOAnalyzer.analyze() di sesi/permintaan berikutnya bisa
        menutup 'missing_data' otomatis TANPA bertanya ulang. Sebelum
        fix ini, InteractionMemory hanya pernah DIBACA, tidak pernah
        DITULIS dari hasil interaksi nyata.
     b. Mempublish event lifecycle "interaction.completed" /
        "interaction.cancelled" ke core/events.py::event_bus, sesuai
        siklus hidup yang sudah didesain DIO.schema.py::DIO.complete()/
        cancel() (kita publish event-nya langsung di sini, bukan lewat
        DIO.complete()/cancel(), karena objek InteractionSchema/Plan asli
        sudah tidak ada lagi di memori setelah giliran tool call selesai
        - publish langsung tetap sah karena event_bus.publish() menerima
        data dict apa pun).
2. build_submission_message() - membangun pasangan (display_message,
   llm_message) dari payload submission, dipakai chat.py & ws.py supaya
   tidak duplikasi logic di dua tempat (sebelumnya pola serupa - lihat
   _apply_slash_command - memang diduplikasi di chat.py & ws.py; kali
   ini sengaja disatukan di sini).
"""

import json
from typing import Optional

from core.dio import get_dio
from core.dio.models import InteractionPlan, MissingField, ChoiceOption
from core.dio.reasoning import select_mode
from core.dio.interaction_memory import get_interaction_memory
from core.events import event_bus


def _to_missing_field(raw: dict) -> MissingField:
    options = [
        ChoiceOption(value=o["value"], label=o.get("label", o["value"]))
        for o in raw.get("options", [])
    ]
    return MissingField(
        key=raw["key"],
        data_type=raw.get("data_type", "string"),
        label=raw.get("label"),
        required=raw.get("required", True),
        options=options,
        placeholder=raw.get("placeholder"),
        helper_text=raw.get("helper_text"),
        default=raw.get("default"),
        min=raw.get("min"),
        max=raw.get("max"),
    )


def _to_choice(raw: dict) -> ChoiceOption:
    return ChoiceOption(value=raw["value"], label=raw.get("label", raw["value"]))


def request_structured_input(
    intent: str,
    missing_fields: Optional[list] = None,
    choices: Optional[list] = None,
    danger: bool = False,
    needs_review: bool = False,
    title: Optional[str] = None,
    description: Optional[str] = None,
) -> dict:
    """
    Dipanggil oleh LLM (lewat agents/rei/planner.py) kapan pun informasi
    dari user KURANG atau AMBIGU untuk menjalankan suatu permintaan.
    Mengembalikan Universal Interaction Schema (dict, sudah divalidasi)
    yang sekarang benar-benar dirender ke frontend sebagai form/pilihan
    interaktif (lihat agents/rei/planner.py + MessageBubble.jsx) - BUKAN
    hanya teks JSON yang terkubur di tool result seperti sebelumnya.

    Setelah tool ini dipanggil, LLM WAJIB berhenti menjawab dengan teks
    panjang di giliran itu - biarkan schema yang ditampilkan ke user,
    lalu tunggu balasan user di giliran berikutnya (masuk lewat
    submit_structured_input() di bawah).
    """

    plan = InteractionPlan(
        intent=intent,
        missing_data=[_to_missing_field(m) for m in (missing_fields or [])],
        choices=[_to_choice(c) for c in (choices or [])],
        danger=danger,
        needs_review=needs_review,
    )
    plan.suggested_mode = select_mode(plan)

    schema = get_dio().generate_schema(plan, title=title, description=description)

    return {
        "success": True,
        "tool": "request_structured_input",
        "interaction_schema": schema.to_dict(),
    }


def submit_structured_input(
    schema_id: str,
    action_id: str,
    values: Optional[dict] = None,
    cancelled: bool = False,
) -> dict:
    """
    Dipanggil LANGSUNG oleh api/routers/chat.py dan api/routers/ws.py
    (bukan tool LLM) begitu user menekan aksi pada form/pilihan
    interaktif yang dirender frontend dari hasil request_structured_input().

    - Kalau TIDAK dibatalkan: setiap field yang diisi disimpan ke
      InteractionMemory supaya DIOAnalyzer bisa menutup gap yang sama di
      permintaan berikutnya tanpa bertanya ulang.
    - Selalu mempublish event lifecycle DIO ke event_bus, apa pun
      hasilnya (completed/cancelled), supaya subscriber lain (mis. Logs,
      atau relay WebSocket di masa depan) bisa mengamati siklus hidup
      interaksi ini.
    """
    values = values or {}
    saved_keys: list[str] = []

    if not cancelled:
        memory = get_interaction_memory()

        for key, value in values.items():
            if value is None or value == "":
                continue
            memory.save(key, value)
            saved_keys.append(key)

    event_name = "interaction.cancelled" if cancelled else "interaction.completed"

    try:
        event_bus.publish(
            event_name, agent="DIO",
            data={"schema_id": schema_id, "action_id": action_id, "values": values},
        )
    except Exception:
        # Publish event tidak boleh pernah menggagalkan submit - efek
        # penyimpanan ke InteractionMemory di atas sudah cukup penting
        # untuk tetap berhasil walau event bus bermasalah.
        pass

    return {
        "success": True,
        "schema_id": schema_id,
        "cancelled": cancelled,
        "saved_keys": saved_keys,
    }


def build_submission_message(dio_submission: dict) -> "tuple[str, str]":
    """
    Return (display_message, llm_message):
    - display_message: teks singkat yang disimpan/ditampilkan sebagai
      bubble chat milik user (bukan JSON mentah - biar enak dibaca).
    - llm_message: instruksi terstruktur yang benar-benar dikirim ke
      LLM, berisi data lengkap yang tadi diisi user di form.
    """
    action_id = dio_submission.get("action_id", "")
    values = dio_submission.get("values") or {}
    cancelled = bool(dio_submission.get("cancelled"))

    if cancelled:
        display_message = "❌ Dibatalkan."
        llm_message = (
            "[Instruksi sistem: User membatalkan form/pilihan interaktif "
            f"sebelumnya (action_id='{action_id}'). Jangan lanjutkan aksi "
            "yang sedang direncanakan - tanyakan apakah ada hal lain yang "
            "bisa dibantu.]"
        )
        return display_message, llm_message

    pretty_values = ", ".join(f"{k}={v}" for k, v in values.items()) or "(tidak ada input)"
    display_message = f"📝 Form terkirim: {pretty_values}"

    llm_message = (
        "[Instruksi sistem: User baru saja mengisi form/pilihan interaktif "
        f"(action_id='{action_id}') dengan data berikut: "
        f"{json.dumps(values, ensure_ascii=False)}. Lanjutkan permintaan "
        "sebelumnya menggunakan data ini - JANGAN minta user mengulang "
        "input yang sudah diberikan di sini, dan JANGAN memanggil "
        "request_structured_input lagi untuk field yang sudah terisi.]"
    )

    return display_message, llm_message