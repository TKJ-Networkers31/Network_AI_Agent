"""
core/dio/analyzer.py — DIOAnalyzer, Phase 2.1 (Intent Analyzer).

Analyzer TIDAK memanggil LLM apa pun (itu tetap wewenang
agents/rei/provider_client.py) dan TIDAK menghasilkan UI apa pun — ia
murni menyusun ulang keluaran reasoning planner (planner_output) jadi
InteractionPlan yang konsisten, sambil menutup gap dengan data yang
sudah diketahui dari InteractionMemory (preferensi lintas sesi seperti
last_project/last_workspace) dan available_capability (kontrak field
yang dimengerti capability/tool tujuan).

planner_output diharapkan berbentuk dict longgar, contoh:
    {
        "intent": "create_folder",
        "confidence": 0.9,
        "known_data": {"workspace": "Projects"},
        "missing_data": [{"key": "folder_name", "label": "Nama Folder"}],
        "choices": [],
        "danger": False,
        "needs_review": False,
        "priority": "normal",
    }
REI Planner (agents/rei/planner.py) yang bertugas menyusun dict ini -
DIOAnalyzer HANYA menormalkan bentuknya, tidak tahu domain apa pun.
"""

from typing import Any, Optional

from core.dio.models import InteractionPlan, MissingField, ChoiceOption
from core.dio.reasoning import select_mode
from core.dio.interaction_memory import InteractionMemory


class DIOAnalyzer:

    def __init__(self, memory: Optional[InteractionMemory] = None):
        self.memory = memory

    def analyze(
        self,
        user_message: str,
        planner_output: dict,
        available_capability: Optional[dict] = None,
        context: Optional[dict] = None,
    ) -> InteractionPlan:
        capability = available_capability or {}
        context = dict(context or {})

        intent = planner_output.get("intent") or capability.get("name") or "unknown"
        confidence = float(planner_output.get("confidence", 0.5))
        known_data = dict(planner_output.get("known_data") or {})
        raw_missing = list(planner_output.get("missing_data") or [])
        raw_choices = list(planner_output.get("choices") or [])

        missing_fields = [self._to_missing_field(m) for m in raw_missing]

        # Tutup gap pakai InteractionMemory (context lintas sesi, lintas
        # domain) - field yang sudah diketahui pindah dari missing ke
        # known, TANPA menyentuh Chat Memory (core/memory.py) sama sekali.
        if self.memory is not None:
            still_missing = []
            for missing in missing_fields:
                remembered = self.memory.load(missing.key)
                if remembered is not None and missing.key not in known_data:
                    known_data[missing.key] = remembered
                else:
                    still_missing.append(missing)
            missing_fields = still_missing

        danger = bool(planner_output.get("danger") or capability.get("danger"))
        needs_review = bool(planner_output.get("needs_review") or capability.get("needs_review"))
        priority = planner_output.get("priority") or ("critical" if danger else "normal")

        plan = InteractionPlan(
            intent=intent,
            confidence=confidence,
            known_data=known_data,
            missing_data=missing_fields,
            choices=[self._to_choice(c) for c in raw_choices],
            priority=priority,
            danger=danger,
            needs_review=needs_review,
            source_agent=planner_output.get("source_agent"),
            context=context,
        )

        plan.suggested_mode = select_mode(plan)

        return plan

    @staticmethod
    def _to_missing_field(raw: Any) -> MissingField:
        if isinstance(raw, MissingField):
            return raw
        if isinstance(raw, str):
            return MissingField(key=raw)

        options = [DIOAnalyzer._to_choice(o) for o in raw.get("options", [])]
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
            pattern=raw.get("pattern"),
        )

    @staticmethod
    def _to_choice(raw: Any) -> ChoiceOption:
        if isinstance(raw, ChoiceOption):
            return raw
        if isinstance(raw, str):
            return ChoiceOption(value=raw, label=raw)
        return ChoiceOption(value=raw["value"], label=raw.get("label", raw["value"]))