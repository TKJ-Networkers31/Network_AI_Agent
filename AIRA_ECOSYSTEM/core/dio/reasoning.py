"""
core/dio/reasoning.py — Mode Selection Rule (Phase 2.2).

Fungsi murni (pure function) — TIDAK menyentuh I/O, SQLite, atau Event
Bus, hanya membaca InteractionPlan dan mengembalikan salah satu dari
SUPPORTED_MODES. Ini SATU-SATUNYA tempat yang boleh memutuskan mode
interaksi; analyzer.py dan builder.py memanggil select_mode() alih-alih
menyimpulkan mode sendiri-sendiri.

PRIORITAS EVALUASI (dari yang paling menang):
  1. danger=True                      -> approval (keselamatan menang)
  2. needs_review=True                -> review
  3. context menandai proses bertahap -> wizard
  4. tidak ada missing_data & tidak ada choices -> display
  5. choice + input manual bercampur  -> mixed
  6. hanya field bertipe choice       -> choice
  7. tepat satu field kurang (bukan choice) -> text
  8. lebih dari dua field kurang      -> form
  9. default (biasanya persis 2 field kurang) -> form

Urutan ini SENGAJA tidak identik 1:1 dengan urutan penyebutan aturan di
spesifikasi Phase 2.2 (yang menyebut 'text' sebelum 'choice'): kalau
field yang kurang persis satu TAPI field itu bertipe choice (punya
'options'), menampilkannya sebagai 'text' polos akan kehilangan
pilihannya — 'choice' lebih tepat secara UX. Sinyal
keselamatan/proses (danger/needs_review/wizard) dievaluasi lebih dulu
karena sifatnya independen dari kelengkapan data.
"""

from core.dio.constants import (
    MODE_DISPLAY, MODE_TEXT, MODE_CHOICE, MODE_MIXED,
    MODE_FORM, MODE_WIZARD, MODE_APPROVAL, MODE_REVIEW,
)


def select_mode(plan) -> str:
    if plan.danger:
        return MODE_APPROVAL

    if plan.needs_review:
        return MODE_REVIEW

    if plan.context.get("wizard") or plan.context.get("is_multi_step"):
        return MODE_WIZARD

    missing = plan.missing_data
    missing_count = len(missing)

    has_top_level_choices = bool(plan.choices)
    missing_with_options = [m for m in missing if getattr(m, "options", None)]
    missing_manual = [m for m in missing if not getattr(m, "options", None)]

    has_choice_signal = has_top_level_choices or bool(missing_with_options)
    has_manual_signal = bool(missing_manual)

    if missing_count == 0 and not has_top_level_choices:
        return MODE_DISPLAY

    if has_choice_signal and has_manual_signal:
        return MODE_MIXED

    if has_choice_signal and not has_manual_signal:
        return MODE_CHOICE

    if missing_count == 1:
        return MODE_TEXT

    if missing_count > 2:
        return MODE_FORM

    return MODE_FORM