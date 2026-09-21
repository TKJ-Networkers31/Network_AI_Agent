"""
core/plugins/manifest.py — Phase 1 Plugin Foundation: manifest parsing.

Memisahkan "membangun PluginManifest dari data mentah (dict)" dari
"memvalidasi isinya" (core/plugins/models.py::validate_manifest) - pola
yang sama dengan core/dio/analyzer.py + core/dio/validator.py dan
core/context/models.py::AIRAContext.from_dict: parser TIDAK PERNAH raise
dan TIDAK menolak data yang bentuknya salah - ia membentuk objek terbaik
yang bisa dibuat, lalu validate_manifest() yang menandai apa yang
bermasalah. Ini penting supaya Phase 2 (loader plugin dari disk) bisa
menampilkan pesan error yang jelas ("manifest.json plugin X: field version
kosong") alih-alih exception mentah saat parsing.

Loader plugin sungguhan (membaca plugin.yaml/plugin.json dari disk,
meng-import entry_point) ADA DI LUAR cakupan Phase 1 - file ini hanya
menyediakan satu fungsi murni: dict -> PluginManifest.

ALIGNMENT (Phase 1.3): manifest_from_dict() adalah pembangun representasi
kanonik. Aturannya:
  - Setiap field yang nilainya VALID dibawa ke PluginManifest apa adanya
    (termasuk api_version, capabilities, permissions) - tidak ada yang
    dibuang, dinormalisasi, atau diubah bentuknya.
  - Nilai yang tipenya SALAH jatuh ke default (mis. `version: 1.0` -> "").
    Informasi "tipe salah" itu memang tidak bisa disimpan di dataclass
    bertipe; untuk mendeteksinya, validasi raw mapping-nya
    (core/plugins/validator.py::validate_manifest_data).
  - Field yang tidak diisi TIDAK diberi nilai pengganti yang menyerupai data
    asli: author yang hilang menghasilkan PluginAuthor(name=""), bukan
    "Unknown", supaya validator bisa membedakannya dari author sungguhan.
  - List disalin (tidak berbagi referensi dengan mapping sumber).
"""

from __future__ import annotations

from typing import Any, Optional

from core.plugins.models import (
    PluginAuthor,
    PluginCompatibility,
    PluginDependency,
    PluginManifest,
    PluginValidationResult,
    validate_manifest,
)


def _str_or_none(value: Any) -> Optional[str]:
    return value if isinstance(value, str) else None


def _str_list(raw: Any) -> list[str]:
    """list -> salinan berisi item string saja; bukan list -> []. Urutan dan duplikat dipertahankan."""
    return [item for item in raw if isinstance(item, str)] if isinstance(raw, list) else []


def _author_from_dict(raw: Any) -> PluginAuthor:
    if not isinstance(raw, dict):
        return PluginAuthor(name="")

    name = raw.get("name")
    return PluginAuthor(
        name=name if isinstance(name, str) else "",
        email=_str_or_none(raw.get("email")),
        url=_str_or_none(raw.get("url")),
    )


def _compatibility_from_dict(raw: Any) -> PluginCompatibility:
    if not isinstance(raw, dict):
        return PluginCompatibility()

    return PluginCompatibility(
        min_aira_version=_str_or_none(raw.get("min_aira_version")),
        max_aira_version=_str_or_none(raw.get("max_aira_version")),
        platforms=_str_list(raw.get("platforms")),
    )


def _dependency_from_dict(raw: Any) -> Optional[PluginDependency]:
    if isinstance(raw, str):
        return PluginDependency(id=raw)

    if not isinstance(raw, dict) or not isinstance(raw.get("id"), str):
        return None

    optional = raw.get("optional")

    return PluginDependency(
        id=raw["id"],
        version_constraint=_str_or_none(raw.get("version_constraint")),
        # Hanya boolean asli yang dibawa. bool("false") == True akan diam-diam
        # membalik arti manifest; nilai non-boolean dideteksi validator raw.
        optional=optional if isinstance(optional, bool) else False,
    )


def _dependencies_from_list(raw: Any) -> list[PluginDependency]:
    if not isinstance(raw, list):
        return []

    dependencies = []
    for item in raw:
        dependency = _dependency_from_dict(item)
        if dependency is not None:
            dependencies.append(dependency)

    return dependencies


def manifest_from_dict(data: dict) -> PluginManifest:
    """
    dict -> PluginManifest. Toleran: field hilang/rusak -> default aman,
    tidak pernah raise; field VALID selalu dibawa utuh (lihat docstring
    modul). Untuk tahu apakah manifest layak dipakai, validasi hasilnya
    (core/plugins/validator.py::validate_plugin_manifest); untuk mendeteksi
    tipe salah yang dinormalisasi parser ini, validasi mapping aslinya
    (validate_manifest_data).
    """
    data = data if isinstance(data, dict) else {}

    return PluginManifest(
        id=data.get("id") if isinstance(data.get("id"), str) else "",
        name=data.get("name") if isinstance(data.get("name"), str) else "",
        version=data.get("version") if isinstance(data.get("version"), str) else "",
        description=data.get("description") if isinstance(data.get("description"), str) else "",
        author=_author_from_dict(data.get("author")),
        entry_point=_str_or_none(data.get("entry_point")),
        category=data.get("category") if isinstance(data.get("category"), str) else "general",
        tags=_str_list(data.get("tags")),
        dependencies=_dependencies_from_list(data.get("dependencies")),
        compatibility=_compatibility_from_dict(data.get("compatibility")),
        api_version=data.get("api_version") if isinstance(data.get("api_version"), str) else "",
        capabilities=_str_list(data.get("capabilities")),
        permissions=_str_list(data.get("permissions")),
    )


def load_and_validate_manifest(data: dict) -> tuple[PluginManifest, PluginValidationResult]:
    """Shortcut: parse lalu validasi sekaligus - dipakai loader Phase 2+."""
    manifest = manifest_from_dict(data)
    return manifest, validate_manifest(manifest)