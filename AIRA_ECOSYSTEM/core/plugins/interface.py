"""
core/plugins/interface.py — Phase 1 Plugin Foundation: abstract Plugin
contract.

Mendefinisikan KONTRAK yang harus dipenuhi setiap plugin AIRA:

    manifest        - property, mengembalikan PluginManifest (wajib)
    identity        - property, id plugin (turunan dari manifest.id)
    state           - property, PluginState instance ini saat ini
    initialize(ctx)  -\
    enable()          |  lifecycle - WAJIB diimplementasikan subclass
    disable()         |  (abstrak, tidak ada default behaviour)
    shutdown()       -/

TIDAK ADA di file ini (sesuai cakupan Phase 1 / AKANE_PLUGIN_SPEC.md):
    - Plugin Manager (discovery, loading, dependency resolution)
    - Capability Registry (apa yang boleh diakses plugin)
    - Permission System (izin/otorisasi)
    - eksekusi SSH/SNMP/API apa pun
Instance Plugin di sini murni objek Python biasa; TIDAK ada mekanisme
yang mendaftarkan/menjalankannya secara otomatis.

PluginContext sengaja MINIMAL (hanya plugin_id + bag data bebas) supaya
tidak diam-diam menjadi capability registry/permission system. Field baru
di context ini adalah keputusan arsitektur untuk fase berikutnya, bukan
untuk Phase 1.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from core.plugins.models import PluginManifest, PluginState


@dataclass
class PluginContext:
    """
    Konteks minimal yang diteruskan ke Plugin.initialize().

    plugin_id : id plugin ini (memudahkan plugin melakukan logging
                ber-konteks tanpa perlu membaca manifest-nya sendiri).
    data      : bag serba-guna untuk fase berikutnya (mis. konfigurasi
                per-plugin) - KOSONG di Phase 1, tidak membawa
                capability/permission apa pun.
    """

    plugin_id: str
    data: dict[str, Any] = field(default_factory=dict)


class Plugin(ABC):
    """
    Kelas dasar abstrak untuk semua plugin AIRA. Subclass WAJIB
    mengimplementasikan property `manifest` dan keempat method lifecycle.

    State (`state` / `_set_state()`) disediakan sebagai bookkeeping
    sederhana milik instance plugin itu sendiri - BUKAN state machine yang
    memvalidasi/menegakkan urutan transisi (itu akan jadi tanggung jawab
    Plugin Manager di fase berikutnya, yang eksplisit di luar cakupan
    Phase 1). Subclass bebas memanggil `_set_state()` di titik yang sesuai
    di dalam method lifecycle-nya sendiri.
    """

    def __init__(self) -> None:
        self._state: PluginState = PluginState.DISCOVERED

    # ------------------------------------------------------------ wajib

    @property
    @abstractmethod
    def manifest(self) -> PluginManifest:
        """Deskripsi statis plugin ini. WAJIB diimplementasikan subclass."""
        raise NotImplementedError

    @property
    def identity(self) -> str:
        """Id plugin, diturunkan langsung dari manifest.id."""
        return self.manifest.id

    # --------------------------------------------------------------- state

    @property
    def state(self) -> PluginState:
        return self._state

    def _set_state(self, state: PluginState) -> None:
        if not isinstance(state, PluginState):
            raise TypeError("state harus berupa PluginState, bukan " + type(state).__name__)
        self._state = state

    # ----------------------------------------------------------- lifecycle

    @abstractmethod
    def initialize(self, context: PluginContext) -> None:
        """Dipanggil sekali setelah plugin dimuat, sebelum diaktifkan.
        Tempat yang tepat untuk validasi konfigurasi awal plugin."""
        raise NotImplementedError

    @abstractmethod
    def enable(self) -> None:
        """Aktifkan plugin (mis. mulai berpartisipasi dalam alur AIRA).
        Boleh dipanggil berulang (enable -> disable -> enable)."""
        raise NotImplementedError

    @abstractmethod
    def disable(self) -> None:
        """Nonaktifkan plugin tanpa membongkarnya - kebalikan dari enable()."""
        raise NotImplementedError

    @abstractmethod
    def shutdown(self) -> None:
        """Bongkar plugin secara permanen (lepas resource, dst). Setelah ini
        plugin tidak diharapkan di-enable() lagi tanpa initialize() ulang."""
        raise NotImplementedError