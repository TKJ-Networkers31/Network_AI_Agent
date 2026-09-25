"""
core/attachments/engine.py - AttachmentEngine (Sprint 2.7 / Wave 1 / W2).

    upload / reference
        -> validate (core/attachments/validator.py)
        -> persist bytes (user_upload) OR reference existing storage
           (workspace / generated / external) via the EXISTING Workspace
           (core.filesystem.WorkspaceManager - NO second storage system)
        -> register metadata (core/attachments/store.py)
        -> AttachmentResult (JSON-safe)

Mirrors core/artifacts/engine.py's shape deliberately (same Sprint, same
"structured request -> deterministic engine -> stored metadata + existing
storage" contract), but an Attachment differs from an Artifact in one
essential way: an Artifact is ALWAYS AIRA-generated; an Attachment may
point at a file AIRA never touched (a pre-existing workspace file, or an
external URL it never downloads). That's why create_from_workspace() and
create_from_external() never write bytes - they only register a reference.

Storage: path resolution and sandboxing are delegated to
core.filesystem.WorkspaceManager.resolve() (the SAME sandbox FSE/HAL
already enforce), injected lazily so importing this module never touches
disk (same Dependency Injection pattern as core/artifacts/engine.py and
core/selection/builder.py). Bytes for user uploads are written directly at
the resolved path (core.filesystem.FileOperations.write_text() is
text-only; attachments may be binary) - identical reasoning to
core/artifacts/engine.py's own doc comment.

Context boundary: nothing in this module ever returns raw bytes to a
caller that only asked for metadata. Binary content is only touched by
get_content_reference() (an explicit "give me the reference to read/serve
this" call) and even then it returns a path/URL, never the bytes
themselves - reading the bytes is left to the HTTP layer (StreamingResponse)
or whatever explicitly needs them.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

from core.attachments.constants import DEFAULT_WORKSPACE_SUBDIR
from core.attachments.models import (
    Attachment,
    AttachmentResult,
    AttachmentSource,
    AttachmentStatus,
)
from core.attachments.store import AttachmentStore, get_attachment_store
from core.attachments.validator import validate_for_create

logger = logging.getLogger("aira.attachments.engine")


class AttachmentAccessError(Exception):
    """Raised (caught internally, never propagated past AttachmentResult
    call sites that use the *_or_result helpers) when a caller's
    session_id does not own the attachment it's trying to touch."""


def _default_resolve_path(relative_path: str) -> Path:
    """Lazy import - default only. Resolves through the REAL AIRA Workspace
    sandbox; never imported at module load time (see core/artifacts/engine.py
    for the identical pattern)."""
    from core.filesystem import get_workspace_manager
    return get_workspace_manager().resolve(relative_path)


def _default_workspace_exists(relative_path: str) -> bool:
    from core.filesystem import get_workspace_manager
    return get_workspace_manager().exists(relative_path)


def _default_trash_delete(relative_path: str) -> bool:
    """Move a file the engine itself materialized into Trash (never a
    permanent delete) via the EXISTING FileOperations/TrashEngine - see
    core/filesystem/operations.py::FileOperations.delete()."""
    from core.filesystem import FileOperations
    result = FileOperations().delete(relative_path)
    return bool(result.success)


def _publish(event_name: str, **data: Any) -> None:
    """Best-effort publish to the EXISTING Event Bus. Never raises - same
    defensive pattern as core/artifacts/engine.py::_publish."""
    try:
        from core.events import event_bus
        event_bus.publish(event_name, source="ATTACHMENTS", agent="ATTACHMENTS", data=data)
    except Exception:
        logger.debug("ATTACHMENTS | gagal publish %s (diabaikan).", event_name, exc_info=True)


class AttachmentEngine:
    """
    Dependency Injection: `store`, `resolve_path`, `workspace_exists`, and
    `trash_delete` can all be swapped - tests inject a temp AttachmentStore
    + a temp-dir resolver so no real Workspace or database/attachments.db
    is ever touched (same approach as core/artifacts/tests/test_engine.py).
    """

    def __init__(
        self,
        store: Optional[AttachmentStore] = None,
        resolve_path: Optional[Callable[[str], Path]] = None,
        workspace_exists: Optional[Callable[[str], bool]] = None,
        trash_delete: Optional[Callable[[str], bool]] = None,
        session_lookup: Optional[Callable[[str], bool]] = None,
        workspace_subdir: str = DEFAULT_WORKSPACE_SUBDIR,
    ):
        self._store = store
        self._resolve_path = resolve_path or _default_resolve_path
        self._workspace_exists = workspace_exists or _default_workspace_exists
        self._trash_delete = trash_delete or _default_trash_delete
        self._session_lookup = session_lookup
        self._workspace_subdir = workspace_subdir.strip("/\\") or DEFAULT_WORKSPACE_SUBDIR
        self._lock = threading.Lock()

    @property
    def store(self) -> AttachmentStore:
        return self._store or get_attachment_store()

    # ============================================================ CREATE

    def create_from_upload(
        self,
        *,
        content: bytes,
        name: str,
        session_id: str,
        mime_type: Optional[str] = None,
        message_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> AttachmentResult:
        """User-uploaded file: bytes are written into the AIRA Workspace
        (under Attachments/<id><ext>) and the attachment owns that copy -
        deleting the attachment later moves that copy to Trash."""
        if not isinstance(content, (bytes, bytearray)):
            return AttachmentResult(False, errors=["content harus berupa bytes."])

        validation = validate_for_create(
            name=name, mime_type=mime_type, size=len(content), session_id=session_id,
            source=AttachmentSource.USER_UPLOAD.value, session_lookup=self._session_lookup,
        )
        if not validation.is_valid:
            return AttachmentResult(False, errors=validation.messages())

        resolved_mime = self._resolve_mime(name, mime_type)

        attachment = Attachment(
            session_id=session_id, message_id=message_id, name=name.strip(),
            mime_type=resolved_mime, size=len(content),
            source=AttachmentSource.USER_UPLOAD.value,
            status=AttachmentStatus.PENDING.value,
            metadata=dict(metadata or {}),
        )

        extension = Path(name).suffix
        relative_path = f"{self._workspace_subdir}/{attachment.id}{extension}"

        try:
            output_path = self._resolve_path(relative_path)
        except Exception as exc:
            return self._fail(attachment, f"Gagal resolve path penyimpanan: {exc}")

        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(bytes(content))
        except OSError as exc:
            return self._fail(attachment, f"Gagal menyimpan file: {exc}")

        attachment.storage_reference = relative_path
        attachment.status = AttachmentStatus.AVAILABLE.value
        attachment.updated_at = time.time()

        with self._lock:
            self.store.save(attachment)

        logger.info("ATTACHMENT CREATED (upload) | id=%s session=%s path=%s",
                    attachment.id, session_id, relative_path)
        _publish("attachment.created", id=attachment.id, source=attachment.source, session_id=session_id)

        return AttachmentResult(True, attachment=attachment)

    def create_from_workspace(
        self,
        *,
        relative_path: str,
        session_id: str,
        message_id: Optional[str] = None,
        name: Optional[str] = None,
        mime_type: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> AttachmentResult:
        """Reference a file that already exists in the Workspace - no bytes
        are copied or moved. Deleting this attachment never touches the
        original file (it isn't the attachment's own copy)."""
        relative_path = (relative_path or "").strip()

        if not relative_path:
            return AttachmentResult(False, errors=["relative_path wajib diisi."])

        resolved_name = name or Path(relative_path).name

        try:
            exists = self._workspace_exists(relative_path)
        except Exception as exc:
            return AttachmentResult(False, errors=[f"Gagal memeriksa workspace: {exc}"])

        if not exists:
            return AttachmentResult(False, errors=[f"File workspace '{relative_path}' tidak ditemukan."])

        try:
            absolute = self._resolve_path(relative_path)
            size = absolute.stat().st_size
        except Exception as exc:
            return AttachmentResult(False, errors=[f"Gagal membaca metadata file: {exc}"])

        validation = validate_for_create(
            name=resolved_name, mime_type=mime_type, size=size, session_id=session_id,
            source=AttachmentSource.WORKSPACE.value, session_lookup=self._session_lookup,
        )
        if not validation.is_valid:
            return AttachmentResult(False, errors=validation.messages())

        attachment = Attachment(
            session_id=session_id, message_id=message_id, name=resolved_name.strip(),
            mime_type=self._resolve_mime(resolved_name, mime_type), size=size,
            storage_reference=relative_path,
            source=AttachmentSource.WORKSPACE.value,
            status=AttachmentStatus.AVAILABLE.value,
            metadata=dict(metadata or {}),
        )

        with self._lock:
            self.store.save(attachment)

        logger.info("ATTACHMENT CREATED (workspace ref) | id=%s session=%s path=%s",
                    attachment.id, session_id, relative_path)
        _publish("attachment.created", id=attachment.id, source=attachment.source, session_id=session_id)

        return AttachmentResult(True, attachment=attachment)

    def create_from_artifact(
        self,
        *,
        artifact,
        session_id: str,
        message_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> AttachmentResult:
        """Wrap an AIRA-generated file (core.artifacts.models.Artifact) as
        an attachment - references the artifact's own storage_reference,
        never duplicates it. `artifact` duck-types Artifact (id, name,
        mime_type, size, storage_reference) so this stays decoupled from a
        hard import of core.artifacts at module load time."""
        storage_reference = getattr(artifact, "storage_reference", None)

        if not storage_reference:
            return AttachmentResult(False, errors=["artifact belum punya storage_reference (belum ready)."])

        name = getattr(artifact, "name", None) or Path(storage_reference).name
        mime_type = getattr(artifact, "mime_type", None)
        size = getattr(artifact, "size", 0) or 0

        validation = validate_for_create(
            name=name, mime_type=mime_type, size=max(size, 1), session_id=session_id,
            source=AttachmentSource.GENERATED.value, session_lookup=self._session_lookup,
        )
        if not validation.is_valid:
            return AttachmentResult(False, errors=validation.messages())

        attachment = Attachment(
            session_id=session_id, message_id=message_id, name=name,
            mime_type=mime_type or "application/octet-stream", size=size,
            storage_reference=storage_reference,
            source=AttachmentSource.GENERATED.value,
            status=AttachmentStatus.AVAILABLE.value,
            metadata={**(metadata or {}), "artifact_id": getattr(artifact, "id", None)},
        )

        with self._lock:
            self.store.save(attachment)

        logger.info("ATTACHMENT CREATED (generated) | id=%s session=%s artifact_id=%s",
                    attachment.id, session_id, attachment.metadata.get("artifact_id"))
        _publish("attachment.created", id=attachment.id, source=attachment.source, session_id=session_id)

        return AttachmentResult(True, attachment=attachment)

    def create_external(
        self,
        *,
        url: str,
        name: str,
        session_id: str,
        mime_type: Optional[str] = None,
        message_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> AttachmentResult:
        """Reference a file outside AIRA's storage entirely (a URL). AIRA
        never fetches the bytes here - only the reference is recorded, kept
        in metadata['url']. size is unknown up front (0) unless the caller
        supplies it in metadata."""
        url = (url or "").strip()

        if not url:
            return AttachmentResult(False, errors=["url wajib diisi."])

        if not (url.startswith("http://") or url.startswith("https://")):
            return AttachmentResult(False, errors=["url harus dimulai dengan http:// atau https://."])

        declared_size = (metadata or {}).get("size", 1)

        validation = validate_for_create(
            name=name, mime_type=mime_type, size=max(int(declared_size or 1), 1),
            session_id=session_id, source=AttachmentSource.EXTERNAL.value,
            session_lookup=self._session_lookup,
        )
        if not validation.is_valid:
            return AttachmentResult(False, errors=validation.messages())

        attachment = Attachment(
            session_id=session_id, message_id=message_id, name=name.strip(),
            mime_type=self._resolve_mime(name, mime_type),
            size=int((metadata or {}).get("size") or 0),
            storage_reference=None,
            source=AttachmentSource.EXTERNAL.value,
            status=AttachmentStatus.AVAILABLE.value,
            metadata={**(metadata or {}), "url": url},
        )

        with self._lock:
            self.store.save(attachment)

        logger.info("ATTACHMENT CREATED (external ref) | id=%s session=%s", attachment.id, session_id)
        _publish("attachment.created", id=attachment.id, source=attachment.source, session_id=session_id)

        return AttachmentResult(True, attachment=attachment)

    # ============================================================== READ

    def get(self, attachment_id: str, *, session_id: Optional[str] = None) -> Optional[Attachment]:
        """Metadata only. Enforces ownership when session_id is given -
        an attachment belonging to another session is treated as not
        found, never leaked as "exists but forbidden"."""
        attachment = self.store.get(attachment_id)

        if attachment is None or attachment.is_deleted:
            return None

        if session_id is not None and not attachment.owned_by_session(session_id):
            return None

        return attachment

    def list(
        self,
        *,
        session_id: Optional[str] = None,
        message_id: Optional[str] = None,
        status: Optional[str] = None,
        source: Optional[str] = None,
    ) -> list[Attachment]:
        return self.store.list(session_id=session_id, message_id=message_id, status=status, source=source)

    def get_content_reference(
        self, attachment_id: str, *, session_id: Optional[str] = None,
    ) -> Optional[dict]:
        """Explicit "I need to actually read/serve this file" call - the
        ONLY place this module hands back something that lets a caller
        reach binary content. Even here it returns a REFERENCE (an
        absolute path or an external URL), never the bytes themselves;
        Context must never receive this, only metadata (see module
        docstring's Context boundary section)."""
        attachment = self.get(attachment_id, session_id=session_id)

        if attachment is None or not attachment.is_available:
            return None

        if attachment.source == AttachmentSource.EXTERNAL.value:
            return {"kind": "external_url", "url": attachment.metadata.get("url")}

        if not attachment.storage_reference:
            return None

        try:
            absolute = self._resolve_path(attachment.storage_reference)
        except Exception:
            logger.exception("ATTACHMENTS | gagal resolve path untuk %s", attachment_id)
            return None

        return {
            "kind": "workspace_path",
            "relative_path": attachment.storage_reference,
            "absolute_path": str(absolute),
            "mime_type": attachment.mime_type,
        }

    # ------------------------------------------------------------- update

    def associate_with_message(
        self, attachment_id: str, message_id: str, *, session_id: Optional[str] = None,
    ) -> AttachmentResult:
        attachment = self.get(attachment_id, session_id=session_id)

        if attachment is None:
            return AttachmentResult(False, errors=[f"Attachment '{attachment_id}' tidak ditemukan."])

        attachment.message_id = message_id
        attachment.updated_at = time.time()

        with self._lock:
            self.store.save(attachment)

        _publish("attachment.associated", id=attachment.id, message_id=message_id)

        return AttachmentResult(True, attachment=attachment)

    def mark_failed(self, attachment_id: str, error: str) -> AttachmentResult:
        attachment = self.store.get(attachment_id)

        if attachment is None:
            return AttachmentResult(False, errors=[f"Attachment '{attachment_id}' tidak ditemukan."])

        return self._fail(attachment, error)

    # ------------------------------------------------------------- delete

    def delete(self, attachment_id: str, *, session_id: Optional[str] = None) -> AttachmentResult:
        """Soft delete: status -> 'deleted'. The underlying file is only
        moved to Trash (never permanently destroyed here) when the
        attachment materialized its OWN copy (source == user_upload) -
        workspace/generated/external attachments only ever reference
        storage they don't own, so their files are left untouched."""
        attachment = self.get(attachment_id, session_id=session_id)

        if attachment is None:
            return AttachmentResult(False, errors=[f"Attachment '{attachment_id}' tidak ditemukan."])

        if attachment.source == AttachmentSource.USER_UPLOAD.value and attachment.storage_reference:
            try:
                self._trash_delete(attachment.storage_reference)
            except Exception:
                logger.exception("ATTACHMENTS | gagal memindahkan file ke trash untuk %s", attachment_id)

        attachment.status = AttachmentStatus.DELETED.value
        attachment.updated_at = time.time()

        with self._lock:
            self.store.save(attachment)

        logger.info("ATTACHMENT DELETED | id=%s session=%s", attachment_id, attachment.session_id)
        _publish("attachment.deleted", id=attachment_id, session_id=attachment.session_id)

        return AttachmentResult(True, attachment=attachment)

    # ------------------------------------------------------------ internal

    def _fail(self, attachment: Attachment, message: str) -> AttachmentResult:
        attachment.status = AttachmentStatus.FAILED.value
        attachment.updated_at = time.time()
        attachment.metadata = {**attachment.metadata, "error": message}

        with self._lock:
            self.store.save(attachment)

        logger.warning("ATTACHMENT FAILED | id=%s error=%s", attachment.id, message)
        _publish("attachment.failed", id=attachment.id, error=message)

        return AttachmentResult(False, attachment=attachment, errors=[message])

    @staticmethod
    def _resolve_mime(name: str, mime_type: Optional[str]) -> str:
        if isinstance(mime_type, str) and mime_type.strip():
            return mime_type.strip().lower()

        from core.attachments.constants import EXTENSION_TO_MIME
        extension = Path(name).suffix.lower()
        return EXTENSION_TO_MIME.get(extension, "application/octet-stream")


_engine_singleton: Optional[AttachmentEngine] = None
_engine_lock = threading.Lock()


def get_attachment_engine() -> AttachmentEngine:
    global _engine_singleton
    if _engine_singleton is None:
        with _engine_lock:
            if _engine_singleton is None:
                _engine_singleton = AttachmentEngine()
    return _engine_singleton
