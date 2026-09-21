"""
core/plugins/models.py — Phase 1 Plugin Foundation: data models.

HANYA bentuk data + regex/format checks murni (dataclass + str-Enum),
mengikuti pola yang sudah dipakai di repo ini (core/dio/models.py,
core/filesystem/models.py, core/host/models.py, core/runtime_state/models.py):
tanpa I/O, tanpa database, tanpa Event Bus, tanpa reasoning.

Ini BUKAN Plugin Manager, BUKAN Capability Registry, dan BUKAN Permission
System - itu semua eksplisit di luar cakupan Phase 1 (lihat
AKANE_PLUGIN_SPEC.md). File ini hanya mendefinisikan bentuk manifest
plugin, dependency-nya, dan state lifecycle-nya.

"Validasi format" (validate_plugin_id / validate_version / validate_manifest)
ada di sini bersama modelnya, dipisah dari "membangun manifest dari
dict" (core/plugins/manifest.py) — pola yang sama dengan
core/dio/models.py + core/dio/validator.py: builder/parser tetap berhasil
membentuk objek walau datanya cacat, validator yang menandai masalahnya.

ALIGNMENT (Phase 1.3): PluginManifest adalah representasi KANONIK manifest
plugin (single source of truth). Semua field manifest yang disepakati
(id, name, version, description, author, api_version, compatibility,
capabilities, permissions, dependencies) dimodelkan di sini, dan tipenya
dipakai apa adanya oleh manifest_from_dict(), loader, dan validator.
Validasi LENGKAP ada di core/plugins/validator.py; validate_manifest() di
file ini tetap pemeriksaan struktural dasar Phase 1.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional

# ------------------------------------------------------------------ regex

# Sama gayanya dengan _STYLE_ID_RE (core/persona/loader.py) dan
# _STYLE_ID_RE-style slug lain di repo: huruf kecil/angka, - dan _,
# mulai dengan huruf/angka, panjang wajar.
PLUGIN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")

# Semver inti (major.minor.patch) + pre-release/build metadata opsional.
# Regex-only (tanpa dependency baru seperti `packaging`/`semver`) - sama
# dengan pendekatan validasi format lain di repo (core/dio, core/persona).
VERSION_RE = re.compile(
    r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)


def validate_plugin_id(value: Any) -> Optional[str]:
    """Return pesan error, atau None kalau valid."""
    if not isinstance(value, str) or not PLUGIN_ID_RE.match(value):
        return (
            "plugin id harus huruf kecil/angka/'-'/'_' (mis. 'akane-net-tools'), "
            "diawali huruf atau angka, 2-64 karakter."
        )
    return None


def validate_version(value: Any) -> Optional[str]:
    """Return pesan error, atau None kalau valid (semver inti: MAJOR.MINOR.PATCH)."""
    if not isinstance(value, str) or not VERSION_RE.match(value):
        return "version harus format semver, mis. '1.0.0' atau '1.2.0-beta.1'."
    return None


def _clean(data: dict) -> dict:
    """Buang key bernilai None, konsisten dengan pola *.to_dict() lain di repo
    (mis. core/dio/models.py::_clean)."""
    return {k: v for k, v in data.items() if v is not None}


# ============================================================ PluginState

class PluginState(str, Enum):
    """str-Enum: langsung JSON-serializable, sama gayanya dengan
    core/runtime_state/models.py::RuntimeState dan
    core/filesystem/models.py::PermissionLevel.

    Lifecycle linear yang direpresentasikan (urutan normal):
        DISCOVERED -> LOADED -> INITIALIZED -> ENABLED <-> DISABLED -> SHUTDOWN
    ERROR bisa dicapai dari state mana pun. Transisi TIDAK divalidasi di
    sini (bukan state machine/manager) - modul ini hanya mendefinisikan
    nilai yang sah; pelacakan & transisi state ada di interface.py, milik
    tiap instance Plugin sendiri.
    """

    DISCOVERED = "DISCOVERED"
    LOADED = "LOADED"
    INITIALIZED = "INITIALIZED"
    ENABLED = "ENABLED"
    DISABLED = "DISABLED"
    ERROR = "ERROR"
    SHUTDOWN = "SHUTDOWN"


# ============================================================ PluginAuthor

@dataclass
class PluginAuthor:
    name: str
    email: Optional[str] = None
    url: Optional[str] = None

    def to_dict(self) -> dict:
        return _clean(asdict(self))


# ===================================================== PluginCompatibility

@dataclass
class PluginCompatibility:
    """
    min_aira_version / max_aira_version: batas versi AIRA OS yang didukung
    (string semver, opsional). platforms: daftar platform yang didukung
    ("windows", "linux") - list KOSONG berarti tidak ada batasan platform
    (didukung di semua platform), sesuai HAL di core/host/*.
    """

    min_aira_version: Optional[str] = None
    max_aira_version: Optional[str] = None
    platforms: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        data = asdict(self)
        return _clean(data) | {"platforms": data["platforms"]}


# ======================================================= PluginDependency

@dataclass
class PluginDependency:
    """Satu dependency antar-plugin. version_constraint adalah string bebas
    (mis. '>=1.0.0') - parsing range semver penuh di luar cakupan Phase 1;
    hanya divalidasi non-kosong kalau diisi."""

    id: str
    version_constraint: Optional[str] = None
    optional: bool = False

    def to_dict(self) -> dict:
        return _clean(asdict(self)) | {"optional": self.optional}


# ========================================================= PluginManifest

@dataclass
class PluginManifest:
    """
    Deskripsi statis satu plugin - dibaca dari mis. plugin.yaml/plugin.json
    oleh loader di fase berikutnya (di luar cakupan Phase 1). Di sini hanya
    bentuk datanya.

    entry_point: path modul/class Python yang mengimplementasikan Plugin
    (string, mis. "plugins.contoh.main:ContohPlugin") - TIDAK di-import
    atau dieksekusi di sini; itu tanggung jawab loader Phase 2+.

    Field dan tipenya (representasi kanonik; dipakai sama persis oleh
    manifest_from_dict(), loader, dan validator):

      Field spesifikasi
        id, name, version   str
        description         str            ("" = tidak diisi)
        author              PluginAuthor
        api_version         str            ("" = tidak dideklarasikan)
        compatibility       PluginCompatibility
        capabilities        list[str]      (deklarasi saja; BUKAN Capability Registry)
        permissions         list[str]      (deklarasi saja; BUKAN Permission System)
        dependencies        list[PluginDependency]

      Field opsional di luar daftar spesifikasi (dipertahankan demi
      kompatibilitas Phase 1; BUKAN kontrak wajib)
        entry_point         Optional[str]
        category            str
        tags                list[str]

    Field baru (api_version, capabilities, permissions) sengaja diletakkan
    di AKHIR dan punya default, sehingga konstruksi posisional/keyword
    Phase 1.1 tetap valid.
    """

    id: str
    name: str
    version: str
    description: str = ""
    author: PluginAuthor = field(default_factory=lambda: PluginAuthor(name="Unknown"))
    entry_point: Optional[str] = None
    category: str = "general"
    tags: list[str] = field(default_factory=list)
    dependencies: list[PluginDependency] = field(default_factory=list)
    compatibility: PluginCompatibility = field(default_factory=PluginCompatibility)
    api_version: str = ""
    capabilities: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author.to_dict(),
            "api_version": self.api_version,
            "entry_point": self.entry_point,
            "category": self.category,
            "tags": list(self.tags),
            "capabilities": list(self.capabilities),
            "permissions": list(self.permissions),
            "dependencies": [d.to_dict() for d in self.dependencies],
            "compatibility": self.compatibility.to_dict(),
        }


# ============================================================ validasi

@dataclass
class PluginValidationIssue:
    field: str
    message: str

    def to_dict(self) -> dict:
        return {"field": self.field, "message": self.message}


@dataclass
class PluginValidationResult:
    is_valid: bool
    issues: list[PluginValidationIssue] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"is_valid": self.is_valid, "issues": [i.to_dict() for i in self.issues]}


def _require_non_empty(value: Any, field_name: str, issues: list[PluginValidationIssue]) -> None:
    if not isinstance(value, str) or not value.strip():
        issues.append(PluginValidationIssue(field_name, f"'{field_name}' wajib diisi (tidak boleh kosong)."))


def validate_manifest(manifest: PluginManifest) -> PluginValidationResult:
    """
    Validasi dasar Phase 1: field wajib tidak kosong, id/version berformat
    valid, tiap dependency id berformat valid. TIDAK memeriksa apakah
    dependency-nya benar-benar ada/terpasang (itu tugas resolver di fase
    berikutnya, bukan Phase 1).

    CATATAN (Phase 1.3): ini pemeriksaan struktural DASAR dan logikanya
    tidak berubah - ia belum memeriksa api_version/capabilities/permissions.
    Validasi lengkap atas PluginManifest ada di
    core/plugins/validator.py::validate_plugin_manifest.
    """
    issues: list[PluginValidationIssue] = []

    if not isinstance(manifest, PluginManifest):
        return PluginValidationResult(
            is_valid=False,
            issues=[PluginValidationIssue("manifest", "manifest harus berupa PluginManifest.")],
        )

    _require_non_empty(manifest.id, "id", issues)
    _require_non_empty(manifest.name, "name", issues)
    _require_non_empty(manifest.version, "version", issues)

    if isinstance(manifest.id, str) and manifest.id.strip():
        id_error = validate_plugin_id(manifest.id)
        if id_error:
            issues.append(PluginValidationIssue("id", id_error))

    if isinstance(manifest.version, str) and manifest.version.strip():
        version_error = validate_version(manifest.version)
        if version_error:
            issues.append(PluginValidationIssue("version", version_error))

    if not isinstance(manifest.author, PluginAuthor):
        issues.append(PluginValidationIssue("author", "author harus berupa PluginAuthor."))
    else:
        _require_non_empty(manifest.author.name, "author.name", issues)

    if not isinstance(manifest.compatibility, PluginCompatibility):
        issues.append(PluginValidationIssue("compatibility", "compatibility harus berupa PluginCompatibility."))

    for index, dependency in enumerate(manifest.dependencies):
        prefix = f"dependencies[{index}]"

        if not isinstance(dependency, PluginDependency):
            issues.append(PluginValidationIssue(prefix, "dependency harus berupa PluginDependency."))
            continue

        dep_id_error = validate_plugin_id(dependency.id)
        if dep_id_error:
            issues.append(PluginValidationIssue(f"{prefix}.id", dep_id_error))

        if dependency.version_constraint is not None and not str(dependency.version_constraint).strip():
            issues.append(PluginValidationIssue(
                f"{prefix}.version_constraint",
                "version_constraint tidak boleh string kosong - kosongkan (None) kalau tidak dibatasi.",
            ))

    return PluginValidationResult(is_valid=len(issues) == 0, issues=issues)