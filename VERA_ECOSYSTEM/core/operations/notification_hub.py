"""
AIRA OS — Controlled Operational Notification Hub (Networking VII / WP 7.7).

Handles alert deduplication, cooldown intervals, timezone-aware quiet hours (Asia/Jakarta),
severity-based overrides, and WebSocket event distribution.
"""

from __future__ import annotations

from datetime import datetime, time as dtime, timezone
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid
import zoneinfo

from core.events import event_bus
from core.operations.db import ensure_operational_schema
from core.operations.models import (
    IncidentSeverity,
    NotificationDeliveryStatus,
    OperationalNotificationRecord,
)
from core.topology_db import (
    DEFAULT_TOPOLOGY_DB_PATH,
    topology_transaction,
)

logger = logging.getLogger("aira.operations.notifications")

DEFAULT_QUIET_HOURS_START = dtime(22, 0)  # 22:00 WIB
DEFAULT_QUIET_HOURS_END = dtime(6, 0)     # 06:00 WIB
DEFAULT_COOLDOWN_SECONDS = 900             # 15 minutes


class NotificationHub:
    """Manages operational notifications with deduplication and quiet hours policy."""

    def __init__(
        self,
        db_path: Optional[Path] = None,
        tz_name: str = "Asia/Jakarta",
        cooldown_sec: int = DEFAULT_COOLDOWN_SECONDS,
        quiet_start: dtime = DEFAULT_QUIET_HOURS_START,
        quiet_end: dtime = DEFAULT_QUIET_HOURS_END,
    ) -> None:
        self.db_path = Path(db_path or DEFAULT_TOPOLOGY_DB_PATH).resolve()
        self.tz = zoneinfo.ZoneInfo(tz_name)
        self.cooldown_sec = cooldown_sec
        self.quiet_start = quiet_start
        self.quiet_end = quiet_end
        ensure_operational_schema(self.db_path)

    @staticmethod
    def compute_dedup_key(category: str, title: str, identifier: str = "") -> str:
        """Generates a stable deduplication hash."""
        raw = f"{category.strip()}:{title.strip()}:{identifier.strip()}".lower()
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def is_in_quiet_hours(self, dt: Optional[datetime] = None) -> bool:
        """Evaluates whether the given timestamp falls inside local quiet hours in Asia/Jakarta."""
        current_dt = (dt or datetime.now(timezone.utc)).astimezone(self.tz)
        current_time = current_dt.time()

        if self.quiet_start > self.quiet_end:
            # Crosses midnight (e.g. 22:00 to 06:00)
            return current_time >= self.quiet_start or current_time < self.quiet_end
        else:
            return self.quiet_start <= current_time < self.quiet_end

    def dispatch_notification(
        self,
        category: str,
        severity: str,
        title: str,
        message: str,
        identifier: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        now_utc: Optional[datetime] = None,
    ) -> OperationalNotificationRecord:
        """
        Processes and dispatches an operational notification through deduplication and quiet hours.
        """
        curr_dt = now_utc or datetime.now(timezone.utc)
        now_iso = curr_dt.isoformat()
        dedup_key = self.compute_dedup_key(category, title, identifier)
        sev = severity.upper().strip()

        # 1. Deduplication & Cooldown Check
        with topology_transaction(self.db_path, write=False) as conn:
            recent_row = conn.execute(
                """
                SELECT created_at FROM operational_notifications
                WHERE dedup_key = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (dedup_key,),
            ).fetchone()

        if recent_row:
            try:
                last_dt = datetime.fromisoformat(recent_row[0])
                delta_sec = (curr_dt - last_dt).total_seconds()
                if delta_sec < self.cooldown_sec:
                    # Suppress duplicate
                    record = OperationalNotificationRecord(
                        notification_id=f"notif_{uuid.uuid4().hex[:10]}",
                        category=category,
                        severity=sev,
                        title=title,
                        message=message,
                        dedup_key=dedup_key,
                        delivery_status=NotificationDeliveryStatus.SUPPRESSED_COOLDOWN.value,
                        metadata=metadata or {},
                        created_at=now_iso,
                    )
                    self._persist_notification(record)
                    logger.debug("Notification suppressed by cooldown (key=%s, age=%ss)", dedup_key, int(delta_sec))
                    return record
            except Exception:
                pass

        # 2. Quiet Hours Evaluation
        in_quiet = self.is_in_quiet_hours(curr_dt)
        is_emergency = sev in (IncidentSeverity.CRITICAL.value, IncidentSeverity.HIGH.value)

        if in_quiet and not is_emergency:
            delivery_status = NotificationDeliveryStatus.QUEUED_QUIET_HOURS.value
        else:
            delivery_status = NotificationDeliveryStatus.SENT.value

        record = OperationalNotificationRecord(
            notification_id=f"notif_{uuid.uuid4().hex[:10]}",
            category=category,
            severity=sev,
            title=title,
            message=message,
            dedup_key=dedup_key,
            delivery_status=delivery_status,
            metadata=metadata or {},
            created_at=now_iso,
        )

        self._persist_notification(record)

        # 3. Publish to EventBus if SENT
        if delivery_status == NotificationDeliveryStatus.SENT.value:
            try:
                event_bus.publish(
                    event_name="operational.notification",
                    data=record.to_dict(),
                )
            except Exception as e:
                logger.warning("Failed to publish notification to EventBus: %s", e)

        return record

    def _persist_notification(self, record: OperationalNotificationRecord) -> None:
        """Saves notification log to SQLite."""
        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                """
                INSERT INTO operational_notifications (
                    notification_id, category, severity, title, message,
                    dedup_key, delivery_status, target_channels_json, metadata_json,
                    is_read, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.notification_id,
                    record.category,
                    record.severity,
                    record.title,
                    record.message,
                    record.dedup_key,
                    record.delivery_status,
                    json.dumps(record.target_channels),
                    json.dumps(record.metadata),
                    1 if record.is_read else 0,
                    record.created_at,
                ),
            )

    def list_notifications(
        self,
        unread_only: bool = False,
        limit: int = 50,
    ) -> List[OperationalNotificationRecord]:
        """Lists recent operational notifications."""
        query = """
            SELECT notification_id, category, severity, title, message,
                   dedup_key, delivery_status, target_channels_json, metadata_json,
                   is_read, created_at
            FROM operational_notifications
        """
        params: List[Any] = []
        if unread_only:
            query += " WHERE is_read = 0"
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with topology_transaction(self.db_path, write=False) as conn:
            rows = conn.execute(query, tuple(params)).fetchall()

        return [
            OperationalNotificationRecord(
                notification_id=r[0],
                category=r[1],
                severity=r[2],
                title=r[3],
                message=r[4],
                dedup_key=r[5],
                delivery_status=r[6],
                target_channels=json.loads(r[7] or "[]"),
                metadata=json.loads(r[8] or "{}"),
                is_read=bool(r[9]),
                created_at=r[10],
            )
            for r in rows
        ]
