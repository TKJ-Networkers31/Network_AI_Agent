"""
core/model_router.py — pemilih model otomatis (Sprint 1).

Flow: TaskClassification -> ModelRouter.select() -> ModelPolicy -> SelectedModel
REI/Planner TIDAK memilih model; mereka hanya menerima SelectedModel dari sini.
"""

import logging
from typing import Optional

from core.events import event_bus
from core.model_policy import ModelPolicy, get_model_policy
from core.model_store import ModelStore, get_model_store
from core.model_types import (
    DEFAULT_LABEL, EVENT_MODEL_SELECTED, VALID_LABELS, SelectedModel, TaskClassification,
)

logger = logging.getLogger("aira.model_router")


class ModelRouter:

    def __init__(self, store: Optional[ModelStore] = None, policy: Optional[ModelPolicy] = None):
        self._store = store
        self._policy = policy or (ModelPolicy(store) if store else None)

    @property
    def store(self) -> ModelStore:
        return self._store or get_model_store()

    @property
    def policy(self) -> ModelPolicy:
        return self._policy or get_model_policy()

    def select(self, task: TaskClassification, publish: bool = True) -> Optional[SelectedModel]:
        label = task.primary_label if task.primary_label in VALID_LABELS else DEFAULT_LABEL
        return self.select_for_label(label, publish=publish)

    def select_for_label(self, label: str, publish: bool = True) -> Optional[SelectedModel]:
        routing = self.store.get_routing()
        default_id = routing.get(label) or routing.get(DEFAULT_LABEL)
        row = self.store.get_model(default_id)

        selected = self.policy.ensure_usable(row, label)

        if selected is None:
            logger.error("ROUTER | tidak ada model yang bisa dipakai untuk label '%s'.", label)
            return None

        logger.info("ROUTER | label=%s -> %s (%s)", label, selected.display_name, selected.provider)

        if publish:
            try:
                event_bus.publish(
                    EVENT_MODEL_SELECTED, agent="ROUTER",
                    data={"display_name": selected.display_name, "provider": selected.provider, "label": label},
                )
            except Exception:
                logger.exception("Gagal publish model.selected (diabaikan).")

        return selected


_router_singleton: Optional[ModelRouter] = None


def get_model_router() -> ModelRouter:
    global _router_singleton
    if _router_singleton is None:
        _router_singleton = ModelRouter()
    return _router_singleton