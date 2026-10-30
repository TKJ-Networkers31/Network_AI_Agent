"""
core/nms_models.py — Domain constants, enums, rate calculation formulas, and safe defaults
for AIRA Network Management System & Live Topology Monitoring (NMS).
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# NMS Status Values (State Machine)
# ---------------------------------------------------------------------------
# UP: Health check passed and required metrics responding.
# DEGRADED: Reachable, but one or more monitoring checks or required metrics are failing.
# SUSPECTED_DOWN: Consecutive reachability checks failed (< failure threshold).
# DOWN: Consecutive reachability checks failed (>= failure threshold).
# UNKNOWN: No reliable monitoring result is available yet.
# MONITORING_UNAVAILABLE: Device reachable, but selected management method (SNMP/API) is unavailable/misconfigured.
# MAINTENANCE: Device intentionally excluded from outage alerts.
NMS_STATUS_VALUES = (
    "UP",
    "DEGRADED",
    "SUSPECTED_DOWN",
    "DOWN",
    "UNKNOWN",
    "MONITORING_UNAVAILABLE",
    "MAINTENANCE",
)

MANAGEMENT_MODE_VALUES = ("managed", "unmanaged", "ping_only")
SNMP_VERSION_VALUES = ("v1", "v2c", "v3")

INCIDENT_SEVERITY_VALUES = ("critical", "warning", "info")
INCIDENT_STATUS_VALUES = ("open", "resolved", "acknowledged")
INCIDENT_TYPE_VALUES = (
    "device_down",
    "device_recovered",
    "service_degraded",
    "monitoring_failed",
    "resource_threshold",
    "interface_down",
)

DEFAULT_NMS_SETTINGS: Dict[str, Any] = {
    "auto_monitoring_enabled": True,
    "default_interval_sec": 15,
    "failure_threshold": 3,
    "recovery_threshold": 2,
    "ping_timeout_sec": 2.0,
    "snmp_timeout_sec": 3.0,
    "max_concurrent_polls": 10,
    "history_retention_days": 7,
    "cpu_warning_threshold": 85.0,
    "memory_warning_threshold": 90.0,
}

INTERVAL_PRESETS = (5, 10, 15, 30, 60)
MIN_INTERVAL_SEC = 5
MAX_INTERVAL_SEC = 3600

# Rollover boundaries for 32-bit and 64-bit network octet counters
UINT32_MAX = 4294967295
UINT64_MAX = 18446744073709551615


def calculate_traffic_rate(
    curr_octets: Optional[int],
    prev_octets: Optional[int],
    curr_time: float,
    prev_time: float,
    speed_bps: Optional[int] = None,
) -> Tuple[float, Optional[float]]:
    """
    Menghitung laju bandwidth (bps) dan persentase utilisasi dari dua sampel counter octet.
    Menangani counter wraparound (32-bit / 64-bit), reset counter (reboot router),
    dan batas waktu elapsed.

    Returns:
        (rate_bps, utilization_percent)
    """
    if curr_octets is None or prev_octets is None:
        return 0.0, None

    time_delta = curr_time - prev_time
    if time_delta <= 0.001:
        return 0.0, None

    # Hitung selisih byte
    if curr_octets >= prev_octets:
        octets_delta = curr_octets - prev_octets
    else:
        # Counter turun (curr_octets < prev_octets).
        # Bedakan antara wraparound yang sah vs counter reset / device reboot.
        if prev_octets > UINT32_MAX:
            # 64-bit counter: hanya wrap bila prev mendekati UINT64_MAX
            if prev_octets >= (UINT64_MAX - 100_000_000_000):
                octets_delta = (UINT64_MAX - prev_octets) + curr_octets + 1
            else:
                octets_delta = 0  # Counter reset / reboot
        elif prev_octets >= (UINT32_MAX // 2):
            # 32-bit counter: hanya wrap bila prev sudah di paruh atas (>= 2.14 GB)
            potential_wrap = (UINT32_MAX - prev_octets) + curr_octets + 1
            # Cek apakah laju wrap ini masuk akal
            wrap_rate = (potential_wrap * 8.0) / time_delta
            if speed_bps and speed_bps > 0 and wrap_rate > (speed_bps * 1.5):
                octets_delta = 0  # Terlalu tinggi untuk kapasitas port, pasti reboot
            elif wrap_rate > 10_000_000_000:  # Port 32-bit umumnya maks 1-10 Gbps
                octets_delta = 0  # Spurious spike / reboot
            else:
                octets_delta = potential_wrap
        else:
            # Counter turun padahal prev_octets masih rendah (< 2.14 GB): pasti reboot/reset
            octets_delta = 0

    # Cegah lonjakan janggal (spikes) bila counter reset drastis
    # Maksimum traffic wajar per detik: 100 Gbps (12.5 GB/s)
    max_reasonable_bytes = 12_500_000_000 * time_delta
    if octets_delta < 0 or octets_delta > max_reasonable_bytes:
        octets_delta = 0

    rate_bps = (octets_delta * 8.0) / time_delta

    # Hitung utilisasi bila speed_bps terpercaya (> 0)
    utilization_percent = None
    if speed_bps and speed_bps > 0:
        utilization = (rate_bps / float(speed_bps)) * 100.0
        utilization_percent = round(min(100.0, max(0.0, utilization)), 2)

    return round(rate_bps, 2), utilization_percent


def determine_device_availability(
    current_status: str,
    consecutive_failures: int,
    consecutive_successes: int,
    ping_ok: bool,
    management_ok: Optional[bool],
    is_managed: bool,
    failure_threshold: int = 3,
    recovery_threshold: int = 2,
    is_paused: bool = False,
    is_maintenance: bool = False,
) -> Tuple[str, int, int]:
    """
    Transisi State Machine Ketersediaan Perangkat NMS.

    Returns:
        (new_status, new_consecutive_failures, new_consecutive_successes)
    """
    if is_maintenance:
        return "MAINTENANCE", 0, 0

    if is_paused:
        return "UNKNOWN", 0, 0

    if not ping_ok:
        new_failures = consecutive_failures + 1
        new_successes = 0
        if new_failures >= failure_threshold:
            new_status = "DOWN"
        else:
            new_status = "SUSPECTED_DOWN"
        return new_status, new_failures, new_successes

    # Ping berhasil
    new_successes = consecutive_successes + 1
    new_failures = 0

    # Bila sebelumnya DOWN atau SUSPECTED_DOWN, butuh recovery_threshold sukses
    if current_status in ("DOWN", "SUSPECTED_DOWN"):
        if new_successes < recovery_threshold:
            return current_status, new_failures, new_successes

    # Evaluasi status management jika perangkat berstatus 'managed'
    if is_managed:
        if management_ok is False:
            return "MONITORING_UNAVAILABLE", new_failures, new_successes
        elif management_ok is None:
            return "DEGRADED", new_failures, new_successes

    return "UP", new_failures, new_successes


def resolve_device_display_name(
    user_override: Optional[str] = None,
    verified_identity: Optional[str] = None,
    snmp_sys_name: Optional[str] = None,
    inventory_name: Optional[str] = None,
    ip: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Menentukan nama tampilan perangkat (display name) dan sumber nama (name_source)
    berdasarkan aturan preseden yang ketat:
    1. User override (prioritas tertinggi — tidak boleh ditimpa otomatis)
    2. Verified RouterOS identity (hasil query /system identity print)
    3. SNMP sysName (hasil query OID 1.3.6.1.2.1.1.5.0)
    4. Inventory name (nama saat didaftarkan di inventory)
    5. Fallback berlabel jelas (misal: 'Device (192.168.1.1)')

    Returns:
        (resolved_display_name, name_source)
    """
    if user_override and user_override.strip():
        return user_override.strip(), "user_override"

    if verified_identity and verified_identity.strip():
        clean_ident = verified_identity.strip()
        if clean_ident.lower() not in ("unknown", "unidentified", "none", ""):
            return clean_ident, "routeros_identity"

    if snmp_sys_name and snmp_sys_name.strip():
        clean_snmp = snmp_sys_name.strip()
        if clean_snmp.lower() not in ("unknown", "unidentified", "none", ""):
            return clean_snmp, "snmp_sys_name"

    if inventory_name and inventory_name.strip():
        return inventory_name.strip(), "inventory"

    if ip and ip.strip():
        return f"Device ({ip.strip()})", "fallback"

    return "Unidentified Device", "fallback"


def is_check_stale(
    last_check_at: Optional[float],
    interval_sec: int = 15,
    multiplier: float = 3.0,
    now: Optional[float] = None,
) -> bool:
    """
    Mengecek apakah data health check sudah usang (stale).
    True jika belum pernah dicek atau rentang waktu sejak check terakhir > (interval * multiplier).
    """
    if last_check_at is None or last_check_at <= 0:
        return True
    current_time = now if now is not None else time.time()
    stale_threshold = max(15.0, float(interval_sec) * float(multiplier))
    return (current_time - last_check_at) > stale_threshold



def parse_uptime_to_seconds(val: Any) -> Optional[int]:
    """Parses RouterOS or SNMP uptime representations to integer seconds."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return int(val)
    import re
    s = str(val).strip().lower()
    if not s or s in ("-", "unknown", "none", "null"):
        return None
    if s.isdigit():
        return int(s)

    if ":" in s:
        d = 0
        m_w = re.search(r"(\d+)w", s)
        if m_w:
            d += int(m_w.group(1)) * 7
        m_d = re.search(r"(\d+)d", s)
        if m_d:
            d += int(m_d.group(1))
        m_time = re.search(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", s)
        if m_time:
            h = int(m_time.group(1))
            m = int(m_time.group(2))
            sec = int(m_time.group(3) or 0)
            return d * 86400 + h * 3600 + m * 60 + sec

    weeks = re.search(r"(\d+)\s*w", s)
    days = re.search(r"(\d+)\s*d", s)
    hours = re.search(r"(\d+)\s*h", s)
    mins = re.search(r"(\d+)\s*m(?!s)", s)
    secs = re.search(r"(\d+)\s*s", s)

    if weeks or days or hours or mins or secs:
        total = 0
        if weeks:
            total += int(weeks.group(1)) * 7 * 86400
        if days:
            total += int(days.group(1)) * 86400
        if hours:
            total += int(hours.group(1)) * 3600
        if mins:
            total += int(mins.group(1)) * 60
        if secs:
            total += int(secs.group(1))
        return total

    return None
