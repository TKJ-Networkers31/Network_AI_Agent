"""
core/location/store.py — pemilik database/location.db.

HANYA lokasi HOSTING yang disimpan permanen (satu baris, id=1). Lokasi AKSES
sengaja tidak ditulis ke disk: itu posisi user dan berubah-ubah.
"""

import logging
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path
from typing import Optional

from core.location.models import LocationContext, ROLE_HOST

logger = logging.getLogger("aira.location.store")

BASE_DIR = Path(__file__).resolve().parents[2]  # AIRA_ECOSYSTEM/
DEFAULT_DB_FILE = BASE_DIR / "database" / "location.db"


class HostLocationStore:

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_FILE
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS host_location (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    latitude REAL,
                    longitude REAL,
                    label TEXT,
                    city TEXT,
                    region TEXT,
                    country TEXT,
                    timezone TEXT,
                    source TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)
            conn.commit()

    def load(self) -> Optional[LocationContext]:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM host_location WHERE id = 1").fetchone()

        if not row:
            return None

        return LocationContext(
            role=ROLE_HOST,
            latitude=row["latitude"], longitude=row["longitude"],
            label=row["label"], city=row["city"], region=row["region"],
            country=row["country"], timezone=row["timezone"],
            source=row["source"], timestamp=row["updated_at"],
        )

    def save(self, host: LocationContext) -> None:
        with self._lock, closing(self._connect()) as conn:
            conn.execute("""
                INSERT INTO host_location
                    (id, latitude, longitude, label, city, region, country, timezone, source, updated_at)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    latitude = excluded.latitude, longitude = excluded.longitude,
                    label = excluded.label, city = excluded.city, region = excluded.region,
                    country = excluded.country, timezone = excluded.timezone,
                    source = excluded.source, updated_at = excluded.updated_at
            """, (
                host.latitude, host.longitude, host.label, host.city, host.region,
                host.country, host.timezone, host.source, host.timestamp or time.time(),
            ))
            conn.commit()

        logger.info("HOST LOCATION SAVED | source=%s label=%s", host.source, host.label)


_store_singleton: Optional[HostLocationStore] = None
_store_lock = threading.Lock()


def get_host_store() -> HostLocationStore:
    global _store_singleton

    if _store_singleton is None:
        with _store_lock:
            if _store_singleton is None:
                _store_singleton = HostLocationStore()

    return _store_singleton