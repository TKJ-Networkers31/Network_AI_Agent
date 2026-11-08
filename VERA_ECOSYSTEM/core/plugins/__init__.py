"""
core/plugins/ — Phase 1 Plugin Foundation (AKANE_PLUGIN_SPEC.md, Phase 1).

Public API:

    from core.plugins import (
        Plugin, PluginContext,
        PluginManifest, PluginAuthor, PluginCompatibility, PluginDependency,
        PluginState,
        PluginValidationIssue, PluginValidationResult,
        validate_plugin_id, validate_version, validate_manifest,
        manifest_from_dict, load_and_validate_manifest,
    )

Cakupan Phase 1 (lihat masing-masing modul untuk detail):
    models.py    - dataclass/enum murni: manifest, dependency,
                   compatibility, author, state, hasil validasi
    manifest.py  - dict -> PluginManifest (parser toleran, terpisah dari
                   validasi)
    interface.py - kontrak abstrak Plugin + PluginContext minimal

TIDAK ADA di package ini (di luar cakupan Phase 1, sesuai
AKANE_PLUGIN_SPEC.md): Plugin Manager, Capability Registry, Permission
System, loader dari disk, eksekusi SSH/SNMP/API, atau plugin apa pun yang
sungguhan terdaftar/berjalan. Package ini murni definisi kontrak/data.
"""

from core.plugins.interface import Plugin, PluginContext
from core.plugins.manifest import load_and_validate_manifest, manifest_from_dict
from core.plugins.models import (
    PluginAuthor,
    PluginCompatibility,
    PluginDependency,
    PluginManifest,
    PluginState,
    PluginValidationIssue,
    PluginValidationResult,
    validate_manifest,
    validate_plugin_id,
    validate_version,
)

__all__ = [
    "Plugin",
    "PluginContext",
    "PluginManifest",
    "PluginAuthor",
    "PluginCompatibility",
    "PluginDependency",
    "PluginState",
    "PluginValidationIssue",
    "PluginValidationResult",
    "validate_plugin_id",
    "validate_version",
    "validate_manifest",
    "manifest_from_dict",
    "load_and_validate_manifest",
]