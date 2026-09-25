"""
core/workspace_links/service.py - WorkspaceIntegrationService
(Sprint 2.7 / Wave 2 / W6).

Connects the EXISTING Workspace (core/filesystem) with Conversation
(core/chat_sessions), Attachment (core/attachments), and Artifact
(core/artifacts) - WITHOUT creating a second filesystem and WITHOUT
duplicating any file. Every WorkspaceLink this module hands back is either:

    - a CONVERSATION-kind row this module itself persisted
      (core/workspace_links/store.py), for files a session saved straight
      into the Workspace or explicitly "adopted", or
    - an ARTIFACT/ATTACHMENT-kind row DERIVED, at read time, from
      core.artifacts.ArtifactStore / core.attachments.AttachmentStore -
      never copied into this module's own table, so there is exactly ONE
      place that owns each fact (Artifact.session_id stays owned by
      core/artifacts, Attachment.session_id stays owned by
      core/attachments).

Four flows (per the Sprint 2.7 / W6 brief):

    conversation -> workspace : save_conversation_file() writes bytes
                                 through the EXISTING FileOperations and
                                 records a CONVERSATION link.
                                 adopt_workspace_file() claims ownership of
                                 a pre-existing Workspace path without
                                 writing anything.
    workspace -> conversation : resolve_owner() / list_for_session() answer
                                 "whose is this path?" by checking this
                                 module's own table FIRST, then Artifact,
                                 then Attachment.
    artifact -> workspace      : never written here - core.artifacts
                                 already stores session_id +
                                 storage_reference; this module only
                                 SURFACES that fact through the same
                                 WorkspaceLink shape.
    attachment -> workspace    : same as artifact, for core.attachments
                                 (user_upload/workspace sources only -
                                 "generated" attachments resolve through
                                 the artifact they wrap; "external"
                                 attachments have no workspace path and are
                                 never returned here; soft-deleted
                                 attachments are excluded).

A path is never claimed by two flows at once: Artifacts/* and
Attachments/* already live in disjoint subtrees owned by their own
engines, and save_conversation_file()/adopt_workspace_file() explicitly
refuse to create a CONVERSATION link inside either subtree.

Sandboxing/permissions are NEVER reimplemented here: every path this
module touches is resolved and permission-checked by the EXISTING
core.filesystem.FileOperations / WorkspaceManager, injected lazily so
importing this module never touches disk (same Dependency Injection
pattern as core/artifacts/engine.py and core/attachments/engine.py).
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Optional

from core.workspace_links.models import LinkKind, LinkResult, WorkspaceLink
from core.workspace_links.store import WorkspaceLinkStore, get_workspace_link_store

logger = logging.getLogger("aira.workspace_links")

RESERVED_PREFIXES = ("Artifacts/", "Attachments/")


def _is_reserved(relative_path: str) -> bool:
    return relative_path.startswith(RESERVED_PREFIXES)


# ============================================================ DEFAULTS
# (lazy import - only used when not injected, so importing this module
# never touches disk/DB - same pattern as core/artifacts/engine.py)

def _default_write_text(relative_path: str, content: str) -> Any:
    from core.filesystem import FileOperations
    return FileOperations().write_text(relative_path, content)


def _default_workspace_exists(relative_path: str) -> bool:
    from core.filesystem import get_workspace_manager
    return get_workspace_manager().exists(relative_path)


def _default_session_lookup(session_id: str) -> bool:
    from core import chat_sessions as store
    return store.get_session_row(session_id) is not None


def _default_artifact_lookup(relative_path: str):
    from core.artifacts.store import get_artifact_store
    return get_artifact_store().get_by_storage_reference(relative_path)


def _default_attachment_lookup(relative_path: str):
    from core.attachments.store import get_attachment_store
    return get_attachment_store().get_by_storage_reference(relative_path)


def _default_artifacts_for_session(session_id: str) -> list:
    from core.artifacts.store import get_artifact_store
    return get_artifact_store().list(session_id=session_id)


def _default_attachments_for_session(session_id: str) -> list:
    from core.attachments.store import get_attachment_store
    return get_attachment_store().list(session_id=session_id)


def _publish(event_name: str, **data: Any) -> None:
    """Best-effort publish to the EXISTING Event Bus. Never raises - same
    defensive pattern as core/artifacts/engine.py::_publish."""
    try:
        from core.events import event_bus
        event_bus.publish(event_name, source="WORKSPACE_LINKS", agent="WORKSPACE_LINKS", data=data)
    except Exception:
        logger.debug("WORKSPACE_LINKS | gagal publish %s (diabaikan).", event_name, exc_info=True)


class WorkspaceIntegrationService:
    """
    Dependency Injection: every collaborator can be swapped - tests inject
    fakes so no real Workspace/database is ever touched (same approach as
    core/artifacts/tests/test_engine.py and core/attachments/tests/test_engine.py).
    """

    def __init__(
        self,
        store: Optional[WorkspaceLinkStore] = None,
        write_text: Optional[Callable[[str, str], Any]] = None,
        workspace_exists: Optional[Callable[[str], bool]] = None,
        session_lookup: Optional[Callable[[str], bool]] = None,
        artifact_lookup: Optional[Callable[[str], Any]] = None,
        attachment_lookup: Optional[Callable[[str], Any]] = None,
        artifacts_for_session: Optional[Callable[[str], list]] = None,
        attachments_for_session: Optional[Callable[[str], list]] = None,
    ):
        self._store = store
        self._write_text = write_text or _default_write_text
        self._workspace_exists = workspace_exists or _default_workspace_exists
        self._session_lookup = session_lookup or _default_session_lookup
        self._artifact_lookup = artifact_lookup or _default_artifact_lookup
        self._attachment_lookup = attachment_lookup or _default_attachment_lookup
        self._artifacts_for_session = artifacts_for_session or _default_artifacts_for_session
        self._attachments_for_session = attachments_for_session or _default_attachments_for_session
        self._lock = threading.Lock()

    @property
    def store(self) -> WorkspaceLinkStore:
        return self._store or get_workspace_link_store()

    # ============================================================
    # conversation -> workspace
    # ============================================================

    def save_conversation_file(
        self,
        *,
        session_id: str,
        relative_path: str,
        content: str,
        message_id: Optional[str] = None,
        note: Optional[str] = None,
    ) -> LinkResult:
        """Write text content into the EXISTING Workspace (via
        FileOperations - sandbox/permissions enforced there, not here) and
        record a CONVERSATION-kind ownership link."""
        session_id = (session_id or "").strip()
        relative_path = (relative_path or "").strip().replace("\\", "/").strip("/")

        if not session_id:
            return LinkResult(False, errors=["session_id wajib diisi."])
        if not relative_path:
            return LinkResult(False, errors=["relative_path wajib diisi."])
        if _is_reserved(relative_path):
            return LinkResult(False, errors=[
                f"Path '{relative_path}' dikelola oleh engine artifact/attachment, bukan conversation link.",
            ])
        if not self._session_lookup(session_id):
            return LinkResult(False, errors=[f"session '{session_id}' tidak ditemukan."])

        try:
            write_result = self._write_text(relative_path, content or "")
        except Exception as exc:
            logger.exception("WORKSPACE_LINKS | gagal menulis %s", relative_path)
            return LinkResult(False, errors=[f"Gagal menulis file: {exc}"])

        if not getattr(write_result, "success", False):
            return LinkResult(False, errors=[getattr(write_result, "error", None) or "Gagal menulis file."])

        link = WorkspaceLink(
            relative_path=relative_path, session_id=session_id, message_id=message_id,
            kind=LinkKind.CONVERSATION.value, note=note,
        )

        with self._lock:
            self.store.save(link)

        logger.info("WORKSPACE LINK CREATED | session=%s path=%s", session_id, relative_path)
        _publish("workspace_link.created", session_id=session_id, relative_path=relative_path, kind=link.kind)

        return LinkResult(True, link=link)

    def adopt_workspace_file(
        self,
        *,
        session_id: str,
        relative_path: str,
        message_id: Optional[str] = None,
        note: Optional[str] = None,
    ) -> LinkResult:
        """Claim ownership of a file that ALREADY exists in the Workspace
        (e.g. dropped in via the Workspace UI outside any conversation)
        without writing/duplicating anything."""
        session_id = (session_id or "").strip()
        relative_path = (relative_path or "").strip().replace("\\", "/").strip("/")

        if not session_id:
            return LinkResult(False, errors=["session_id wajib diisi."])
        if not relative_path:
            return LinkResult(False, errors=["relative_path wajib diisi."])
        if _is_reserved(relative_path):
            return LinkResult(False, errors=[
                f"Path '{relative_path}' dikelola oleh engine artifact/attachment, bukan conversation link.",
            ])
        if not self._session_lookup(session_id):
            return LinkResult(False, errors=[f"session '{session_id}' tidak ditemukan."])

        try:
            exists = self._workspace_exists(relative_path)
        except Exception as exc:
            return LinkResult(False, errors=[f"Gagal memeriksa workspace: {exc}"])

        if not exists:
            return LinkResult(False, errors=[f"Path '{relative_path}' tidak ditemukan di workspace."])

        link = WorkspaceLink(
            relative_path=relative_path, session_id=session_id, message_id=message_id,
            kind=LinkKind.CONVERSATION.value, note=note,
        )

        with self._lock:
            self.store.save(link)

        logger.info("WORKSPACE LINK ADOPTED | session=%s path=%s", session_id, relative_path)
        _publish("workspace_link.created", session_id=session_id, relative_path=relative_path, kind=link.kind)

        return LinkResult(True, link=link)

    # ============================================================
    # workspace -> conversation
    # ============================================================

    def resolve_owner(self, relative_path: str) -> Optional[WorkspaceLink]:
        """
        Given a Workspace path, answer "whose is this, conversationally?".
        Lookup order (first match wins):
            1. this module's own CONVERSATION links
            2. core.artifacts (ARTIFACT-kind, derived)
            3. core.attachments (ATTACHMENT-kind, derived)
        Returns None if the path is unowned (never raises).
        """
        relative_path = (relative_path or "").replace("\\", "/").strip("/")

        if not relative_path:
            return None

        conversation_link = self.store.get_by_path(relative_path)
        if conversation_link is not None:
            return conversation_link

        try:
            artifact = self._artifact_lookup(relative_path)
        except Exception:
            logger.exception("WORKSPACE_LINKS | artifact lookup gagal untuk %s", relative_path)
            artifact = None

        if artifact is not None and getattr(artifact, "session_id", None):
            return WorkspaceLink(
                relative_path=relative_path, session_id=artifact.session_id,
                kind=LinkKind.ARTIFACT.value, ref_id=artifact.id,
                created_at=artifact.created_at,
            )

        try:
            attachment = self._attachment_lookup(relative_path)
        except Exception:
            logger.exception("WORKSPACE_LINKS | attachment lookup gagal untuk %s", relative_path)
            attachment = None

        if attachment is not None and getattr(attachment, "session_id", None):
            return WorkspaceLink(
                relative_path=relative_path, session_id=attachment.session_id,
                message_id=attachment.message_id, kind=LinkKind.ATTACHMENT.value,
                ref_id=attachment.id, created_at=attachment.created_at,
            )

        return None

    def list_for_session(self, session_id: str) -> list[WorkspaceLink]:
        """Every Workspace path this session is associated with, across all
        three flows, newest first. Never raises - a failing source is
        skipped (logged), the other sources still return."""
        session_id = (session_id or "").strip()

        if not session_id:
            return []

        links: list[WorkspaceLink] = list(self.store.list_for_session(session_id))

        try:
            for artifact in self._artifacts_for_session(session_id):
                if getattr(artifact, "storage_reference", None):
                    links.append(WorkspaceLink(
                        relative_path=artifact.storage_reference, session_id=session_id,
                        kind=LinkKind.ARTIFACT.value, ref_id=artifact.id,
                        created_at=artifact.created_at,
                    ))
        except Exception:
            logger.exception("WORKSPACE_LINKS | gagal mengambil artifact untuk sesi %s", session_id)

        try:
            for attachment in self._attachments_for_session(session_id):
                if getattr(attachment, "storage_reference", None) and not getattr(attachment, "is_deleted", False):
                    links.append(WorkspaceLink(
                        relative_path=attachment.storage_reference, session_id=session_id,
                        message_id=attachment.message_id, kind=LinkKind.ATTACHMENT.value,
                        ref_id=attachment.id, created_at=attachment.created_at,
                    ))
        except Exception:
            logger.exception("WORKSPACE_LINKS | gagal mengambil attachment untuk sesi %s", session_id)

        links.sort(key=lambda l: l.created_at, reverse=True)

        return links

    # ============================================================
    # cleanup
    # ============================================================

    def release(self, relative_path: str) -> int:
        """Remove CONVERSATION-kind links for a path (e.g. right before
        core.filesystem.FileOperations.delete()/move() acts on it). Never
        touches ARTIFACT/ATTACHMENT-kind ownership - that belongs to their
        own engines' delete() calls."""
        return self.store.delete_by_path(relative_path)


_service_singleton: Optional[WorkspaceIntegrationService] = None
_service_lock = threading.Lock()


def get_workspace_integration_service() -> WorkspaceIntegrationService:
    global _service_singleton
    if _service_singleton is None:
        with _service_lock:
            if _service_singleton is None:
                _service_singleton = WorkspaceIntegrationService()
    return _service_singleton