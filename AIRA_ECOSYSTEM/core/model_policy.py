"""
core/model_policy.py — aturan fallback & batas context (Sprint 1).

Rules (semua data dari database, tidak ada nama model yang di-hardcode):
  1. Model disabled/hilang               -> fallback          (ensure_usable)
  2. Provider gagal                      -> fallback          (on_provider_failure)
  3. Context > context_window            -> model dgn label sama & context
                                            terbesar (yang lebih besar dari
                                            model saat ini)  (check_context)
  4. Tidak ada kandidat rule 3           -> fallback          (check_context)

Setiap perpindahan model mempublish event "model.fallback" {from, to, reason}.
"""

import json
import logging
from typing import Optional

from core.events import event_bus
from core.model_store import ModelStore, get_model_store
from core.model_types import DEFAULT_LABEL, EVENT_MODEL_FALLBACK, SelectedModel

logger = logging.getLogger("aira.model_policy")


def estimate_tokens(messages: list, tools: Optional[list] = None) -> int:
    """Estimasi kasar (~3 karakter/token, konservatif untuk teks Indonesia + JSON)."""
    try:
        raw = json.dumps(messages, ensure_ascii=False, default=str)
        if tools:
            raw += json.dumps(tools, ensure_ascii=False, default=str)
    except Exception:
        raw = str(messages)
    return len(raw) // 3 + 1


class ModelPolicy:

    def __init__(self, store: Optional[ModelStore] = None):
        self._store = store

    @property
    def store(self) -> ModelStore:
        return self._store or get_model_store()

    # ----------------------------------------------------------- lookup

    def retry_count(self) -> int:
        return int(self.store.get_policy().get("retry_provider") or 0)

    def fallback_model(self, exclude_id: Optional[str] = None) -> Optional[dict]:
        """Model fallback dari policy; kalau tidak ada/nonaktif, jaring pengaman:
        default label general, lalu model enabled pertama."""
        fallback_id = self.store.get_policy().get("fallback_model_id")
        if fallback_id and fallback_id != exclude_id:
            row = self.store.get_model(fallback_id)
            if row and row["enabled"]:
                return row

        general_id = self.store.get_routing().get(DEFAULT_LABEL)
        if general_id and general_id != exclude_id:
            row = self.store.get_model(general_id)
            if row and row["enabled"]:
                return row

        for row in self.store.list_models(enabled_only=True):
            if row["id"] != exclude_id:
                return row

        return None

    # ------------------------------------------------------------ rules

    def ensure_usable(self, row: Optional[dict], task_label: str) -> Optional[SelectedModel]:
        """Rule 1."""
        if row and row["enabled"]:
            return SelectedModel.from_row(row)

        reason = "model_disabled" if row else "model_missing"
        origin_id = row["id"] if row else None
        fallback = self.fallback_model(exclude_id=origin_id)

        if not fallback:
            logger.error("Tidak ada model fallback untuk label '%s' (%s).", task_label, reason)
            return None

        if origin_id:
            self._publish_fallback(origin_id, fallback["id"], reason)

        return SelectedModel.from_row(fallback, fallback_from=origin_id)

    def check_context(self, selected: SelectedModel, estimated_tokens: int) -> SelectedModel:
        """Rule 3 lalu rule 4."""
        window = selected.context_window

        if not window or estimated_tokens <= window:
            return selected

        larger = [
            m for m in self.store.list_models(label=selected.label, enabled_only=True)
            if m["id"] != selected.id and (m["context_window"] or 0) > window
        ]

        if larger:
            best = max(larger, key=lambda m: m["context_window"])
            self._publish_fallback(selected.id, best["id"], "context_exceeded")
            return SelectedModel.from_row(best, fallback_from=selected.id)

        fallback = self.fallback_model(exclude_id=selected.id)
        if fallback:
            self._publish_fallback(selected.id, fallback["id"], "context_exceeded")
            return SelectedModel.from_row(fallback, fallback_from=selected.id)

        return selected

    def on_provider_failure(self, failed: SelectedModel, reason: str) -> Optional[SelectedModel]:
        """Rule 2."""
        fallback = self.fallback_model(exclude_id=failed.id)
        if not fallback:
            return None
        self._publish_fallback(failed.id, fallback["id"], reason)
        return SelectedModel.from_row(fallback, fallback_from=failed.id)

    # ----------------------------------------------------------- events

    @staticmethod
    def _publish_fallback(from_id: str, to_id: str, reason: str) -> None:
        logger.warning("MODEL FALLBACK | %s -> %s (%s)", from_id, to_id, reason)
        try:
            event_bus.publish(
                EVENT_MODEL_FALLBACK, agent="POLICY",
                data={"from": from_id, "to": to_id, "reason": reason},
            )
        except Exception:
            logger.exception("Gagal publish model.fallback (diabaikan).")


_policy_singleton: Optional[ModelPolicy] = None


def get_model_policy() -> ModelPolicy:
    global _policy_singleton
    if _policy_singleton is None:
        _policy_singleton = ModelPolicy()
    return _policy_singleton