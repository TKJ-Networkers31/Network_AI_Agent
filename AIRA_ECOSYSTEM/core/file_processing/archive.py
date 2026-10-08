"""
core/file_processing/archive.py - ekstraksi archive AMAN
(ZIP / TAR / TGZ / GZ / BZ2 / XZ).

Tidak ada batas ukuran file/upload. Yang ada hanya proteksi resource:
  - Zip Slip / path traversal / path absolut: setiap nama entry divalidasi,
    hasil resolve wajib di dalam direktori ekstraksi; tidak pernah extractall().
  - symlink/hardlink/device/fifo TIDAK diekstrak (security_blocked).
  - ukuran diukur dari byte NYATA yang ditulis (header archive tidak dipercaya).
  - decompression bomb: rasio ekspansi (berlaku setelah expansion_floor byte)
    + cek sisa disk di tiap chunk.
  - jumlah entry dan kedalaman archive bersarang dibatasi.
File hasil ekstraksi diperlakukan sebagai DATA; tidak pernah dieksekusi.
"""
from __future__ import annotations

import bz2
import gzip
import lzma
import os
import re
import shutil
import tarfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from core.file_processing.models import E_CORRUPTED, E_EXTRACTION, E_RESOURCE, E_SECURITY

CHUNK = 1024 * 1024
ZIP_EXT = (".zip",)
TAR_EXT = (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz")
SINGLE_OPENERS = {".gz": gzip.open, ".bz2": bz2.open, ".xz": lzma.open}


@dataclass
class ArchiveLimits:
    max_entries: int = int(os.getenv("AIRA_ARCHIVE_MAX_ENTRIES", "100000"))
    max_ratio: float = float(os.getenv("AIRA_ARCHIVE_MAX_RATIO", "1000"))
    expansion_floor: int = int(os.getenv("AIRA_ARCHIVE_EXPANSION_FLOOR", str(512 * 1024 * 1024)))
    disk_margin: int = int(os.getenv("AIRA_ARCHIVE_DISK_MARGIN", str(64 * 1024 * 1024)))
    max_depth: int = int(os.getenv("AIRA_ARCHIVE_MAX_DEPTH", "3"))


@dataclass
class ArchiveReport:
    entries: list = field(default_factory=list)   # [{"path": rel, "abs": Path, "size": int}]
    errors: list = field(default_factory=list)    # [(code, message, path)]
    fatal: bool = False


class _Stop(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


def archive_kind(name: str):
    n = name.lower()
    if n.endswith(ZIP_EXT):
        return "zip"
    if n.endswith(TAR_EXT):
        return "tar"
    if n.endswith(tuple(SINGLE_OPENERS)):
        return "single"
    return None


def safe_target(root: Path, name: str) -> Path:
    raw = name.replace("\\", "/")
    if "\x00" in raw or raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
        raise ValueError("path absolut/tidak valid")
    parts = [p for p in raw.split("/") if p not in ("", ".")]
    if not parts or ".." in parts:
        raise ValueError("path traversal")
    root = root.resolve()
    target = root.joinpath(*parts).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise ValueError("keluar dari direktori ekstraksi")
    return target


class _Budget:
    def __init__(self, dest: Path, compressed: int, limits: ArchiveLimits):
        self.dest, self.compressed, self.limits, self.total = dest, max(compressed, 1), limits, 0

    def copy(self, src, target: Path):
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            n = 1
            while target.with_name(f"{target.stem}__dup{n}{target.suffix}").exists():
                n += 1
            target = target.with_name(f"{target.stem}__dup{n}{target.suffix}")
        written = 0
        with open(target, "wb") as out:
            while True:
                chunk = src.read(CHUNK)
                if not chunk:
                    break
                out.write(chunk)
                written += len(chunk)
                self.total += len(chunk)
                if self.total > self.limits.expansion_floor and self.total > self.limits.max_ratio * self.compressed:
                    raise _Stop(E_RESOURCE, "Rasio ekspansi archive melewati batas aman (kemungkinan decompression bomb).")
                if shutil.disk_usage(self.dest).free < self.limits.disk_margin:
                    raise _Stop(E_RESOURCE, "Ruang disk tidak cukup untuk melanjutkan ekstraksi.")
        return written, target


def extract_archive(path: Path, dest: Path, limits: ArchiveLimits = None) -> ArchiveReport:
    limits = limits or ArchiveLimits()
    path, dest = Path(path), Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    report = ArchiveReport()
    budget = _Budget(dest, path.stat().st_size, limits)
    kind = archive_kind(path.name)

    try:
        if kind == "zip":
            _zip(path, dest, budget, report, limits)
        elif kind == "tar" or (kind == "single" and tarfile.is_tarfile(path)):
            _tar(path, dest, budget, report, limits)
        elif kind == "single":
            _single(path, dest, budget, report)
        else:
            raise _Stop(E_EXTRACTION, "Format archive tidak dikenali.")
    except _Stop as stop:
        report.errors.append((stop.code, stop.message, path.name))
        report.fatal = True
    except (zipfile.BadZipFile, tarfile.TarError, EOFError, gzip.BadGzipFile,
            lzma.LZMAError, OSError, ValueError) as exc:
        report.errors.append((E_CORRUPTED, f"Archive rusak atau tidak bisa dibaca: {type(exc).__name__}: {exc}", path.name))
        report.fatal = True
    return report


def _add(report, rel, target, size):
    report.entries.append({"path": rel, "abs": target, "size": size})


def _guard_count(report, limits):
    if len(report.entries) >= limits.max_entries:
        raise _Stop(E_RESOURCE, f"Jumlah entry archive melewati batas aman ({limits.max_entries}).")


def _zip(path, dest, budget, report, limits):
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            name = info.filename
            try:
                target = safe_target(dest, name)
            except ValueError as exc:
                report.errors.append((E_SECURITY, f"Entry ditolak ({exc}): {name!r}", name))
                continue
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                report.errors.append((E_SECURITY, f"Symlink tidak diekstrak: {name!r}", name))
                continue
            if info.flag_bits & 0x1:
                report.errors.append((E_EXTRACTION, f"Entry terenkripsi, tidak bisa dibaca: {name!r}", name))
                continue
            _guard_count(report, limits)
            try:
                with zf.open(info) as src:
                    size, real = budget.copy(src, target)
                _add(report, str(real.relative_to(dest.resolve())), real, size)
            except _Stop:
                raise
            except (zipfile.BadZipFile, EOFError, OSError, RuntimeError, NotImplementedError) as exc:
                report.errors.append((E_EXTRACTION, f"Gagal mengekstrak {name!r}: {type(exc).__name__}: {exc}", name))


def _tar(path, dest, budget, report, limits):
    with tarfile.open(path, "r|*") as tf:
        for m in tf:
            try:
                target = safe_target(dest, m.name)
            except ValueError as exc:
                report.errors.append((E_SECURITY, f"Entry ditolak ({exc}): {m.name!r}", m.name))
                continue
            if m.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif m.isreg():
                _guard_count(report, limits)
                src = tf.extractfile(m)
                size, real = budget.copy(src, target)
                _add(report, str(real.relative_to(dest.resolve())), real, size)
            else:
                report.errors.append((E_SECURITY, f"Entry bukan file biasa (link/device) tidak diekstrak: {m.name!r}", m.name))


def _single(path, dest, budget, report):
    """File tunggal terkompresi: .gz / .bz2 / .xz."""
    suffix = path.suffix.lower()
    inner = path.name[: -len(suffix)] or "data"
    target = safe_target(dest, inner)
    with SINGLE_OPENERS[suffix](path, "rb") as src:
        size, real = budget.copy(src, target)
    _add(report, str(real.relative_to(dest.resolve())), real, size)