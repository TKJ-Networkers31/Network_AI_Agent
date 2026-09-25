"""
core/attachments/constants.py - Universal Attachment vocabulary
(Sprint 2.7 / Wave 1 / Worker 2).

Single source of truth for what an attachment is allowed to be: size
limits, and the MIME-type / extension allowlist used by
core/attachments/validator.py. Kept separate from models.py so callers
that only need the vocabulary (not the dataclasses) can import lightly -
the same split already used by core/capability (constants.py vs models.py)
and core/dio (constants.py vs models.py).
"""

from __future__ import annotations

# Default workspace subfolder attachments are materialized into (mirrors
# core/artifacts/engine.py::DEFAULT_WORKSPACE_SUBDIR - a sibling folder,
# not a new storage root).
DEFAULT_WORKSPACE_SUBDIR = "Attachments"

# Hard ceiling on any single attachment. Generous enough for documents/
# images, small enough that one upload can't exhaust disk in the sandbox.
MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024  # 25 MiB

# name/path safety
MAX_NAME_CHARS = 255

# mime_type (lowercased) -> set of accepted extensions (lowercased, with
# leading dot). Used both to validate an explicit mime_type and to infer
# one from an extension when the caller doesn't supply mime_type.
ALLOWED_MIME_EXTENSIONS: dict[str, frozenset[str]] = {
    # images
    "image/png": frozenset({".png"}),
    "image/jpeg": frozenset({".jpg", ".jpeg"}),
    "image/gif": frozenset({".gif"}),
    "image/webp": frozenset({".webp"}),
    "image/svg+xml": frozenset({".svg"}),
    # documents
    "application/pdf": frozenset({".pdf"}),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": frozenset({".docx"}),
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": frozenset({".xlsx"}),
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": frozenset({".pptx"}),
    "text/markdown": frozenset({".md"}),
    "text/plain": frozenset({".txt", ".log"}),
    "text/csv": frozenset({".csv"}),
    "application/json": frozenset({".json"}),
    "application/yaml": frozenset({".yaml", ".yml"}),
    "text/yaml": frozenset({".yaml", ".yml"}),
}

# Reverse index: extension -> mime_type, built once at import time. Ties
# (an extension shared by two mime types, e.g. none currently) keep the
# LAST entry above - none exist today, kept deterministic regardless.
EXTENSION_TO_MIME: dict[str, str] = {
    ext: mime
    for mime, extensions in ALLOWED_MIME_EXTENSIONS.items()
    for ext in extensions
}

ALLOWED_EXTENSIONS: frozenset[str] = frozenset(EXTENSION_TO_MIME.keys())
ALLOWED_MIME_TYPES: frozenset[str] = frozenset(ALLOWED_MIME_EXTENSIONS.keys())

# Extensions never accepted regardless of declared mime_type - executable/
# script content has no legitimate reason to arrive as a chat attachment.
BLOCKED_EXTENSIONS: frozenset[str] = frozenset({
    ".exe", ".bat", ".cmd", ".com", ".sh", ".ps1", ".msi", ".dll",
    ".so", ".dylib", ".apk", ".app", ".scr", ".vbs", ".js", ".jar",
})
