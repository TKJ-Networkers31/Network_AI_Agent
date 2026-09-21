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


def _author_from_dict(raw: Any) -> PluginAuthor:
    if not isinstance(raw, dict):
        return PluginAuthor(name="Unknown")

    name = raw.get("name")
    return PluginAuthor(
        name=name if isinstance(name, str) and name.strip() else "Unknown",
        email=_str_or_none(raw.get("email")),
        url=_str_or_none(raw.get("url")),
    )


def _compatibility_from_dict(raw: Any) -> PluginCompatibility:
    if not isinstance(raw, dict):
        return PluginCompatibility()

    platforms = raw.get("platforms")
    clean_platforms = [p for p in platforms if isinstance(p, str)] if isinstance(platforms, list) else []

    return PluginCompatibility(
        min_aira_version=_str_or_none(raw.get("min_aira_version")),
        max_aira_version=_str_or_none(raw.get("max_aira_version")),
        platforms=clean_platforms,
    )


def _dependency_from_dict(raw: Any) -> Optional[PluginDependency]:
    if isinstance(raw, str):
        return PluginDependency(id=raw)

    if not isinstance(raw, dict) or not isinstance(raw.get("id"), str):
        return None

    return PluginDependency(
        id=raw["id"],
        version_constraint=_str_or_none(raw.get("version_constraint")),
        optional=bool(raw.get("optional", False)),
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
    tidak pernah raise. Panggil validate_manifest(hasil) untuk tahu apakah
    manifest ini layak dipakai.
    """
    data = data if isinstance(data, dict) else {}

    tags = data.get("tags")
    clean_tags = [t for t in tags if isinstance(t, str)] if isinstance(tags, list) else []

    return PluginManifest(
        id=data.get("id") if isinstance(data.get("id"), str) else "",
        name=data.get("name") if isinstance(data.get("name"), str) else "",
        version=data.get("version") if isinstance(data.get("version"), str) else "",
        description=data.get("description") if isinstance(data.get("description"), str) else "",
        author=_author_from_dict(data.get("author")),
        entry_point=_str_or_none(data.get("entry_point")),
        category=data.get("category") if isinstance(data.get("category"), str) else "general",
        tags=clean_tags,
        dependencies=_dependencies_from_list(data.get("dependencies")),
        compatibility=_compatibility_from_dict(data.get("compatibility")),
    )


def load_and_validate_manifest(data: dict) -> tuple[PluginManifest, PluginValidationResult]:
    """Shortcut: parse lalu validasi sekaligus - dipakai loader Phase 2+."""
    manifest = manifest_from_dict(data)
    return manifest, validate_manifest(manifest)