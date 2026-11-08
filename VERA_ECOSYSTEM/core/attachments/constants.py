"""
core/attachments/constants.py - Universal Attachment vocabulary
(Sprint 2.7 / Wave 1 / Worker 2).

Hanya format yang BENAR-BENAR bisa diproses core/file_processing yang boleh
masuk whitelist ini.
"""

from __future__ import annotations

import os

DEFAULT_WORKSPACE_SUBDIR = "Attachments"

# 0 = tanpa batas level aplikasi. >0 = batas opsional dari administrator.
# (Batas disk/RAM/reverse proxy di luar aplikasi tetap berlaku.)
MAX_ATTACHMENT_BYTES = int(os.getenv("AIRA_MAX_ATTACHMENT_BYTES", "0") or 0)

MAX_NAME_CHARS = 255

# Urutan penting: EXTENSION_TO_MIME memakai entri TERAKHIR per ekstensi, jadi
# alias browser ditaruh SEBELUM tipe kanonik.
ALLOWED_MIME_EXTENSIONS: dict[str, frozenset[str]] = {
    # images
    "image/png": frozenset({".png"}),
    "image/jpeg": frozenset({".jpg", ".jpeg"}),
    "image/gif": frozenset({".gif"}),
    "image/webp": frozenset({".webp"}),
    "image/svg+xml": frozenset({".svg"}),
    "image/bmp": frozenset({".bmp"}),
    "image/tiff": frozenset({".tif", ".tiff"}),
    # documents
    "application/pdf": frozenset({".pdf"}),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": frozenset({".docx"}),
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": frozenset({".xlsx"}),
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": frozenset({".pptx"}),
    # text / config
    "text/markdown": frozenset({".md"}),
    "text/tab-separated-values": frozenset({".tsv"}),
    "application/xml": frozenset({".xml"}),
    "text/html": frozenset({".html"}),
    "application/vnd.ms-excel": frozenset({".csv"}),  # Windows mengirim ini untuk .csv
    "text/csv": frozenset({".csv"}),
    "text/plain": frozenset({".txt", ".log", ".rsc", ".conf", ".cfg", ".ini"}),
    "application/json": frozenset({".json"}),
    "application/yaml": frozenset({".yaml", ".yml"}),
    "text/yaml": frozenset({".yaml", ".yml"}),
    # archive (alias browser dulu, kanonik terakhir)
    "application/x-zip-compressed": frozenset({".zip"}),
    "application/zip": frozenset({".zip"}),
    "application/x-gzip": frozenset({".gz", ".tgz"}),
    "application/gzip": frozenset({".gz", ".tgz"}),
    "application/x-tar": frozenset({".tar"}),
    "application/x-bzip2": frozenset({".bz2", ".tbz2"}),
    "application/x-xz": frozenset({".xz", ".txz"}),
}

EXTENSION_TO_MIME: dict[str, str] = {
    ext: mime
    for mime, extensions in ALLOWED_MIME_EXTENSIONS.items()
    for ext in extensions
}

ALLOWED_EXTENSIONS: frozenset[str] = frozenset(EXTENSION_TO_MIME.keys())
ALLOWED_MIME_TYPES: frozenset[str] = frozenset(ALLOWED_MIME_EXTENSIONS.keys())

# Tidak pernah diterima apa pun mime-nya. Isi archive yang berekstensi ini
# diperlakukan sebagai DATA oleh file_processing (tidak pernah dieksekusi).
BLOCKED_EXTENSIONS: frozenset[str] = frozenset({
    ".exe", ".bat", ".cmd", ".com", ".sh", ".ps1", ".msi", ".dll",
    ".so", ".dylib", ".apk", ".app", ".scr", ".vbs", ".js", ".jar",
})