"""
core/plugins/validator.py — Phase 1.2 Plugin Foundation: Manifest Validator.

Tanggung jawab TUNGGAL:

    manifest  ->  PluginValidationResult (is_valid + daftar PluginValidationIssue)

Validator murni: tanpa I/O, tanpa membaca file (itu tugas loader.py), tanpa
Event Bus, tanpa import dari agents/api/tools, dan tanpa efek samping.
Hanya PERIKSA - tidak memuat, meng-enable, atau mendaftarkan plugin, dan
tidak memeriksa apakah dependency/capability/permission benar-benar ada
(itu tugas Plugin Manager / Capability Registry / Permission System di fase
berikutnya). Yang divalidasi di sini adalah BENTUK dan TIPE data.

DUA PINTU MASUK (aturan skemanya SAMA; hanya bentuk inputnya yang berbeda)
---------------------------------------------------------------------------
Sejak alignment Phase 1.3, PluginManifest membawa SEMUA field spesifikasi
(termasuk api_version, capabilities, permissions), sehingga jalur objek
memeriksa skema yang sama dengan jalur raw. Jalur raw tetap ada karena
tugasnya berbeda:

1. validate_manifest_data(mapping)
   Memvalidasi raw mapping hasil loader (ManifestLoadResult.raw). Jalur
   inilah yang mendeteksi INPUT CACAT, karena manifest_from_dict() bersifat
   toleran: tipe yang salah dibuang jadi default (mis. `version: 1.0` -> "";
   item dependency cacat -> hilang; `optional: "false"` -> False), sehingga
   informasi "tipe data salah" sudah hilang begitu menjadi objek. Untuk
   manifest yang baru dibaca dari file, gunakan jalur ini.

2. validate_plugin_manifest(PluginManifest)
   Memvalidasi representasi kanonik. Cocok untuk objek yang sudah ada/dibuat
   di kode. Batasan yang tetap berlaku: sebuah objek tidak dapat
   membedakan "field tidak diisi" dari "diisi dengan nilai kosong" untuk
   api_version - keduanya ("") dianggap TIDAK DIDEKLARASIKAN, sehingga
   dilaporkan sebagai field wajib yang hilang.

Skema (field -> aturan). "wajib" = REQUIRED_FIELDS:
    id            wajib   string; format validate_plugin_id (Phase 1.1)
    name          wajib   string tidak kosong
    version       wajib   string; semver validate_version (Phase 1.1)
    author        wajib   mapping {name (wajib), email?, url?}
    api_version   wajib   string "MAJOR", "MAJOR.MINOR", atau "MAJOR.MINOR.PATCH"
    description   opsional string (boleh kosong)
    entry_point   opsional string "paket.modul:NamaClass" (tidak di-import)
    category      opsional string tidak kosong
    tags          opsional list string tidak kosong
    compatibility opsional mapping {min_aira_version?, max_aira_version?, platforms?}
    capabilities  opsional list string identifier deklarasi, tanpa duplikat
    permissions   opsional list string identifier deklarasi, tanpa duplikat
    dependencies  opsional list; item = string id ATAU mapping
                  {id (wajib), version_constraint?, optional?}

Nilai `null` (mis. "description:" kosong di YAML) diperlakukan sebagai
field TIDAK DIISI.

Tata bahasa version_constraint (bebas didefinisikan di Phase 1; parsing/
evaluasi range sebenarnya adalah urusan resolver dependency nanti):
    constraint := "*" | clause ("," clause)*
    clause     := [op] versi           op ∈ >= <= > < == != ~= ^ ~
    versi      := MAJOR[.MINOR[.PATCH]][-prerelease][+build]
    (tanpa op = versi persis)

Nama field pada PluginValidationIssue mengikuti gaya Phase 1.1:
"id", "author.name", "dependencies[0].id", "compatibility.platforms[1]".
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any, Optional, Union
from urllib.parse import urlparse

from core.plugins.models import (
    PluginManifest,
    PluginValidationIssue,
    PluginValidationResult,
    VERSION_RE,
    validate_plugin_id,
    validate_version,
)

logger = logging.getLogger("aira.plugins.validator")

# ============================================================ skema

REQUIRED_FIELDS: tuple[str, ...] = ("id", "name", "version", "author", "api_version")

# Jalur objek kini memakai daftar wajib yang sama: PluginManifest membawa
# semua field spesifikasi. Nama ini dipertahankan agar import lama tetap jalan.
OBJECT_REQUIRED_FIELDS: tuple[str, ...] = REQUIRED_FIELDS

KNOWN_FIELDS: tuple[str, ...] = (
    "id", "name", "version", "description", "author", "entry_point", "category",
    "tags", "api_version", "compatibility", "capabilities", "permissions",
    "dependencies",
)

# Sama dengan yang disebut di core/plugins/models.py::PluginCompatibility.
KNOWN_PLATFORMS: frozenset[str] = frozenset({"windows", "linux"})

_AUTHOR_FIELDS = ("name", "email", "url")
_COMPATIBILITY_FIELDS = ("min_aira_version", "max_aira_version", "platforms")
_DEPENDENCY_FIELDS = ("id", "version_constraint", "optional")

API_VERSION_RE = re.compile(r"^\d+(?:\.\d+){0,2}$")
ENTRY_POINT_RE = re.compile(r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*$")
DECLARATION_ID_RE = re.compile(r"^[a-z][a-z0-9_-]*(?:[.:][a-z0-9][a-z0-9_-]*)*$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_CLAUSE_RE = re.compile(
    r"^(?:(>=|<=|==|!=|~=|>|<|\^|~)\s*)?"
    r"(\d+(?:\.\d+){0,2}(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?)$"
)


def validate_version_constraint(value: Any) -> Optional[str]:
    """Return pesan error, atau None kalau valid. Lihat tata bahasa di docstring modul."""
    if not isinstance(value, str) or not value.strip():
        return "version_constraint harus string tidak kosong, mis. '>=1.0.0,<2.0.0'."

    text = value.strip()

    if text == "*":
        return None

    for clause in text.split(","):
        clause = clause.strip()

        if not clause or not _CLAUSE_RE.match(clause):
            return (
                f"version_constraint tidak valid pada bagian '{clause}'. Contoh yang benar: "
                "'>=1.0.0', '^1.2', '~=1.4.0', '>=1.0.0,<2.0.0', atau '*'."
            )

    return None


# ============================================================ collector + helper

class _Issues:

    def __init__(self) -> None:
        self.items: list[PluginValidationIssue] = []

    def add(self, field: str, message: str) -> None:
        self.items.append(PluginValidationIssue(field, message))


def _label(value: Any) -> str:
    """Nama tipe yang enak dibaca untuk pesan error."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "string"
    if isinstance(value, Mapping):
        return "mapping"
    if isinstance(value, (list, tuple)):
        return "list"
    return type(value).__name__


def _quote_hint(value: Any) -> str:
    # `version: 1.0` di YAML jadi float; pengguna hampir selalu bermaksud string.
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return " Tulis dengan tanda kutip (mis. \"1.0.0\") agar dibaca sebagai teks."
    return ""


def _string(
    container: Mapping, key: str, path: str, issues: _Issues,
    *, required: bool = False, allow_empty: bool = False,
) -> Optional[str]:
    """Ambil field string. Return nilainya kalau valid, selain itu None (+ issue bila perlu)."""
    value = container.get(key)

    if value is None:
        if required:
            issues.add(path, f"'{path}' wajib diisi (tidak boleh kosong).")
        return None

    if not isinstance(value, str):
        issues.add(path, f"'{path}' harus berupa string, bukan {_label(value)}.{_quote_hint(value)}")
        return None

    if not allow_empty and not value.strip():
        message = (
            f"'{path}' wajib diisi (tidak boleh kosong)." if required
            else f"'{path}' tidak boleh string kosong - hapus field-nya kalau tidak dipakai."
        )
        issues.add(path, message)
        return None

    return value


def _mapping(
    container: Mapping, key: str, issues: _Issues, *, required: bool = False, hint: str = "",
) -> Optional[Mapping]:
    value = container.get(key)

    if value is None:
        if required:
            issues.add(key, f"'{key}' wajib diisi.")
        return None

    if not isinstance(value, Mapping):
        issues.add(key, f"'{key}' harus berupa mapping{hint}, bukan {_label(value)}.")
        return None

    return value


def _list(container: Mapping, key: str, path: str, issues: _Issues) -> Optional[list]:
    value = container.get(key)

    if value is None:
        return None

    if not isinstance(value, list):
        issues.add(path, f"'{path}' harus berupa list, bukan {_label(value)}.")
        return None

    return value


def _unknown_keys(container: Mapping, allowed: tuple[str, ...], prefix: str, issues: _Issues) -> None:
    for key in container:
        if isinstance(key, str) and key not in allowed:
            issues.add(f"{prefix}{key}", f"field '{prefix}{key}' tidak dikenal.")


def _core_version(version: str) -> Optional[tuple[int, int, int]]:
    """(major, minor, patch) dari string semver valid; pre-release/build diabaikan."""
    if not VERSION_RE.match(version):
        return None

    core = re.split(r"[-+]", version, maxsplit=1)[0]
    major, minor, patch = (int(part) for part in core.split("."))

    return major, minor, patch


# ============================================================ validasi per bagian

def _check_author(data: Mapping, strict: bool, required: bool, issues: _Issues) -> None:
    author = _mapping(data, "author", issues, required=required, hint=" (name, email, url)")

    if author is None:
        return

    _string(author, "name", "author.name", issues, required=True)

    email = _string(author, "email", "author.email", issues)
    if email is not None and not EMAIL_RE.match(email):
        issues.add("author.email", "'author.email' bukan alamat email yang valid.")

    url = _string(author, "url", "author.url", issues)
    if url is not None:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            issues.add("author.url", "'author.url' harus berupa URL http:// atau https://.")

    if strict:
        _unknown_keys(author, _AUTHOR_FIELDS, "author.", issues)


def _check_compatibility(data: Mapping, strict: bool, issues: _Issues) -> None:
    compat = _mapping(data, "compatibility", issues)

    if compat is None:
        return

    versions: dict[str, Optional[tuple[int, int, int]]] = {}

    for key in ("min_aira_version", "max_aira_version"):
        path = f"compatibility.{key}"
        value = _string(compat, key, path, issues)

        if value is None:
            continue

        error = validate_version(value)
        if error:
            issues.add(path, f"'{path}': {error}")
        else:
            versions[key] = _core_version(value)

    low, high = versions.get("min_aira_version"), versions.get("max_aira_version")
    if low is not None and high is not None and low > high:
        issues.add(
            "compatibility.min_aira_version",
            "'compatibility.min_aira_version' tidak boleh lebih besar dari 'compatibility.max_aira_version'.",
        )

    platforms = _list(compat, "platforms", "compatibility.platforms", issues)

    if platforms is not None:
        seen: set[str] = set()

        for index, item in enumerate(platforms):
            path = f"compatibility.platforms[{index}]"

            if not isinstance(item, str):
                issues.add(path, f"'{path}' harus berupa string, bukan {_label(item)}.")
            elif item not in KNOWN_PLATFORMS:
                issues.add(path, f"platform '{item}' tidak dikenal. Pilihan: {', '.join(sorted(KNOWN_PLATFORMS))}.")
            elif item in seen:
                issues.add(path, f"platform '{item}' terdaftar lebih dari sekali.")
            else:
                seen.add(item)

    if strict:
        _unknown_keys(compat, _COMPATIBILITY_FIELDS, "compatibility.", issues)


def _check_declarations(data: Mapping, key: str, issues: _Issues) -> None:
    """capabilities / permissions: list identifier deklarasi tanpa duplikat (syntax saja)."""
    items = _list(data, key, key, issues)

    if items is None:
        return

    seen: set[str] = set()

    for index, item in enumerate(items):
        path = f"{key}[{index}]"

        if not isinstance(item, str):
            issues.add(path, f"'{path}' harus berupa string, bukan {_label(item)}.")
        elif not DECLARATION_ID_RE.match(item):
            issues.add(
                path,
                f"'{path}' ('{item}') bukan identifier yang valid: huruf kecil/angka/'_'/'-', "
                "dipisah '.' atau ':' (mis. 'network.ssh').",
            )
        elif item in seen:
            issues.add(path, f"'{key}' berisi '{item}' lebih dari sekali.")
        else:
            seen.add(item)


def _check_dependencies(data: Mapping, plugin_id: Optional[str], strict: bool, issues: _Issues) -> None:
    items = _list(data, "dependencies", "dependencies", issues)

    if items is None:
        return

    seen: set[str] = set()

    for index, item in enumerate(items):
        prefix = f"dependencies[{index}]"
        dep_id: Optional[str] = None

        if isinstance(item, str):
            dep_id = item
            error = validate_plugin_id(item)
            if error:
                issues.add(prefix, f"'{prefix}': {error}")
                dep_id = None

        elif isinstance(item, Mapping):
            raw_id = item.get("id")

            if raw_id is None:
                issues.add(f"{prefix}.id", f"'{prefix}.id' wajib diisi.")
            elif not isinstance(raw_id, str):
                issues.add(f"{prefix}.id", f"'{prefix}.id' harus berupa string, bukan {_label(raw_id)}.")
            else:
                error = validate_plugin_id(raw_id)
                if error:
                    issues.add(f"{prefix}.id", f"'{prefix}.id': {error}")
                else:
                    dep_id = raw_id

            constraint = item.get("version_constraint")
            if constraint is not None:
                if not isinstance(constraint, str):
                    issues.add(
                        f"{prefix}.version_constraint",
                        f"'{prefix}.version_constraint' harus berupa string, bukan {_label(constraint)}."
                        f"{_quote_hint(constraint)}",
                    )
                else:
                    error = validate_version_constraint(constraint)
                    if error:
                        issues.add(f"{prefix}.version_constraint", f"'{prefix}.version_constraint': {error}")

            optional = item.get("optional")
            if optional is not None and not isinstance(optional, bool):
                issues.add(
                    f"{prefix}.optional",
                    f"'{prefix}.optional' harus berupa boolean (true/false), bukan {_label(optional)}.",
                )

            if strict:
                _unknown_keys(item, _DEPENDENCY_FIELDS, f"{prefix}.", issues)

        else:
            issues.add(prefix, f"'{prefix}' harus berupa string id atau mapping, bukan {_label(item)}.")
            continue

        if dep_id is None:
            continue

        if plugin_id is not None and dep_id == plugin_id:
            issues.add(f"{prefix}.id" if isinstance(item, Mapping) else prefix,
                       f"plugin tidak boleh bergantung pada dirinya sendiri ('{dep_id}').")
        elif dep_id in seen:
            issues.add(f"{prefix}.id" if isinstance(item, Mapping) else prefix,
                       f"dependency '{dep_id}' terdaftar lebih dari sekali.")
        else:
            seen.add(dep_id)


def _check_tags(data: Mapping, issues: _Issues) -> None:
    tags = _list(data, "tags", "tags", issues)

    if tags is None:
        return

    for index, tag in enumerate(tags):
        path = f"tags[{index}]"

        if not isinstance(tag, str):
            issues.add(path, f"'{path}' harus berupa string, bukan {_label(tag)}.")
        elif not tag.strip():
            issues.add(path, f"'{path}' tidak boleh string kosong.")


# ============================================================ inti

def _validate(data: Any, *, strict: bool, required: tuple[str, ...], issues: _Issues) -> None:
    if not isinstance(data, Mapping):
        issues.add("manifest", f"Root manifest harus berupa mapping, bukan {_label(data)}.")
        return

    for key in data:
        if not isinstance(key, str):
            issues.add(
                "manifest",
                f"Semua key manifest harus string, ditemukan key {_label(key)}: {key!r}. "
                "(Hati-hati: 'yes'/'no'/'on'/'off' tanpa kutip dibaca YAML sebagai boolean.)",
            )

    if strict:
        _unknown_keys(data, KNOWN_FIELDS, "", issues)

    # ---- identitas
    plugin_id = _string(data, "id", "id", issues, required="id" in required)
    if plugin_id is not None:
        error = validate_plugin_id(plugin_id)
        if error:
            issues.add("id", error)
            plugin_id = None

    _string(data, "name", "name", issues, required="name" in required)

    version = _string(data, "version", "version", issues, required="version" in required)
    if version is not None:
        error = validate_version(version)
        if error:
            issues.add("version", error)

    _string(data, "description", "description", issues, allow_empty=True)
    _check_author(data, strict, "author" in required, issues)

    entry_point = _string(data, "entry_point", "entry_point", issues)
    if entry_point is not None and not ENTRY_POINT_RE.match(entry_point):
        issues.add(
            "entry_point",
            "'entry_point' harus berformat 'paket.modul:NamaClass' (mis. 'plugins.contoh.main:ContohPlugin').",
        )

    _string(data, "category", "category", issues)
    _check_tags(data, issues)

    # ---- kontrak API
    api_version = _string(data, "api_version", "api_version", issues, required="api_version" in required)
    if api_version is not None and not API_VERSION_RE.match(api_version):
        issues.add(
            "api_version",
            "'api_version' harus berformat 'MAJOR', 'MAJOR.MINOR', atau 'MAJOR.MINOR.PATCH' (mis. \"1\" atau \"1.0\").",
        )

    _check_compatibility(data, strict, issues)
    _check_declarations(data, "capabilities", issues)
    _check_declarations(data, "permissions", issues)
    _check_dependencies(data, plugin_id, strict, issues)


def _result(issues: _Issues) -> PluginValidationResult:
    return PluginValidationResult(is_valid=not issues.items, issues=issues.items)


# ============================================================ API publik

def validate_manifest_data(data: Any, *, strict: bool = False) -> PluginValidationResult:
    """
    Validasi OTORITATIF atas raw mapping (mis. ManifestLoadResult.raw).
    strict=True juga menolak field yang tidak dikenal (deteksi salah ketik).
    Tidak pernah raise; input apa pun menghasilkan PluginValidationResult.
    """
    issues = _Issues()

    try:
        _validate(data, strict=strict, required=REQUIRED_FIELDS, issues=issues)
    except Exception as exc:  # jaring pengaman: validator tidak boleh menjatuhkan caller
        logger.exception("MANIFEST VALIDATOR | kegagalan tak terduga.")
        issues.add("manifest", f"Validator gagal memeriksa manifest ({type(exc).__name__}).")

    return _result(issues)


def validate_plugin_manifest(manifest: PluginManifest, *, strict: bool = False) -> PluginValidationResult:
    """
    Validasi objek PluginManifest (representasi kanonik) dengan skema yang
    sama seperti validate_manifest_data. api_version kosong ("") berarti
    tidak dideklarasikan -> dilaporkan sebagai field wajib. Untuk mendeteksi
    tipe salah dari file mentah, gunakan validate_manifest_data(raw).
    Tidak pernah raise.
    """
    if not isinstance(manifest, PluginManifest):
        return PluginValidationResult(
            is_valid=False,
            issues=[PluginValidationIssue("manifest", "manifest harus berupa PluginManifest.")],
        )

    try:
        data = manifest.to_dict()
    except Exception:
        return PluginValidationResult(
            is_valid=False,
            issues=[PluginValidationIssue("manifest", "manifest tidak dapat diperiksa (ada field bertipe salah).")],
        )

    # api_version "" (default PluginManifest) = tidak dideklarasikan; _string()
    # melaporkannya sebagai field wajib yang kosong, sama seperti key yang hilang.
    #
    # to_dict() memakai list(...), yang akan memecah string "abc" menjadi
    # ["a", "b", "c"] dan meloloskannya. Periksa nilai atribut apa adanya.
    for name in ("capabilities", "permissions"):
        data[name] = getattr(manifest, name)

    issues = _Issues()

    try:
        _validate(data, strict=strict, required=OBJECT_REQUIRED_FIELDS, issues=issues)
    except Exception as exc:
        logger.exception("MANIFEST VALIDATOR | kegagalan tak terduga.")
        issues.add("manifest", f"Validator gagal memeriksa manifest ({type(exc).__name__}).")

    return _result(issues)


class ManifestValidator:
    """Pembungkus tipis supaya strictness diset sekali: validate(mapping | PluginManifest)."""

    def __init__(self, *, strict: bool = False) -> None:
        self.strict = strict

    def validate(self, source: Union[Mapping, PluginManifest]) -> PluginValidationResult:
        if isinstance(source, PluginManifest):
            return validate_plugin_manifest(source, strict=self.strict)

        return validate_manifest_data(source, strict=self.strict)


__all__ = [
    "API_VERSION_RE",
    "KNOWN_FIELDS",
    "KNOWN_PLATFORMS",
    "OBJECT_REQUIRED_FIELDS",
    "REQUIRED_FIELDS",
    "ManifestValidator",
    "validate_manifest_data",
    "validate_plugin_manifest",
    "validate_version_constraint",
]