"""
core/location/service.py — LocationService: lokasi HOSTING + lokasi AKSES.

HOSTING : disimpan di database/location.db. Kalau kosong, dideteksi otomatis
          dari IP publik server (sekali). Isi manual (source=manual) tidak
          pernah ditimpa deteksi otomatis - hanya tombol "Deteksi otomatis".
AKSES   : per session_id, di memori. Prioritas: GPS browser > IP publik klien >
          klien di jaringan lokal (= lokasi hosting).

Privasi: koordinat TIDAK ditulis ke log/event; ke system prompt hanya dikirim
label kota + koordinat dibulatkan (~1 km).
"""

import logging
import math
import threading
import time
from dataclasses import dataclass, replace
from typing import Optional

from core.events import EventNames, event_bus

from . import geo
from .models import (
    LocationContext, ROLE_ACCESS, ROLE_HOST,
    SOURCE_BROWSER, SOURCE_IP, SOURCE_MANUAL, SOURCE_NETWORK,
    compose_label,
)
from .store import HostLocationStore, get_host_store

logger = logging.getLogger("aira.location")

SAME_AREA_KM = 25.0
ACCESS_RESOLVE_TTL = 30 * 60  # detik

_SOURCE_TEXT = {
    SOURCE_MANUAL: "diatur manual",
    SOURCE_BROWSER: "GPS/lokasi browser",
    SOURCE_IP: "perkiraan dari IP, bisa meleset",
    SOURCE_NETWORK: "jaringan lokal",
}


@dataclass
class _ClientState:
    ip: Optional[str] = None
    gps: Optional[LocationContext] = None
    resolved: Optional[LocationContext] = None
    resolved_at: float = 0.0


class LocationService:

    def __init__(self, store: Optional[HostLocationStore] = None):
        self._store = store
        self._clients: dict[str, _ClientState] = {}
        self._last_session_id: Optional[str] = None
        self._lock = threading.RLock()
        self._host_lock = threading.Lock()

    @property
    def store(self) -> HostLocationStore:
        return self._store or get_host_store()

    # ============================================================ HOSTING

    def get_host(self, auto_detect: bool = True) -> Optional[LocationContext]:
        with self._host_lock:
            host = self.store.load()

            if host or not auto_detect:
                return host

            return self._detect_host_locked()

    def detect_host(self) -> dict:
        """Tombol 'Deteksi otomatis' - menimpa lokasi hosting yang ada."""
        with self._host_lock:
            host = self._detect_host_locked()

        if host is None:
            return {"success": False, "error": "Tidak bisa mendeteksi lokasi hosting (server offline atau layanan IP tidak menjawab)."}

        return {"success": True, "host": host.to_dict()}

    def _detect_host_locked(self) -> Optional[LocationContext]:
        info = geo.lookup_ip(None)

        if not info:
            return None

        host = LocationContext(
            role=ROLE_HOST,
            latitude=info["latitude"], longitude=info["longitude"],
            label=compose_label(info.get("city"), info.get("region"), info.get("country")),
            city=info.get("city"), region=info.get("region"), country=info.get("country"),
            timezone=info.get("timezone"), source=SOURCE_IP, timestamp=time.time(),
        )

        self._save_host(host)
        return host

    def set_host(
        self,
        query: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        label: Optional[str] = None,
    ) -> dict:
        name = (label or query or "").strip()
        city = region = country = None

        if latitude is None or longitude is None:
            if not name:
                return {"success": False, "error": "Isi nama tempat atau koordinat."}

            found = geo.forward_geocode(name)

            if not found:
                return {"success": False, "error": f"Tempat '{name}' tidak ditemukan. Coba nama lain atau isi koordinat."}

            latitude, longitude = found["latitude"], found["longitude"]
            city, region, country = found.get("city"), found.get("region"), found.get("country")
        else:
            info = geo.reverse_geocode(latitude, longitude) or {}
            city, region, country = info.get("city"), info.get("region"), info.get("country")

        host = LocationContext(
            role=ROLE_HOST, latitude=latitude, longitude=longitude,
            label=name or compose_label(city, region, country),
            city=city, region=region, country=country,
            source=SOURCE_MANUAL, timestamp=time.time(),
        )

        with self._host_lock:
            self._save_host(host)

        return {"success": True, "host": host.to_dict()}

    def _save_host(self, host: LocationContext) -> None:
        self.store.save(host)
        self._invalidate_resolved()  # akses berbasis jaringan lokal ikut lokasi hosting
        self._publish(EventNames.LOCATION_UPDATED, role=ROLE_HOST, source=host.source, label=host.label)

    # ============================================================== AKSES

    def observe_client(self, session_id: Optional[str], ip: Optional[str]) -> None:
        """Catat IP klien sebuah sesi. Murni memori, tanpa network call."""
        if not session_id:
            return

        with self._lock:
            state = self._clients.setdefault(session_id, _ClientState())

            if ip and ip != state.ip:
                state.ip = ip
                state.resolved = None

            self._last_session_id = session_id

    def update_access(self, session_id: str, location: LocationContext, ip: Optional[str] = None) -> LocationContext:
        """Lokasi akses presisi dari browser (GPS)."""
        location.role = ROLE_ACCESS
        location.timestamp = location.timestamp or time.time()

        if location.has_coordinates() and not location.label:
            info = geo.reverse_geocode(location.latitude, location.longitude)
            if info:
                location.city = location.city or info.get("city")
                location.region = location.region or info.get("region")
                location.country = location.country or info.get("country")
                location.label = compose_label(location.city, location.region, location.country)

        with self._lock:
            state = self._clients.setdefault(session_id, _ClientState())
            state.gps = location
            if ip:
                state.ip = ip
            self._last_session_id = session_id

        self._publish(
            EventNames.LOCATION_UPDATED, role=ROLE_ACCESS, session_id=session_id,
            source=location.source, label=location.label,
        )
        return location

    def clear_access(self, session_id: str) -> None:
        """Buang GPS. IP klien tetap dicatat, jadi lokasi kembali berbasis jaringan/IP."""
        with self._lock:
            state = self._clients.get(session_id)
            if state:
                state.gps = None

        self._publish(EventNames.LOCATION_CLEARED, role=ROLE_ACCESS, session_id=session_id)

    def get_access(self, session_id: Optional[str], resolve: bool = True) -> Optional[LocationContext]:
        if not session_id:
            return self._terminal_access()

        with self._lock:
            # Sesi yang baru dibuat belum sempat melapor -> pakai klien yang terakhir terlihat.
            state = self._clients.get(session_id) or self._clients.get(self._last_session_id or "")

            if state is None:
                return None

            gps, ip = state.gps, state.ip
            fresh = state.resolved and (time.time() - state.resolved_at) < ACCESS_RESOLVE_TTL
            cached = state.resolved if fresh else None

        if gps:
            return gps

        if cached:
            return cached

        if not resolve or not ip:
            return None

        resolved = self._resolve_from_ip(ip)

        with self._lock:
            state.resolved = resolved
            state.resolved_at = time.time()

        return resolved

    def _terminal_access(self) -> Optional[LocationContext]:
        """Tanpa session (mode terminal) = user duduk di mesin hosting."""
        host = self.get_host()
        if host is None:
            return None
        return replace(host, role=ROLE_ACCESS, source=SOURCE_NETWORK, same_as_host=True, ip=None)

    def _resolve_from_ip(self, ip: str) -> Optional[LocationContext]:
        if geo.is_local_ip(ip):
            host = self.get_host()

            if host is None:
                return LocationContext(
                    role=ROLE_ACCESS, source=SOURCE_NETWORK, same_as_host=True, ip=ip,
                    label="jaringan lokal (lokasi hosting belum diketahui)", timestamp=time.time(),
                )

            return replace(host, role=ROLE_ACCESS, source=SOURCE_NETWORK,
                           same_as_host=True, ip=ip, accuracy=None)

        info = geo.lookup_ip(ip)

        if not info:
            return None

        return LocationContext(
            role=ROLE_ACCESS,
            latitude=info["latitude"], longitude=info["longitude"],
            label=compose_label(info.get("city"), info.get("region"), info.get("country")),
            city=info.get("city"), region=info.get("region"), country=info.get("country"),
            timezone=info.get("timezone"), source=SOURCE_IP, ip=ip, timestamp=time.time(),
        )

    def _invalidate_resolved(self) -> None:
        with self._lock:
            for state in self._clients.values():
                state.resolved = None

    # ============================================== RELASI, SNAPSHOT, PROMPT

    @staticmethod
    def relation(host: Optional[LocationContext], access: Optional[LocationContext]) -> dict:
        if host is None or access is None:
            return {"kind": "unknown", "distance_km": None}

        if access.same_as_host:
            same_network = bool(access.ip) and not geo.is_loopback_ip(access.ip)
            return {"kind": "same_network" if same_network else "same_machine", "distance_km": 0.0}

        if host.has_coordinates() and access.has_coordinates():
            distance = LocationService._haversine(
                host.latitude, host.longitude, access.latitude, access.longitude,
            )
            return {
                "kind": "same_area" if distance <= SAME_AREA_KM else "remote",
                "distance_km": round(distance, 1),
            }

        return {"kind": "unknown", "distance_km": None}

    def snapshot(self, session_id: Optional[str]) -> dict:
        host = self.get_host()
        access = self.get_access(session_id)

        return {
            "session_id": session_id,
            "host": host.to_dict() if host else None,
            "access": access.to_dict() if access else None,
            "relation": self.relation(host, access),
        }

    def build_prompt_block(self, session_id: Optional[str]) -> str:
        try:
            host = self.get_host()
            access = self.get_access(session_id)
        except Exception:
            logger.exception("LOCATION | gagal menyusun blok prompt (diabaikan).")
            return ""

        if host is None and access is None:
            return ""

        lines = ["=== KONTEKS LOKASI ==="]
        lines.append(
            f"Lokasi hosting (tempat server AIRA berjalan): {self._describe(host)}."
            if host else "Lokasi hosting: belum diketahui."
        )
        lines.append(
            f"Lokasi akses (tempat user membuka AIRA sekarang): {self._describe(access)}."
            if access else "Lokasi akses: belum diketahui."
        )

        sentence = self._relation_sentence(self.relation(host, access))
        if sentence:
            lines.append(sentence)

        lines.append(
            "Pakai lokasi akses untuk 'dekat sini', cuaca, atau waktu setempat user. "
            "Ping/traceroute/SSH/SNMP berjalan dari lokasi hosting, bukan dari lokasi akses. "
            "Kalau lokasi berstatus perkiraan atau belum diketahui, katakan begitu - jangan mengarang."
        )

        return "\n" + "\n".join(lines) + "\n"

    @staticmethod
    def _describe(loc: LocationContext) -> str:
        text = loc.display_name()

        if loc.has_coordinates():
            text += f"; koordinat ≈ {loc.latitude:.2f}, {loc.longitude:.2f}"
        if loc.timezone:
            text += f"; zona waktu {loc.timezone}"

        detail = _SOURCE_TEXT.get(loc.source, loc.source)
        if loc.source == SOURCE_BROWSER and loc.accuracy:
            detail += f", akurasi ±{int(loc.accuracy)} m"

        return f"{text} ({detail})"

    @staticmethod
    def _relation_sentence(rel: dict) -> str:
        kind = rel.get("kind")

        if kind == "same_machine":
            return "User mengakses dari mesin hosting itu sendiri."
        if kind == "same_network":
            return "User berada di jaringan yang sama dengan server hosting."
        if kind in ("same_area", "remote") and rel.get("distance_km") is not None:
            return f"Jarak user ke server hosting ≈ {rel['distance_km']} km."
        return ""

    # ============================================================= UTIL

    def has_location(self, session_id: str) -> bool:
        return self.get_access(session_id, resolve=False) is not None

    def distance_km(self, session_id: str, latitude: float, longitude: float) -> Optional[float]:
        location = self.get_access(session_id)

        if not location or not location.has_coordinates():
            return None

        return self._haversine(location.latitude, location.longitude, latitude, longitude)

    @staticmethod
    def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        radius = 6371.0

        lat1, lat2 = math.radians(lat1), math.radians(lat2)
        dlat = lat2 - lat1
        dlon = math.radians(lon2 - lon1)

        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2

        return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    @staticmethod
    def _publish(event_name: str, **data) -> None:
        try:
            event_bus.publish(event_name, agent="LOCATION", data=data)
        except Exception:
            logger.exception("Gagal publish %s (diabaikan).", event_name)

    # Kompatibilitas nama lama
    def update(self, session_id: str, location: LocationContext) -> LocationContext:
        return self.update_access(session_id, location)

    def get(self, session_id: str) -> Optional[LocationContext]:
        return self.get_access(session_id)

    def clear(self, session_id: str) -> None:
        self.clear_access(session_id)


location_service = LocationService()