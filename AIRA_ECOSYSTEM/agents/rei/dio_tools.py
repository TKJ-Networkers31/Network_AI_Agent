"""
agents/rei/dio_tools.py — wrapper tipis REI di atas Dynamic Interaction
Orchestrator (core/dio/*), Phase 2.0 -> Integrasi Phase 2.6.

KENAPA FILE INI ADA (root cause "AIRA tidak pernah tanya balik"):
core/dio/* (DIOAnalyzer/SchemaBuilder/SchemaValidator/InteractionMemory)
sudah lengkap sejak Phase 2.0, tapi TIDAK PERNAH terdaftar sebagai tool
REI - satu-satunya sumber kemampuan yang dikirim ke LLM adalah
AGENT_TOOL_SCHEMAS di core/orchestrator.py, yang cuma menggabungkan
AKANE_TOOLS + HIKARI_TOOLS + REI_TOOLS. DIO tidak masuk salah satu dari
tiga itu -> LLM (benar secara teknis) tidak pernah tahu DIO ada, dan
selalu menjawab dari tebakan/pengetahuan umum walau informasi user
kurang.

Fix: daftarkan DIO sebagai tool REI (lihat agents/rei/registry.py) +
instruksi eksplisit di persona (core/persona/prompt_builder.py) supaya
LLM WAJIB memanggil tool ini ketika informasi kurang, DAERIPADA
mengarang jawaban. TIDAK ADA perubahan pada core/dio/* sama sekali.

Tool ini murni menerjemahkan argumen sederhana dari LLM (intent,
missing_fields, choices, danger, needs_review) menjadi InteractionPlan
lalu memanggil DIO.generate_schema() - tidak ada reasoning tambahan di
sini, semua reasoning tetap di core/dio/reasoning.py.
"""

from typing import Optional

from core.dio import get_dio
from core.dio.models import InteractionPlan, MissingField, ChoiceOption
from core.dio.reasoning import select_mode


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
    yang dikirim balik ke frontend untuk dirender sebagai form/pilihan
    interaktif (Companion Renderer, Sprint 03.5) - BUKAN teks biasa.

    Setelah tool ini dipanggil, LLM WAJIB berhenti menjawab dengan teks
    panjang di giliran itu - biarkan schema yang ditampilkan ke user,
    lalu tunggu balasan user di giliran berikutnya.
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