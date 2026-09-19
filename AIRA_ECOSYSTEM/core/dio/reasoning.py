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