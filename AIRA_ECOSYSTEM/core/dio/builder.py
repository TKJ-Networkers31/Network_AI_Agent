"""
core/dio/builder.py — SchemaBuilder, Phase 2.3 (Schema Builder).

Mengubah InteractionPlan (reasoning murni) jadi Universal Interaction
Schema (serializable dict-able), TANPA tahu apa pun soal domain
(Router/Docker/OCR/dst) — hanya membaca field generik
plan.missing_data / plan.known_data / plan.choices, sesuai prinsip
"DIO tidak mengetahui domain" (Phase 2.0).
"""

from typing import Any, Optional

from core.dio.models import (
    InteractionPlan, InteractionSchema, Section, Field, Action,
    MissingField, _new_id,
)
from core.dio.reasoning import select_mode
from core.dio.constants import (
    MODE_DISPLAY, MODE_TEXT, MODE_CHOICE, MODE_MIXED,
    MODE_FORM, MODE_WIZARD, MODE_APPROVAL, MODE_REVIEW,
    COMPONENT_SELECT, COMPONENT_RADIO, COMPONENT_INFO, COMPONENT_TEXT,
    DATA_TYPE_TO_COMPONENT,
)


class SchemaBuilder:

    def build_schema(
        self,
        plan: InteractionPlan,
        title: Optional[str] = None,
        description: Optional[str] = None,
    ) -> InteractionSchema:
        mode = plan.suggested_mode or select_mode(plan)

        builders = {
            MODE_DISPLAY: self._build_display,
            MODE_TEXT: self._build_text,
            MODE_CHOICE: self._build_choice,
            MODE_MIXED: self._build_mixed,
            MODE_FORM: self._build_form,
            MODE_WIZARD: self._build_form,  # satu langkah wizard = bentuk form biasa
            MODE_APPROVAL: self._build_approval,
            MODE_REVIEW: self._build_review,
        }

        build_fn = builders.get(mode, self._build_form)
        sections, actions = build_fn(plan)

        return InteractionSchema(
            id=_new_id("schema"),
            mode=mode,
            title=title or self._default_title(plan),
            description=description,
            sections=sections,
            actions=actions,
            metadata={
                "plan_id": plan.plan_id,
                "intent": plan.intent,
                "confidence": plan.confidence,
                "priority": plan.priority,
            },
        )

    # ---------------- per-mode builders ----------------

    def _build_display(self, plan: InteractionPlan):
        fields = [self._known_data_field(k, v) for k, v in plan.known_data.items()]
        if not fields:
            fields = [Field(id="info", type=COMPONENT_INFO, variant="info",
                             text="Tidak ada informasi untuk ditampilkan.")]
        return [Section(id="display", fields=fields)], [
            Action(id="close", label="Tutup", style="secondary"),
        ]

    def _build_text(self, plan: InteractionPlan):
        if not plan.missing_data:
            return self._build_display(plan)

        missing = plan.missing_data[0]
        section = Section(id="input", fields=[self._field_from_missing(missing)])
        actions = [
            Action(id="cancel", label="Batal", style="ghost"),
            Action(id="submit", label="Kirim", style="primary"),
        ]
        return [section], actions

    def _build_choice(self, plan: InteractionPlan):
        fields = []
        if plan.choices:
            fields.append(Field(
                id="choice",
                type=COMPONENT_RADIO if len(plan.choices) <= 4 else COMPONENT_SELECT,
                label=self._humanize(plan.intent), required=True,
                options=list(plan.choices),
            ))
        for missing in plan.missing_data:
            if missing.options:
                fields.append(self._field_from_missing(missing))

        if not fields:
            fields = [Field(id="info", type=COMPONENT_INFO, variant="info",
                             text="Tidak ada pilihan yang tersedia.")]

        section = Section(id="choice", fields=fields)
        actions = [
            Action(id="cancel", label="Batal", style="ghost"),
            Action(id="submit", label="Pilih", style="primary"),
        ]
        return [section], actions

    def _build_mixed(self, plan: InteractionPlan):
        fields = []
        if plan.choices:
            fields.append(Field(
                id="choice", type=COMPONENT_SELECT, label=self._humanize(plan.intent),
                required=True, options=list(plan.choices),
            ))
        for missing in plan.missing_data:
            fields.append(self._field_from_missing(missing))

        if not fields:
            fields = [Field(id="info", type=COMPONENT_INFO, variant="info",
                             text="Tidak ada input yang diperlukan.")]

        section = Section(id="mixed", fields=fields)
        actions = [
            Action(id="cancel", label="Batal", style="ghost"),
            Action(id="submit", label="Lanjut", style="primary"),
        ]
        return [section], actions

    def _build_form(self, plan: InteractionPlan):
        fields = [self._field_from_missing(m) for m in plan.missing_data]
        if not fields:
            fields = [Field(id="info", type=COMPONENT_INFO, variant="info",
                             text="Tidak ada input yang diperlukan.")]

        section = Section(id="form", fields=fields, columns=2 if len(fields) > 2 else 1)
        actions = [
            Action(id="cancel", label="Batal", style="ghost"),
            Action(id="submit", label="Simpan", style="primary"),
        ]
        return [section], actions

    def _build_approval(self, plan: InteractionPlan):
        warning_text = plan.context.get("warning_text") or (
            f"Tindakan '{self._humanize(plan.intent)}' berpotensi berisiko. "
            f"Pastikan kamu benar-benar ingin melanjutkan."
        )
        info_field = Field(id="warning", type=COMPONENT_INFO, variant="warning", text=warning_text)
        extra_fields = [self._field_from_missing(m) for m in plan.missing_data]

        section = Section(id="approval", fields=[info_field, *extra_fields])
        actions = [
            Action(id="cancel", label="Batal", style="ghost"),
            Action(id="confirm", label="Ya, Lanjutkan", style="danger"),
        ]
        return [section], actions

    def _build_review(self, plan: InteractionPlan):
        fields = [self._known_data_field(k, v) for k, v in plan.known_data.items()]
        fields += [self._field_from_missing(m) for m in plan.missing_data]

        if not fields:
            fields = [Field(id="info", type=COMPONENT_INFO, variant="info",
                             text="Tidak ada data untuk direview.")]

        section = Section(id="review", fields=fields)
        actions = [
            Action(id="reject", label="Tolak", style="ghost"),
            Action(id="approve", label="Setujui", style="primary"),
        ]
        return [section], actions

    # ---------------- helpers ----------------

    @staticmethod
    def _humanize(text: str) -> str:
        return (text or "").replace("_", " ").strip().capitalize() or "Interaksi"

    @staticmethod
    def _default_title(plan: InteractionPlan) -> str:
        return SchemaBuilder._humanize(plan.intent)

    @staticmethod
    def _known_data_field(key: str, value: Any) -> Field:
        return Field(id=f"known_{key}", type=COMPONENT_INFO, label=key, text=str(value), variant="info")

    @staticmethod
    def _field_from_missing(missing: MissingField) -> Field:
        component = DATA_TYPE_TO_COMPONENT.get(missing.data_type, COMPONENT_TEXT)
        if missing.options:
            component = COMPONENT_SELECT if len(missing.options) > 4 else COMPONENT_RADIO

        return Field(
            id=missing.key,
            type=component,
            label=missing.label or SchemaBuilder._humanize(missing.key),
            required=missing.required,
            default=missing.default,
            placeholder=missing.placeholder,
            helper_text=missing.helper_text,
            options=list(missing.options),
            min=missing.min,
            max=missing.max,
            pattern=missing.pattern,
        )