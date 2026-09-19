"""
agents/rei/dio_tools.py — wrapper tipis REI di atas Dynamic Interaction
Orchestrator (core/dio/*).

Tool untuk LLM:
  - request_structured_input(): form/pilihan interaktif umum.
  - request_location_permission(): izin GPS browser + menyimpan permintaan
    asli user supaya dilanjutkan otomatis setelah izin diberikan.

Alur submission (dipakai chat.py DAN ws.py lewat satu helper):
  resolve_submission(dio_submission) -> (display_message, llm_message)

KEAMANAN:
  - Key yang mengandung pass/secret/token/community/api_key TIDAK PERNAH
    disimpan ke interaction_memory dan dimasker di display_message.
  - Event interaction.completed/cancelled hanya membawa NAMA field (keys),
    bukan nilainya (password/koordinat tidak boleh masuk log/event).
  - Key interaction_memory diberi namespace "<schema_id>:<key>".

session_id untuk request_location_permission diisi otomatis oleh
agents/rei/planner.py - LLM tidak diminta menyebutkannya.
"""

import json
import re
import time
from typing import Optional

from core.dio import get_dio
from core.dio.models import InteractionPlan, MissingField, ChoiceOption
from core.dio.reasoning import select_mode
from core.dio.constants import MODE_LOCATION_PERMISSION, EVENT_INTERACTION_REQUESTED
from core.dio.interaction_memory import get_interaction_memory
from core.events import event_bus
from core.location import location_service
from core.location.models import LocationContext, ROLE_ACCESS, SOURCE_BROWSER

LOCATION_PENDING_KEY_PREFIX = "pending_location_request:"
LOCATION_PENDING_TTL_SECONDS = 600  # 10 menit - cukup untuk merespons dialog izin browser

SENSITIVE_KEY_RE = re.compile(r"pass|secret|token|community|api.?key", re.IGNORECASE)


def _is_sensitive(key) -> bool:
    return bool(SENSITIVE_KEY_RE.search(str(key)))


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


# ============================================================ TOOL: form umum

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
    Dipanggil LLM kapan pun informasi dari user KURANG atau AMBIGU.
    Untuk kebutuhan LOKASI PRESISI, pakai request_location_permission.

    Kalau schema hasil build tidak lolos validator (mis. select tanpa
    options), tool mengembalikan success=False beserta daftar issue supaya
    LLM bisa memperbaiki panggilannya - bukan menampilkan form rusak.
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

    validation = (schema.metadata or {}).get("validation") or {}

    if not validation.get("is_valid", False):
        return {
            "success": False,
            "tool": "request_structured_input",
            "error": "Schema interaksi tidak valid. Perbaiki argumen lalu panggil ulang.",
            "issues": validation.get("issues", []),
        }

    return {
        "success": True,
        "tool": "request_structured_input",
        "interaction_schema": schema.to_dict(),
    }


# ======================================================= TOOL: izin lokasi

def request_location_permission(
    original_request: str,
    reason: Optional[str] = None,
    session_id: Optional[str] = None,
) -> dict:
    """
    Dipanggil LLM saat permintaan user butuh lokasi presisi SEKARANG dan
    lokasi akses sesi belum bersumber dari GPS browser.

    `session_id` diisi otomatis oleh planner - JANGAN diminta dari LLM.
    """

    plan = InteractionPlan(
        intent="location_permission",
        context={"reason": reason or ""},
    )
    plan.suggested_mode = MODE_LOCATION_PERMISSION

    schema = get_dio().generate_schema(
        plan,
        title="Izin Akses Lokasi",
        description=reason or "AIRA butuh tahu lokasimu sekarang untuk menjawab ini.",
    )

    request_id = schema.id

    pending = {
        "request_id": request_id,
        "session_id": session_id,
        "original_request": original_request,
        "created_at": time.time(),
    }

    get_interaction_memory().save(
        f"{LOCATION_PENDING_KEY_PREFIX}{request_id}",
        pending,
        ttl_seconds=LOCATION_PENDING_TTL_SECONDS,
    )

    try:
        event_bus.publish(
            EVENT_INTERACTION_REQUESTED, agent="DIO",
            data={
                "schema_id": request_id,
                "intent": "location_permission",
                "session_id": session_id,
            },
        )
    except Exception:
        pass  # publish event tidak boleh menggagalkan pembuatan form izin

    return {
        "success": True,
        "tool": "request_location_permission",
        "interaction_schema": schema.to_dict(),
    }


def _handle_location_grant(pending: dict, values: dict) -> dict:
    """
    Validasi koordinat lalu simpan sebagai lokasi akses sesi lewat
    LocationService. Return {"granted": bool, ...} - TIDAK PERNAH raise.
    """

    try:
        latitude = float(values.get("latitude"))
        longitude = float(values.get("longitude"))
    except (TypeError, ValueError):
        return {"granted": False, "reason": "invalid_coordinates"}

    if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
        return {"granted": False, "reason": "invalid_coordinates"}

    accuracy = values.get("accuracy")
    try:
        accuracy = float(accuracy) if accuracy is not None else None
    except (TypeError, ValueError):
        accuracy = None

    session_id = pending.get("session_id")

    if not session_id:
        return {"granted": False, "reason": "missing_session"}

    context = LocationContext(
        role=ROLE_ACCESS,
        latitude=latitude,
        longitude=longitude,
        accuracy=accuracy,
        source=SOURCE_BROWSER,
        timestamp=time.time(),
    )

    location_service.update_access(session_id, context)

    return {"granted": True, "latitude": latitude, "longitude": longitude, "accuracy": accuracy}


# ===================================================== SUBMISSION HANDLING

def submit_structured_input(
    schema_id: str,
    action_id: str,
    values: Optional[dict] = None,
    cancelled: bool = False,
) -> dict:
    """
    Menjalankan efek samping submission. SINKRON dan bisa melakukan HTTP
    (reverse_geocode, timeout hingga 4 detik) - dari kode async WAJIB lewat
    asyncio.to_thread (resolve_submission() dipakai untuk itu).
    """
    values = values or {}
    saved_keys: list[str] = []

    memory = get_interaction_memory()
    pending_key = f"{LOCATION_PENDING_KEY_PREFIX}{schema_id}"
    pending = memory.load(pending_key)

    location_result = None

    if pending:
        if action_id == "grant_location" and not cancelled:
            location_result = _handle_location_grant(pending, values)
        else:
            # deny_location, atau cancelled=True dari jalur mana pun.
            location_result = {"granted": False, "reason": "denied"}

        # Pending request selalu sekali pakai.
        memory.clear(pending_key)

    elif not cancelled:
        for key, value in values.items():
            if value is None or value == "":
                continue
            if _is_sensitive(key):
                continue  # password/secret/token tidak pernah disimpan
            memory.save(f"{schema_id}:{key}", value)  # namespace per schema
            saved_keys.append(key)

    event_name = "interaction.cancelled" if cancelled else "interaction.completed"

    try:
        event_bus.publish(
            event_name, agent="DIO",
            # HANYA nama field, bukan nilainya.
            data={"schema_id": schema_id, "action_id": action_id, "keys": list(values.keys())},
        )
    except Exception:
        pass

    return {
        "success": True,
        "schema_id": schema_id,
        "cancelled": cancelled,
        "saved_keys": saved_keys,
        "pending_location": pending,
        "location_result": location_result,
    }


def build_submission_message(
    dio_submission: dict,
    pending_location: Optional[dict] = None,
    location_result: Optional[dict] = None,
) -> "tuple[str, str]":
    """
    Return (display_message, llm_message).

    display_message disimpan ke chat_turns dan tampil di UI, jadi nilai
    sensitif dimasker di sini. llm_message tetap membawa nilai asli
    karena LLM membutuhkannya untuk melanjutkan permintaan.
    """
    action_id = dio_submission.get("action_id", "")
    values = dio_submission.get("values") or {}
    cancelled = bool(dio_submission.get("cancelled"))

    if pending_location:
        original_request = pending_location.get("original_request") or ""
        granted = bool(location_result and location_result.get("granted"))

        if granted:
            accuracy_note = (
                f", akurasi±{location_result['accuracy']:.0f}m"
                if location_result.get("accuracy") is not None else ""
            )
            display_message = "📍 Lokasi diberikan."
            llm_message = (
                "[Instruksi sistem: User baru saja mengizinkan akses lokasi GPS "
                f"browser (lat={location_result['latitude']}, lon={location_result['longitude']}"
                f"{accuracy_note}). Lokasi ini SUDAH tersimpan sebagai lokasi akses sesi "
                "ini - pakai langsung, JANGAN memanggil request_location_permission lagi "
                f"di giliran ini. Lanjutkan permintaan asli user berikut: \"{original_request}\"]"
            )
        else:
            reason = (location_result or {}).get("reason", "denied")
            display_message = "🚫 Izin lokasi ditolak." if reason == "denied" else "⚠ Lokasi tidak valid."
            llm_message = (
                "[Instruksi sistem: User TIDAK memberikan lokasi GPS yang valid "
                f"(alasan: {reason}). JANGAN memanggil request_location_permission lagi "
                "di giliran ini. Jawab permintaan asli user berikut TANPA data lokasi "
                f"presisi, atau jelaskan kenapa lokasi dibutuhkan: \"{original_request}\"]"
            )

        return display_message, llm_message

    if cancelled:
        display_message = "❌ Dibatalkan."
        llm_message = (
            "[Instruksi sistem: User membatalkan form/pilihan interaktif "
            f"sebelumnya (action_id='{action_id}'). Jangan lanjutkan aksi "
            "yang sedang direncanakan - tanyakan apakah ada hal lain yang "
            "bisa dibantu.]"
        )
        return display_message, llm_message

    pretty_values = ", ".join(
        f"{k}={'***' if _is_sensitive(k) else v}" for k, v in values.items()
    ) or "(tidak ada input)"
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


def resolve_submission(dio_submission: dict) -> "tuple[str, str]":
    """
    SATU-SATUNYA jalur memproses submission form/izin: efek samping +
    penyusunan pesan. Dipakai chat.py (langsung) dan ws.py (lewat
    asyncio.to_thread). Dengan begitu REST dan WebSocket tidak bisa
    berbeda perilaku lagi.

    Return (display_message, llm_message).
    """
    result = submit_structured_input(
        schema_id=dio_submission.get("schema_id", ""),
        action_id=dio_submission.get("action_id", ""),
        values=dio_submission.get("values"),
        cancelled=bool(dio_submission.get("cancelled")),
    )

    return build_submission_message(
        dio_submission,
        pending_location=result.get("pending_location"),
        location_result=result.get("location_result"),
    )