"""
core/task_classifier.py — klasifikasi intent dengan LLM kecil (Sprint 1).

Model classifier = model default label "general" dari Model Router (bukan
nama model yang di-hardcode). System prompt persis sesuai spec; daftar label
ditaruh di pesan user karena system prompt spec tidak menyebutkannya.

classify() TIDAK PERNAH raise: gagal apa pun -> fallback general / 0.50.
"""

import json
import logging
import re
from typing import Optional

from agents.rei.provider_client import ProviderClient
from core.events import event_bus
from core.model_router import ModelRouter, get_model_router
from core.model_types import (
    DEFAULT_LABEL, EVENT_TASK_CLASSIFIED, VALID_LABELS, TaskClassification,
)

logger = logging.getLogger("aira.task_classifier")

CLASSIFIER_SYSTEM_PROMPT = """You are AIRA Task Classifier.

Your only job is to classify the user's request.

Return ONLY JSON.

Choose exactly one label.

Never answer the user's question.

Output schema:

{
"primary_label":"",
"confidence":0.00,
"requires_tools":false,
"requires_vision":false,
"requires_voice":false
}"""

LABEL_GUIDE = """Valid labels:
- general: casual chat, general knowledge, writing
- reasoning: math, logic, multi-step analysis, explaining hard concepts
- coding: programming, debugging, refactoring, code review
- networking: routers, MikroTik/RouterOS, VRRP, routing, firewall, SNMP, SSH to devices, ping/traceroute
- vision: images, camera, screenshots, object detection
- voice: speech, speaking, listening, transcription
- retrieval: web search, latest information, recalling saved facts
- automation: file operations, scheduled or repeated tasks, running tools

User request:
"""

MAX_PROMPT_CHARS = 1500
CLASSIFIER_TIMEOUT = 60
CLASSIFIER_MAX_TOKENS = 120

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_JSON_OBJECT_RE = re.compile(r"\{[^{}]*\}", re.DOTALL)


def _to_bool(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes")
    return bool(value)


def parse_classification(raw: Optional[str]) -> TaskClassification:
    """Parse output LLM. Tidak pernah raise."""
    if not raw:
        return TaskClassification.fallback()

    text = _THINK_RE.sub("", raw)
    match = _JSON_OBJECT_RE.search(text)
    if not match:
        return TaskClassification.fallback()

    try:
        data = json.loads(match.group(0))
    except (json.JSONDecodeError, ValueError):
        return TaskClassification.fallback()

    if not isinstance(data, dict):
        return TaskClassification.fallback()

    label = str(data.get("primary_label", "")).strip().lower()
    if label not in VALID_LABELS:
        return TaskClassification.fallback()

    try:
        confidence = max(0.0, min(1.0, float(data.get("confidence", 0.5))))
    except (TypeError, ValueError):
        confidence = 0.5

    return TaskClassification(
        primary_label=label,
        confidence=round(confidence, 2),
        requires_tools=_to_bool(data.get("requires_tools", False)),
        requires_vision=_to_bool(data.get("requires_vision", False)),
        requires_voice=_to_bool(data.get("requires_voice", False)),
    )


class TaskClassifier:

    def __init__(self, router: Optional[ModelRouter] = None, client=None):
        self._router = router
        self._client = client or ProviderClient

    @property
    def router(self) -> ModelRouter:
        return self._router or get_model_router()

    def classify(self, prompt: str) -> TaskClassification:
        prompt = (prompt or "").strip()

        try:
            result = self._classify_with_llm(prompt) if prompt else TaskClassification.fallback()
        except Exception:
            logger.exception("Classifier gagal tak terduga - pakai fallback.")
            result = TaskClassification.fallback()

        logger.info("CLASSIFIER | label=%s confidence=%.2f", result.primary_label, result.confidence)

        try:
            event_bus.publish(
                EVENT_TASK_CLASSIFIED, agent="CLASSIFIER",
                data={"label": result.primary_label, "confidence": result.confidence},
            )
        except Exception:
            logger.exception("Gagal publish task.classified (diabaikan).")

        return result

    def _classify_with_llm(self, prompt: str) -> TaskClassification:
        model = self.router.select_for_label(DEFAULT_LABEL, publish=False)
        if model is None:
            logger.warning("Classifier: tidak ada model general - pakai fallback.")
            return TaskClassification.fallback()

        response = self._client.chat(
            provider=model.provider,
            model=model.model_id,
            messages=[
                {"role": "system", "content": CLASSIFIER_SYSTEM_PROMPT},
                {"role": "user", "content": LABEL_GUIDE + prompt[:MAX_PROMPT_CHARS]},
            ],
            tools=None,
            temperature=0,
            max_tokens=CLASSIFIER_MAX_TOKENS,
            think=False,
            timeout=CLASSIFIER_TIMEOUT,
        )

        if "error" in response:
            logger.warning("Classifier: provider error - %s", response["error"])
            return TaskClassification.fallback()

        return parse_classification((response.get("message") or {}).get("content"))


_classifier_singleton: Optional[TaskClassifier] = None


def get_task_classifier() -> TaskClassifier:
    global _classifier_singleton
    if _classifier_singleton is None:
        _classifier_singleton = TaskClassifier()
    return _classifier_singleton


def classify(prompt: str) -> TaskClassification:
    return get_task_classifier().classify(prompt)