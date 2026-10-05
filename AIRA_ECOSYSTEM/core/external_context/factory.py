"""
core/external_context/factory.py — akses singleton provider.

get_maps_provider() = provider peta AKTIF. Default OpenStreetMap (gratis);
set MAPS_PROVIDER=google di .env untuk kembali ke Google Maps.
"""

from __future__ import annotations

import os
import threading
from typing import Optional

from core.external_context.config import GoogleMapsConfig, load_google_maps_config
from core.external_context.google_maps import GoogleMapsProvider
from core.external_context.openstreetmap import OpenStreetMapProvider

_google_maps_singleton: Optional[GoogleMapsProvider] = None
_google_maps_lock = threading.Lock()

_osm_singleton: Optional[OpenStreetMapProvider] = None
_osm_lock = threading.Lock()


def get_google_maps_provider(config: Optional[GoogleMapsConfig] = None) -> GoogleMapsProvider:
    global _google_maps_singleton

    if config is not None:
        return GoogleMapsProvider(config=config)

    if _google_maps_singleton is None:
        with _google_maps_lock:
            if _google_maps_singleton is None:
                _google_maps_singleton = GoogleMapsProvider(config=load_google_maps_config())

    return _google_maps_singleton


def reset_google_maps_provider() -> None:
    global _google_maps_singleton

    with _google_maps_lock:
        _google_maps_singleton = None


def get_openstreetmap_provider() -> OpenStreetMapProvider:
    global _osm_singleton

    if _osm_singleton is None:
        with _osm_lock:
            if _osm_singleton is None:
                _osm_singleton = OpenStreetMapProvider()

    return _osm_singleton


def get_maps_provider():
    """Provider peta aktif. Default OpenStreetMap; MAPS_PROVIDER=google untuk opt-in."""
    if os.getenv("MAPS_PROVIDER", "openstreetmap").strip().lower() == "google":
        return get_google_maps_provider()

    return get_openstreetmap_provider()