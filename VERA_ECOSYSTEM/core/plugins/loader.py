"""
core/plugins/loader.py — Phase 1.2 Plugin Foundation: Manifest Loader.

Tanggung jawab TUNGGAL:

    file YAML  ->  raw mapping  ->  PluginManifest

Loader hanya MEMBACA dan MEM-PARSE. Ia TIDAK memvalidasi isi manifest
(itu tugas core/plugins/validator.py) dan tidak mengenal lifecycle plugin,
Plugin Manager, registry, capability, atau permission. "Berhasil dimuat"
(`ManifestLoadResult.loaded`) BUKAN berarti "manifest valid": manifest yang
isinya cacat tetap bisa dimuat, lalu ditolak oleh validator.

Kontrak error:
    Semua fungsi publik TIDAK PERNAH raise. Setiap kegagalan (path salah,
    file tidak ada, terlalu besar, bukan UTF-8, YAML rusak, root bukan
    mapping, ...) dikembalikan sebagai `ManifestLoadError` terstruktur di
    `ManifestLoadResult.errors` - lengkap dengan `code` yang stabil supaya
    caller bisa memutuskan tanpa mem-parse teks pesan.

Keamanan:
    - yaml.safe_load saja (tag Python seperti `!!python/object` ditolak).
    - Ukuran file dibatasi (MAX_MANIFEST_BYTES) dan dibaca dengan batas,
      bukan lewat stat() saja, supaya tidak ada celah TOCTOU.
    - Tidak ada import/eksekusi apa pun dari isi manifest (entry_point hanya
      string; meng-import-nya urusan fase berikutnya).

Kenapa `raw` ikut dikembalikan:
    Setelah alignment Phase 1.3, PluginManifest membawa SEMUA field
    spesifikasi dan menjadi representasi kanonik setelah parse berhasil.
    `raw` tetap dikembalikan karena parser (manifest_from_dict) toleran:
    tipe yang salah dibuang menjadi default, sehingga informasi "tipe
    datanya salah" hanya ada di mapping ASLI. Validator butuh `raw` untuk
    mendeteksi input cacat.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Union

import yaml

from core.plugins.manifest import manifest_from_dict
from core.plugins.models import PluginManifest

logger = logging.getLogger("aira.plugins.loader")

# Manifest plugin berupa berkas kecil; 1 MiB sangat longgar dan menahan
# berkas raksasa / YAML "bomb" sebelum sampai ke parser.
MAX_MANIFEST_BYTES = 1024 * 1024

PathLike = Union[str, "os.PathLike[str]"]


# ============================================================ error

class ManifestErrorCode:
    """Kode error stabil (string) - aman dipakai caller untuk percabangan."""

    INVALID_PATH = "invalid_path"
    FILE_NOT_FOUND = "file_not_found"
    NOT_A_FILE = "not_a_file"
    FILE_TOO_LARGE = "file_too_large"
    READ_ERROR = "read_error"
    ENCODING_ERROR = "encoding_error"
    YAML_SYNTAX_ERROR = "yaml_syntax_error"
    YAML_PARSE_ERROR = "yaml_parse_error"
    EMPTY_MANIFEST = "empty_manifest"
    ROOT_NOT_MAPPING = "root_not_mapping"
    UNEXPECTED_ERROR = "unexpected_error"


@dataclass(frozen=True)
class ManifestLoadError:
    """Satu kegagalan pemuatan. line/column 1-based, hanya untuk error sintaks YAML."""

    code: str
    message: str
    source: Optional[str] = None
    line: Optional[int] = None
    column: Optional[int] = None

    def to_dict(self) -> dict:
        data = {"code": self.code, "message": self.message, "source": self.source}

        if self.line is not None:
            data["line"] = self.line
        if self.column is not None:
            data["column"] = self.column

        return data


@dataclass
class ManifestLoadResult:
    """
    Hasil pemuatan.

    source   : path/label sumber (untuk pesan error).
    raw      : mapping hasil parse YAML apa adanya (None kalau gagal dimuat).
    manifest : PluginManifest (representasi kanonik) hasil manifest_from_dict(raw).
               Parser toleran, jadi objek ini bisa berisi default untuk field
               yang cacat - JANGAN dipakai sebagai bukti manifest valid;
               jalankan validator. None kalau gagal dimuat, atau kalau
               pemanggil hanya meminta raw (load_manifest_raw).
    errors   : daftar ManifestLoadError. Kosong == loaded.
    """

    source: Optional[str] = None
    raw: Optional[dict[str, Any]] = None
    manifest: Optional[PluginManifest] = None
    errors: list[ManifestLoadError] = field(default_factory=list)

    @property
    def loaded(self) -> bool:
        """True kalau file berhasil dibaca dan di-parse jadi mapping. BUKAN "valid"."""
        return not self.errors and self.raw is not None

    def to_dict(self) -> dict:
        """JSON-safe. `raw` sengaja tidak disertakan (bentuk bebas, bisa memuat tipe non-JSON)."""
        return {
            "loaded": self.loaded,
            "source": self.source,
            "errors": [e.to_dict() for e in self.errors],
            "manifest": self.manifest.to_dict() if self.manifest is not None else None,
        }


# ============================================================ helper internal

def _error(code: str, message: str, source: Optional[str], **extra: Any) -> ManifestLoadError:
    return ManifestLoadError(code=code, message=message, source=source, **extra)


def _fail(source: Optional[str], code: str, message: str, **extra: Any) -> ManifestLoadResult:
    return ManifestLoadResult(source=source, errors=[_error(code, message, source, **extra)])


def _type_name(value: Any) -> str:
    return type(value).__name__


def _parse_yaml_text(text: str, source: Optional[str]) -> ManifestLoadResult:
    """Teks YAML -> ManifestLoadResult (raw terisi bila sukses; manifest belum dibangun)."""
    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        problem = getattr(exc, "problem", None) or "sintaks YAML tidak valid"
        line = mark.line + 1 if mark is not None else None
        column = mark.column + 1 if mark is not None else None
        where = f" (baris {line}, kolom {column})" if line is not None else ""

        return _fail(
            source, ManifestErrorCode.YAML_SYNTAX_ERROR,
            f"YAML tidak valid{where}: {problem}.",
            line=line, column=column,
        )
    except RecursionError:
        return _fail(
            source, ManifestErrorCode.YAML_PARSE_ERROR,
            "YAML terlalu dalam bersarang untuk diproses.",
        )

    if parsed is None:
        return _fail(
            source, ManifestErrorCode.EMPTY_MANIFEST,
            "File manifest kosong (tidak ada isi YAML).",
        )

    if not isinstance(parsed, dict):
        return _fail(
            source, ManifestErrorCode.ROOT_NOT_MAPPING,
            f"Root manifest harus berupa mapping (key: value), "
            f"bukan {_type_name(parsed)}.",
        )

    return ManifestLoadResult(source=source, raw=parsed)


def _read_text(path: Path, source: str) -> "tuple[Optional[str], Optional[ManifestLoadError]]":
    """Baca file dengan batas ukuran. Return (teks, None) atau (None, error)."""
    try:
        if not path.exists():
            return None, _error(
                ManifestErrorCode.FILE_NOT_FOUND, f"File manifest tidak ditemukan: {source}", source,
            )

        if not path.is_file():
            return None, _error(
                ManifestErrorCode.NOT_A_FILE, f"Path manifest bukan file biasa: {source}", source,
            )

        with open(path, "rb") as handle:
            data = handle.read(MAX_MANIFEST_BYTES + 1)

    except PermissionError:
        return None, _error(
            ManifestErrorCode.READ_ERROR, f"Tidak punya izin membaca file manifest: {source}", source,
        )
    except (OSError, ValueError) as exc:
        return None, _error(
            ManifestErrorCode.READ_ERROR,
            f"Gagal membaca file manifest ({type(exc).__name__}): {source}", source,
        )

    if len(data) > MAX_MANIFEST_BYTES:
        return None, _error(
            ManifestErrorCode.FILE_TOO_LARGE,
            f"File manifest melebihi batas {MAX_MANIFEST_BYTES} byte: {source}", source,
        )

    try:
        # utf-8-sig: BOM (umum di editor Windows) diabaikan, bukan jadi bagian key pertama.
        return data.decode("utf-8-sig"), None
    except UnicodeDecodeError:
        return None, _error(
            ManifestErrorCode.ENCODING_ERROR,
            f"File manifest harus berenkode UTF-8: {source}", source,
        )


def _attach_manifest(result: ManifestLoadResult) -> ManifestLoadResult:
    if result.loaded:
        result.manifest = manifest_from_dict(result.raw)
    return result


# ============================================================ API publik

def load_manifest_text(text: Any, source: Optional[str] = None) -> ManifestLoadResult:
    """
    Teks YAML (di memori) -> ManifestLoadResult lengkap dengan `manifest`.
    Berguna untuk manifest yang tidak berasal dari file. Tidak pernah raise.
    """
    label = source or "<string>"

    try:
        if not isinstance(text, str):
            return _fail(
                label, ManifestErrorCode.INVALID_PATH,
                f"Isi manifest harus berupa string, bukan {_type_name(text)}.",
            )

        return _attach_manifest(_parse_yaml_text(text, label))

    except Exception as exc:  # jaring pengaman terakhir: caller tidak pernah menerima exception
        logger.exception("MANIFEST LOADER | kegagalan tak terduga saat memproses teks.")
        return _fail(label, ManifestErrorCode.UNEXPECTED_ERROR, f"Kegagalan tak terduga: {type(exc).__name__}.")


def load_manifest_raw(path: PathLike) -> ManifestLoadResult:
    """File YAML -> raw mapping SAJA (`manifest` = None). Tidak pernah raise."""
    return _load(path, build_manifest=False)


def load_manifest(path: PathLike) -> ManifestLoadResult:
    """
    File YAML -> raw mapping + PluginManifest. Tidak pernah raise; tidak
    memvalidasi isi (lihat core/plugins/validator.py).
    """
    return _load(path, build_manifest=True)


def _load(path: PathLike, build_manifest: bool) -> ManifestLoadResult:
    source: Optional[str] = None

    try:
        if isinstance(path, (str, os.PathLike)):
            source = os.fspath(path)

        if not isinstance(source, str) or not source.strip():
            return _fail(
                None, ManifestErrorCode.INVALID_PATH,
                f"Path manifest harus string/PathLike tidak kosong, bukan {_type_name(path)}.",
            )

        text, error = _read_text(Path(source), source)

        if error is not None:
            return ManifestLoadResult(source=source, errors=[error])

        result = _parse_yaml_text(text, source)

        return _attach_manifest(result) if build_manifest else result

    except Exception as exc:  # jaring pengaman terakhir
        logger.exception("MANIFEST LOADER | kegagalan tak terduga saat memuat %s.", source)
        return _fail(source, ManifestErrorCode.UNEXPECTED_ERROR, f"Kegagalan tak terduga: {type(exc).__name__}.")


__all__ = [
    "MAX_MANIFEST_BYTES",
    "ManifestErrorCode",
    "ManifestLoadError",
    "ManifestLoadResult",
    "load_manifest",
    "load_manifest_raw",
    "load_manifest_text",
]