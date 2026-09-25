"""
core/unified_context/builder.py — UnifiedContextBuilder (Sprint 2.7 /
Wave 2 / W9).

Composes ONE UnifiedContext packet per turn out of context sources that
already exist elsewhere in AIRA - it does NOT reimplement any of them:

    conversation  -> core.context.ContextBuilder (UNCHANGED, reused as-is
                     via Dependency Injection - this is explicitly NOT a
                     second Context Builder). Its identity/persona/memory/
                     runtime_state/tool_context sections become individual
                     ContextItems under the "conversation" source.
    location      -> the SAME AIRAContext.location section the existing
                     Context Builder already produces (core.location,
                     untouched) - surfaced as its own top-level source
                     because Capability Discovery treats "location" as its
                     own context type.
    attachment    -> core.attachments (metadata/reference only -
                     core.attachments.context.attachment_to_context_dict()
                     already guarantees no binary content; that guarantee
                     is reused here, not reimplemented).
    selection     -> core.selection (SelectionContext.to_dict(), already
                     text-only). core.selection has no "list by session"
                     store today, so selections are always exactly what
                     the caller passes in (never auto-fetched).
    artifact      -> core.artifacts (Artifact metadata only -
                     storage_reference is a path, never bytes).
    permission    -> explicit pending/confirmed permission state handed in
                     by the caller. No persistent "permission store"
                     exists yet in AIRA; nothing here invents one - the
                     source is simply absent unless the caller supplies
                     something.

Nothing in this module touches core.orchestrator, streaming,
core.chat_sessions, or core.capability.CapabilityRegistry - the only
capability import anywhere in this package is the read-only CONTEXT_*
vocabulary in models.py, used so UnifiedContext.context_types() can be
handed straight to CapabilityDiscovery.discover(context=...).
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Iterable, Optional

from core.unified_context.models import (
    ContextItem,
    SOURCE_ARTIFACT,
    SOURCE_ATTACHMENT,
    SOURCE_CONVERSATION,
    SOURCE_LOCATION,
    SOURCE_PERMISSION,
    SOURCE_SELECTION,
    UnifiedContext,
    UnifiedContextSource,
)

logger = logging.getLogger("aira.unified_context")

# AIRAContext fields folded into the "conversation" source as individual
# ContextItems (location is deliberately excluded - it becomes its own
# top-level SOURCE_LOCATION instead).
_CONVERSATION_SECTION_NAMES = (
    "identity", "persona", "memory", "runtime_state", "tool_context",
)


# ============================================================
# DEFAULT PROVIDERS (lazy import - only used when not injected, and only
# when actually called, so constructing this class never touches disk)
# ============================================================

def _default_context_builder():
    from core.context import get_context_builder
    return get_context_builder()


def _default_attachments(session_id: Optional[str]):
    if not session_id:
        return []
    from core.attachments import get_attachment_engine
    return get_attachment_engine().list(session_id=session_id)


def _default_artifacts(session_id: Optional[str]):
    if not session_id:
        return []
    from core.artifacts import get_artifact_engine
    return get_artifact_engine().list(session_id=session_id)


def _attachment_item(attachment: Any) -> Optional[ContextItem]:
    from core.attachments.context import attachment_to_context_dict

    if attachment is None or getattr(attachment, "is_deleted", False):
        return None

    return ContextItem(
        id=str(attachment.id), source=SOURCE_ATTACHMENT,
        data=attachment_to_context_dict(attachment),
        provenance={"origin": "core.attachments", "status": getattr(attachment, "status", None)},
    )


def _selection_item(selection: Any) -> Optional[ContextItem]:
    if selection is None:
        return None

    data = selection.to_dict() if hasattr(selection, "to_dict") else dict(selection)
    selection_id = data.get("selection_id") or getattr(selection, "selection_id", None)

    if not selection_id:
        return None

    return ContextItem(
        id=str(selection_id), source=SOURCE_SELECTION, data=data,
        text=str(data.get("selected_text") or ""),
        provenance={"origin": "core.selection"},
    )


def _artifact_item(artifact: Any) -> Optional[ContextItem]:
    if artifact is None:
        return None

    data = artifact.to_dict() if hasattr(artifact, "to_dict") else dict(artifact)
    artifact_id = data.get("id") or getattr(artifact, "id", None)

    if not artifact_id:
        return None

    return ContextItem(
        id=str(artifact_id), source=SOURCE_ARTIFACT, data=data,
        provenance={"origin": "core.artifacts", "status": data.get("status")},
    )


class UnifiedContextBuilder:
    """
    Dependency Injection, same convention as
    core.context.builder.ContextBuilder and core.selection.builder.
    SelectionBuilder: every provider is optional and swappable; defaults
    are lazily imported so constructing this class never touches disk.
    """

    def __init__(
        self,
        *,
        context_builder=None,
        attachments_provider: Optional[Callable[[Optional[str]], Iterable]] = None,
        artifacts_provider: Optional[Callable[[Optional[str]], Iterable]] = None,
    ):
        self._context_builder = context_builder
        self._attachments_provider = attachments_provider or _default_attachments
        self._artifacts_provider = artifacts_provider or _default_artifacts

    @property
    def context_builder(self):
        return self._context_builder or _default_context_builder()

    # ------------------------------------------------------------ public

    def build(
        self,
        user_input: str,
        *,
        session_id: Optional[str] = None,
        task: Any = None,
        attachments: Optional[Iterable] = None,
        selections: Optional[Iterable] = None,
        artifacts: Optional[Iterable] = None,
        pending_permissions: Optional[Iterable[dict]] = None,
        confirmed_permissions: Optional[Iterable[str]] = None,
    ) -> UnifiedContext:
        """
        Build one UnifiedContext for this turn. Never raises - a failing
        source is recorded (available=False + a warning) and every other
        source still builds normally.

        attachments/artifacts: pass an explicit iterable to OVERRIDE the
        default session lookup (an empty list explicitly means "none" -
        omit the argument entirely to use the default lookup).
        selections/permissions have no persistent store to default from
        yet, so they are always exactly what the caller passes
        (None/omitted = source absent).
        """
        warnings: list[str] = []
        unified = UnifiedContext(session_id=session_id, user_input=str(user_input or ""))

        aira_context = self._call(
            "conversation", lambda: self._build_conversation(user_input, session_id, task), warnings,
        )

        if aira_context is not None:
            unified.system_prompt = aira_context.system_prompt or ""
            unified.conversation_context = aira_context.to_dict(include_prompt=False)
            unified.task = aira_context.task
            unified.warnings.extend(f"conversation.{w}" for w in aira_context.warnings)

            unified.sources[SOURCE_CONVERSATION] = self._conversation_source(aira_context)
            unified.sources[SOURCE_LOCATION] = self._location_source(aira_context)
        else:
            unified.sources[SOURCE_CONVERSATION] = UnifiedContextSource(
                name=SOURCE_CONVERSATION, available=False, error="unavailable",
            )
            unified.sources[SOURCE_LOCATION] = UnifiedContextSource(
                name=SOURCE_LOCATION, available=False, error="unavailable",
            )

        if unified.task is None:
            unified.task = self._normalize_task(task)

        unified.sources[SOURCE_ATTACHMENT] = self._collection_source(
            SOURCE_ATTACHMENT,
            lambda: attachments if attachments is not None else self._attachments_provider(session_id),
            _attachment_item, warnings,
        )

        unified.sources[SOURCE_SELECTION] = self._collection_source(
            SOURCE_SELECTION, lambda: selections or [], _selection_item, warnings,
        )

        unified.sources[SOURCE_ARTIFACT] = self._collection_source(
            SOURCE_ARTIFACT,
            lambda: artifacts if artifacts is not None else self._artifacts_provider(session_id),
            _artifact_item, warnings,
        )

        unified.sources[SOURCE_PERMISSION] = self._permission_source(
            pending_permissions, confirmed_permissions,
        )

        unified.warnings.extend(warnings)

        logger.info("UNIFIED CONTEXT | built %s", unified.summary())

        return unified

    # --------------------------------------------------------- sections

    def _build_conversation(self, user_input, session_id, task):
        return self.context_builder.build(user_input, session_id=session_id, task=task)

    @staticmethod
    def _conversation_source(aira_context) -> UnifiedContextSource:
        items = []

        for name in _CONVERSATION_SECTION_NAMES:
            section = getattr(aira_context, name, None)

            if section is None:
                continue

            items.append(ContextItem(
                id=name, source=SOURCE_CONVERSATION,
                data=dict(section.data or {}), text=section.text or "",
                provenance={"origin": section.source or "core.context"},
            ))

        return UnifiedContextSource(name=SOURCE_CONVERSATION, items=items)

    @staticmethod
    def _location_source(aira_context) -> UnifiedContextSource:
        section = aira_context.location

        if section is None:
            return UnifiedContextSource(name=SOURCE_LOCATION, items=[])

        item = ContextItem(
            id="location", source=SOURCE_LOCATION,
            data=dict(section.data or {}), text=section.text or "",
            provenance={"origin": section.source or "core.location"},
        )
        return UnifiedContextSource(name=SOURCE_LOCATION, items=[item])

    @staticmethod
    def _collection_source(name: str, loader, item_fn, warnings: list) -> UnifiedContextSource:
        try:
            raw = list(loader() or [])
        except Exception as exc:
            logger.warning(
                "UNIFIED CONTEXT | source '%s' failed (%s).", name, type(exc).__name__, exc_info=True,
            )
            warnings.append(f"{name}: unavailable ({type(exc).__name__})")
            return UnifiedContextSource(name=name, available=False, error=type(exc).__name__)

        items = []

        for entry in raw:
            try:
                item = item_fn(entry)
            except Exception as exc:
                logger.warning(
                    "UNIFIED CONTEXT | item in source '%s' failed to convert (%s).",
                    name, type(exc).__name__,
                )
                continue

            if item is not None:
                items.append(item)

        return UnifiedContextSource(name=name, items=items)

    @staticmethod
    def _permission_source(pending, confirmed) -> UnifiedContextSource:
        pending = list(pending or [])
        confirmed_ids = [str(c) for c in (confirmed or [])]

        items = []

        for entry in pending:
            entry = entry if isinstance(entry, dict) else {"id": str(entry)}
            perm_id = str(entry.get("id") or entry.get("capability_id") or "")

            if not perm_id:
                continue

            items.append(ContextItem(
                id=perm_id, source=SOURCE_PERMISSION,
                data={k: v for k, v in entry.items() if k != "id"},
                provenance={"origin": "caller", "state": "pending"},
            ))

        if confirmed_ids:
            items.append(ContextItem(
                id="__confirmed__", source=SOURCE_PERMISSION,
                data={"confirmed_ids": confirmed_ids},
                provenance={"origin": "caller", "state": "confirmed"},
            ))

        return UnifiedContextSource(name=SOURCE_PERMISSION, items=items)

    @staticmethod
    def _normalize_task(task: Any) -> Optional[dict]:
        if task is None:
            return None

        if isinstance(task, dict):
            return dict(task) if task else None

        to_dict = getattr(task, "to_dict", None)

        if callable(to_dict):
            try:
                result = to_dict()
                return dict(result) if isinstance(result, dict) and result else None
            except Exception:
                return None

        return None

    @staticmethod
    def _call(name: str, fn, warnings: list):
        try:
            return fn()
        except Exception as exc:
            logger.warning(
                "UNIFIED CONTEXT | source '%s' failed (%s).", name, type(exc).__name__, exc_info=True,
            )
            warnings.append(f"{name}: unavailable ({type(exc).__name__})")
            return None


# ================================================================ SINGLETON

_builder_singleton: Optional[UnifiedContextBuilder] = None
_builder_lock = threading.Lock()


def get_unified_context_builder() -> UnifiedContextBuilder:
    global _builder_singleton

    if _builder_singleton is None:
        with _builder_lock:
            if _builder_singleton is None:
                _builder_singleton = UnifiedContextBuilder()

    return _builder_singleton