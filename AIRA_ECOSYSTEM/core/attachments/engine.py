"""
core/attachments/engine.py - AttachmentEngine (Sprint 2.7 / Wave 1 / W2).

    upload / reference
        -> validate (core/attachments/validator.py)
        -> persist bytes (user_upload) OR reference existing storage
        -> register metadata (core/attachments/store.py)
        -> AttachmentResult (JSON-safe)

Tambahan: create_from_file() - upload dari file sementara di disk, disalin per
chunk (tidak membaca seluruh file ke RAM).
"""
from __future__ import annotations

import logging
import shutil
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

COPY_CHUNK = 1024 * 1024


class AttachmentAccessError(Exception):
    """Dipakai internal untuk pelanggaran kepemilikan sesi."""


def _default_resolve_path(relative_path: str) -> Path:
    from core.filesystem import get_workspace_manager
    return get_workspace_manager().resolve(relative_path)


def _default_workspace_exists(relative_path: str) -> bool:
    from core.filesystem import get_workspace_manager
    return get_workspace_manager().exists(relative_path)


def _default_trash_delete(relative_path: str) -> bool:
    from core.filesystem import FileOperations
    result = FileOperations().delete(relative_path)
    return bool(result.success)


def _publish(event_name: str, **data: Any) -> None:
    try:
        from core.events import event_bus
        event_bus.publish(event_name, source="ATTACHMENTS", agent="ATTACHMENTS", data=data)
    except Exception:
        logger.debug("ATTACHMENTS | gagal publish %s (diabaikan).", event_name, exc_info=True)


class AttachmentEngine:

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
        """Upload dari bytes di memori (file kecil / test)."""
        if not isinstance(content, (bytes, bytearray)):
            return AttachmentResult(False, errors=["content harus berupa bytes."])

        validation = validate_for_create(
            name=name, mime_type=mime_type, size=len(content), session_id=session_id,
            source=AttachmentSource.USER_UPLOAD.value, session_lookup=self._session_lookup,
        )
        if not validation.is_valid:
            return AttachmentResult(False, errors=validation.messages())

        attachment = Attachment(
            session_id=session_id, message_id=message_id, name=name.strip(),
            mime_type=self._resolve_mime(name, mime_type), size=len(content),
            source=AttachmentSource.USER_UPLOAD.value,
            status=AttachmentStatus.PENDING.value,
            metadata=dict(metadata or {}),
        )

        relative_path = f"{self._workspace_subdir}/{attachment.id}{Path(name).suffix}"

        try:
            output_path = self._resolve_path(relative_path)
        except Exception as exc:
            return self._fail(attachment, f"Gagal resolve path penyimpanan: {exc}")

        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(bytes(content))
        except OSError as exc:
            return self._fail(attachment, f"Gagal menyimpan file: {exc}")

        return self._finalize_upload(attachment, relative_path)

    def create_from_file(
        self,
        *,
        temp_path,
        name: str,
        session_id: str,
        mime_type: Optional[str] = None,
        message_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> AttachmentResult:
        """Upload dari file sementara di disk. Disalin per chunk ke Workspace;
        ukuran dibaca dari disk, isi file tidak pernah dimuat penuh ke RAM.
        Pemanggil bertanggung jawab menghapus temp_path."""
        temp_path = Path(temp_path)

        try:
            size = temp_path.stat().st_size
        except OSError as exc:
            return AttachmentResult(False, errors=[f"File sementara tidak terbaca: {exc}"])

        validation = validate_for_create(
            name=name, mime_type=mime_type, size=size, session_id=session_id,
            source=AttachmentSource.USER_UPLOAD.value, session_lookup=self._session_lookup,
        )
        if not validation.is_valid:
            return AttachmentResult(False, errors=validation.messages())

        attachment = Attachment(
            session_id=session_id, message_id=message_id, name=name.strip(),
            mime_type=self._resolve_mime(name, mime_type), size=size,
            source=AttachmentSource.USER_UPLOAD.value,
            status=AttachmentStatus.PENDING.value,
            metadata=dict(metadata or {}),
        )

        relative_path = f"{self._workspace_subdir}/{attachment.id}{Path(name).suffix}"

        try:
            output_path = self._resolve_path(relative_path)
        except Exception as exc:
            return self._fail(attachment, f"Gagal resolve path penyimpanan: {exc}")

        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(temp_path, "rb") as src, open(output_path, "wb") as dst:
                shutil.copyfileobj(src, dst, COPY_CHUNK)
        except OSError as exc:
            try:
                output_path.unlink()
            except OSError:
                pass
            return self._fail(attachment, f"Gagal menyimpan file: {exc}")

        return self._finalize_upload(attachment, relative_path)

    def _finalize_upload(self, attachment: Attachment, relative_path: str) -> AttachmentResult:
        attachment.storage_reference = relative_path
        attachment.status = AttachmentStatus.AVAILABLE.value
        attachment.updated_at = time.time()

        with self._lock:
            self.store.save(attachment)

        logger.info("ATTACHMENT CREATED (upload) | id=%s session=%s path=%s",
                    attachment.id, attachment.session_id, relative_path)
        _publish("attachment.created", id=attachment.id, source=attachment.source,
                 session_id=attachment.session_id)

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
        from core.attachments.constants import EXTENSION_TO_MIME

        extension = Path(name).suffix.lower()

        if isinstance(mime_type, str) and mime_type.strip():
            declared = mime_type.strip().lower()
            if declared != "application/octet-stream":
                return declared

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