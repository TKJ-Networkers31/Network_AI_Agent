"""
core/attachments/validator.py - validation for Universal Attachment
(Sprint 2.7 / Wave 1 / Worker 2).

Nothing here raises. AttachmentEngine calls validate_for_create() BEFORE it
touches storage. Batas ukuran hanya berlaku bila MAX_ATTACHMENT_BYTES > 0.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, Callable, Optional

from core.attachments.constants import (
    ALLOWED_EXTENSIONS,
    ALLOWED_MIME_EXTENSIONS,
    BLOCKED_EXTENSIONS,
    EXTENSION_TO_MIME,
    MAX_ATTACHMENT_BYTES,
    MAX_NAME_CHARS,
)
from core.attachments.models import (
    AttachmentSource,
    ValidationIssue,
    ValidationResult,
)

SessionLookup = Callable[[str], bool]


def _default_session_lookup(session_id: str) -> bool:
    from core import chat_sessions as store
    return store.get_session_row(session_id) is not None


def _result(issues: list[ValidationIssue]) -> ValidationResult:
    return ValidationResult(is_valid=not issues, issues=issues)


def _extension_of(name: str) -> str:
    return PurePosixPath(name.replace("\\", "/")).suffix.lower()


def validate_name(name: Any, issues: list[ValidationIssue]) -> Optional[str]:
    """Filename/path safety. Returns the cleaned name, or None if rejected."""
    if not isinstance(name, str) or not name.strip():
        issues.append(ValidationIssue("name", "name wajib diisi (tidak boleh kosong)."))
        return None

    cleaned = name.strip()

    if len(cleaned) > MAX_NAME_CHARS:
        issues.append(ValidationIssue("name", f"name maksimal {MAX_NAME_CHARS} karakter."))
        return None

    if "\x00" in cleaned:
        issues.append(ValidationIssue("name", "name mengandung byte NUL - tidak valid."))
        return None

    normalized = cleaned.replace("\\", "/")

    if "/" in normalized:
        issues.append(ValidationIssue("name", "name tidak boleh berisi path ('/', '\\') - hanya nama file."))
        return None

    if cleaned in (".", ".."):
        issues.append(ValidationIssue("name", "name tidak boleh '.' atau '..'."))
        return None

    return cleaned


def validate_mime_and_extension(
    name: str, mime_type: Any, issues: list[ValidationIssue],
) -> Optional[str]:
    """Cross-checks extension against mime_type. Returns resolved mime or None."""
    extension = _extension_of(name)

    if extension in BLOCKED_EXTENSIONS:
        issues.append(ValidationIssue(
            "name", f"ekstensi '{extension}' tidak diizinkan (file executable/script).",
        ))
        return None

    declared = mime_type.strip().lower() if isinstance(mime_type, str) and mime_type.strip() else None

    if not extension:
        issues.append(ValidationIssue("name", "file tanpa ekstensi tidak diizinkan."))
        return None

    if extension not in ALLOWED_EXTENSIONS:
        issues.append(ValidationIssue(
            "name", f"ekstensi '{extension}' tidak didukung. Pilihan: {sorted(ALLOWED_EXTENSIONS)}.",
        ))
        return None

    if declared is None:
        return EXTENSION_TO_MIME[extension]

    # Browser sering mengirim application/octet-stream untuk ekstensi yang
    # tidak dikenalnya (mis. .rsc, .conf). Ekstensi sudah lolos whitelist,
    # jadi pakai mime hasil inferensi.
    if declared == "application/octet-stream":
        return EXTENSION_TO_MIME[extension]

    if declared not in ALLOWED_MIME_EXTENSIONS:
        issues.append(ValidationIssue(
            "mime_type", f"mime_type '{declared}' tidak didukung. Pilihan: {sorted(ALLOWED_MIME_EXTENSIONS)}.",
        ))
        return None

    if extension not in ALLOWED_MIME_EXTENSIONS[declared]:
        issues.append(ValidationIssue(
            "mime_type",
            f"mime_type '{declared}' tidak cocok dengan ekstensi '{extension}' "
            f"(diharapkan salah satu dari {sorted(ALLOWED_MIME_EXTENSIONS[declared])}).",
        ))
        return None

    return declared


def validate_size(size: Any, issues: list[ValidationIssue]) -> Optional[int]:
    try:
        value = int(size)
    except (TypeError, ValueError):
        issues.append(ValidationIssue("size", "size harus berupa angka (byte)."))
        return None

    if value <= 0:
        issues.append(ValidationIssue("size", "size harus lebih besar dari 0."))
        return None

    # 0 = tanpa batas aplikasi. Batas hanya ada kalau administrator mengaturnya.
    if MAX_ATTACHMENT_BYTES > 0 and value > MAX_ATTACHMENT_BYTES:
        issues.append(ValidationIssue(
            "size",
            f"size ({value} byte) melebihi batas yang dikonfigurasi administrator "
            f"({MAX_ATTACHMENT_BYTES} byte).",
        ))
        return None

    return value


def validate_session(
    session_id: Any,
    issues: list[ValidationIssue],
    session_lookup: Optional[SessionLookup] = None,
) -> Optional[str]:
    if not isinstance(session_id, str) or not session_id.strip():
        issues.append(ValidationIssue("session_id", "session_id wajib diisi (attachment harus terikat sesi)."))
        return None

    lookup = session_lookup or _default_session_lookup

    try:
        exists = lookup(session_id)
    except Exception as exc:
        issues.append(ValidationIssue("session_id", f"gagal memeriksa sesi ({type(exc).__name__})."))
        return None

    if not exists:
        issues.append(ValidationIssue("session_id", f"session '{session_id}' tidak ditemukan."))
        return None

    return session_id


def validate_for_create(
    *,
    name: Any,
    mime_type: Any,
    size: Any,
    session_id: Any,
    source: Any,
    session_lookup: Optional[SessionLookup] = None,
) -> ValidationResult:
    issues: list[ValidationIssue] = []

    validate_name(name, issues)
    if not issues:
        validate_mime_and_extension(name, mime_type, issues)

    validate_size(size, issues)
    validate_session(session_id, issues, session_lookup=session_lookup)

    try:
        AttachmentSource.coerce(source)
    except ValueError as exc:
        issues.append(ValidationIssue("source", str(exc)))

    return _result(issues)