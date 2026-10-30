"""
core/nms_snmp.py — Async SNMP polling and capability inspection for AIRA NMS.
Supports SNMPv1, SNMPv2c, and SNMPv3 via pysnmp, querying standard MIB-II,
HOST-RESOURCES-MIB, and IF-MIB.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("aira.nms.snmp")


async def _create_transport_target(target_cls: Any, host: str, port: int, timeout: float, retries: int) -> Any:
    """Creates transport target compatible with both pysnmp v4/v5 and v6/v7 async signatures."""
    if hasattr(target_cls, "create") and inspect.iscoroutinefunction(target_cls.create):
        return await target_cls.create((host, port), timeout=timeout, retries=retries)
    return target_cls((host, port), timeout=timeout, retries=retries)

# Standard MIB OIDs
OID_SYS_DESCR = "1.3.6.1.2.1.1.1.0"
OID_SYS_UPTIME = "1.3.6.1.2.1.1.3.0"
OID_SYS_NAME = "1.3.6.1.2.1.1.5.0"

OID_CPU_LOAD_BASE = "1.3.6.1.2.1.25.3.3.1.2"  # hrProcessorLoad
OID_STORAGE_DESCR_BASE = "1.3.6.1.2.1.25.2.3.1.3"  # hrStorageDescr
OID_STORAGE_ALLOC_BASE = "1.3.6.1.2.1.25.2.3.1.4"  # hrStorageAllocationUnits
OID_STORAGE_SIZE_BASE = "1.3.6.1.2.1.25.2.3.1.5"  # hrStorageSize
OID_STORAGE_USED_BASE = "1.3.6.1.2.1.25.2.3.1.6"  # hrStorageUsed

# IF-MIB
OID_IF_DESCR_BASE = "1.3.6.1.2.1.2.2.1.2"
OID_IF_TYPE_BASE = "1.3.6.1.2.1.2.2.1.3"
OID_IF_SPEED_BASE = "1.3.6.1.2.1.2.2.1.5"
OID_IF_ADMIN_STATUS_BASE = "1.3.6.1.2.1.2.2.1.7"
OID_IF_OPER_STATUS_BASE = "1.3.6.1.2.1.2.2.1.8"
OID_IF_IN_OCTETS_BASE = "1.3.6.1.2.1.2.2.1.10"
OID_IF_IN_ERRORS_BASE = "1.3.6.1.2.1.2.2.1.14"
OID_IF_IN_DISCARDS_BASE = "1.3.6.1.2.1.2.2.1.13"
OID_IF_OUT_OCTETS_BASE = "1.3.6.1.2.1.2.2.1.16"
OID_IF_OUT_ERRORS_BASE = "1.3.6.1.2.1.2.2.1.20"
OID_IF_OUT_DISCARDS_BASE = "1.3.6.1.2.1.2.2.1.19"

# 64-bit HC counters & High Speed (IF-MIB extensions)
OID_IF_HIGH_SPEED_BASE = "1.3.6.1.2.1.31.1.1.1.15"

# 64-bit HC counters
OID_IF_HC_IN_OCTETS_BASE = "1.3.6.1.2.1.31.1.1.1.6"
OID_IF_HC_OUT_OCTETS_BASE = "1.3.6.1.2.1.31.1.1.1.10"

# MikroTik Health / Temperature MIB
OID_MT_TEMP = "1.3.6.1.4.1.14988.1.1.3.10.0"
OID_MT_CPU_TEMP = "1.3.6.1.4.1.14988.1.1.3.11.0"


def _safe_int(val: Any, default: int = 0) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


async def snmp_get_multi(
    host: str,
    port: int = 161,
    community: str = "public",
    version: str = "v2c",
    oids: Optional[Dict[str, str]] = None,
    timeout: float = 2.5,
    retries: int = 1,
) -> Tuple[Optional[Dict[str, str]], Optional[str]]:
    """
    Menjalankan SNMP GET multi-OID secara asinkron.
    Returns: (dict_values, error_str)
    """
    if not oids:
        return {}, None

    try:
        from pysnmp.hlapi.v3arch.asyncio import (
            CommunityData,
            ContextData,
            ObjectIdentity,
            ObjectType,
            SnmpEngine,
            UdpTransportTarget,
            get_cmd,
        )

        mp_model = 0 if version == "v1" else 1
        comm_data = CommunityData(community, mpModel=mp_model)
        target = await _create_transport_target(UdpTransportTarget, host, port, timeout, retries)

        labels = list(oids.keys())
        obj_types = [ObjectType(ObjectIdentity(oids[k])) for k in labels]

        engine = SnmpEngine()
        error_indication, error_status, error_index, var_binds = await get_cmd(
            engine,
            comm_data,
            target,
            ContextData(),
            *obj_types,
        )

        if error_indication:
            return None, str(error_indication)
        if error_status:
            return None, error_status.prettyPrint()

        result = {}
        for label, vb in zip(labels, var_binds):
            val_str = str(vb[1])
            # Handle No Such Object / No Such Instance
            if "No Such" in val_str:
                result[label] = ""
            else:
                result[label] = val_str

        return result, None
    except Exception as exc:
        return None, str(exc)


async def snmp_walk_table(
    host: str,
    port: int = 161,
    community: str = "public",
    version: str = "v2c",
    base_oid: str = "",
    timeout: float = 2.5,
    retries: int = 1,
    max_rows: int = 250,
) -> Tuple[List[Tuple[str, str]], Optional[str]]:
    """
    Menjalankan SNMP WALK pada subtree base_oid.
    Returns: ([(full_oid, val_str), ...], error_str)
    """
    if not base_oid:
        return [], None

    results = []
    try:
        from pysnmp.hlapi.v3arch.asyncio import (
            CommunityData,
            ContextData,
            ObjectIdentity,
            ObjectType,
            SnmpEngine,
            UdpTransportTarget,
            next_cmd,
        )

        mp_model = 0 if version == "v1" else 1
        comm_data = CommunityData(community, mpModel=mp_model)
        target = await _create_transport_target(UdpTransportTarget, host, port, timeout, retries)
        engine = SnmpEngine()

        current = ObjectType(ObjectIdentity(base_oid))
        count = 0

        while count < max_rows:
            error_indication, error_status, error_index, var_binds = await next_cmd(
                engine,
                comm_data,
                target,
                ContextData(),
                current,
            )

            if error_indication:
                return results, str(error_indication)
            if error_status:
                return results, error_status.prettyPrint()
            if not var_binds:
                break

            vb = var_binds[0]
            oid_str = str(vb[0])

            if not (oid_str == base_oid or oid_str.startswith(base_oid + ".")):
                break

            val_str = str(vb[1])
            if "No Such" not in val_str:
                results.append((oid_str, val_str))

            current = ObjectType(ObjectIdentity(oid_str))
            count += 1

        return results, None
    except Exception as exc:
        return results, str(exc)


async def poll_device_snmp_full(
    host: str,
    port: int = 161,
    community: str = "public",
    version: str = "v2c",
    timeout: float = 3.0,
) -> Dict[str, Any]:
    """
    Mengambil data sistem komprehensif (CPU, RAM, Uptime, Suhu, Storage, Interface)
    melalui SNMP secara terkoordinasi.
    """
    result: Dict[str, Any] = {
        "success": False,
        "error": None,
        "identity": "",
        "sys_descr": "",
        "uptime_seconds": 0,
        "cpu_load_percent": None,
        "memory_used_bytes": None,
        "memory_total_bytes": None,
        "memory_used_percent": None,
        "storage_used_bytes": None,
        "storage_total_bytes": None,
        "temperature_celsius": None,
        "interfaces": [],
    }

    # 1. System Info GET
    sys_oids = {
        "name": OID_SYS_NAME,
        "descr": OID_SYS_DESCR,
        "uptime": OID_SYS_UPTIME,
        "temp": OID_MT_TEMP,
        "cpu_temp": OID_MT_CPU_TEMP,
    }
    sys_data, err = await snmp_get_multi(
        host=host, port=port, community=community, version=version, oids=sys_oids, timeout=timeout
    )

    if err or not sys_data:
        result["error"] = err or "SNMP tidak merespons"
        return result

    result["success"] = True
    result["identity"] = sys_data.get("name", "")
    result["sys_descr"] = sys_data.get("descr", "")

    # Hitung uptime
    uptime_ticks = _safe_int(sys_data.get("uptime", 0))
    result["uptime_seconds"] = int(uptime_ticks / 100) if uptime_ticks else 0

    # Suhu (MikroTik OID mengembalikan celcius atau 1/10 celcius)
    temp_val = _safe_int(sys_data.get("cpu_temp") or sys_data.get("temp") or 0)
    if temp_val > 0:
        result["temperature_celsius"] = float(temp_val / 10.0 if temp_val > 200 else temp_val)

    # 2. CPU Load (hrProcessorLoad walk)
    cpu_walk, _ = await snmp_walk_table(
        host=host, port=port, community=community, version=version, base_oid=OID_CPU_LOAD_BASE, timeout=timeout
    )
    if cpu_walk:
        cores = [_safe_int(v) for _, v in cpu_walk if _safe_int(v, -1) >= 0]
        if cores:
            result["cpu_load_percent"] = round(sum(cores) / len(cores), 1)

    # 3. Storage & Memory (hrStorage table walk)
    descr_walk, _ = await snmp_walk_table(host=host, port=port, community=community, base_oid=OID_STORAGE_DESCR_BASE, timeout=timeout)
    size_walk, _ = await snmp_walk_table(host=host, port=port, community=community, base_oid=OID_STORAGE_SIZE_BASE, timeout=timeout)
    used_walk, _ = await snmp_walk_table(host=host, port=port, community=community, base_oid=OID_STORAGE_USED_BASE, timeout=timeout)
    alloc_walk, _ = await snmp_walk_table(host=host, port=port, community=community, base_oid=OID_STORAGE_ALLOC_BASE, timeout=timeout)

    alloc_map = {oid.split(".")[-1]: _safe_int(val, 1) for oid, val in alloc_walk}
    size_map = {oid.split(".")[-1]: _safe_int(val, 0) for oid, val in size_walk}
    used_map = {oid.split(".")[-1]: _safe_int(val, 0) for oid, val in used_walk}

    for oid, descr in descr_walk:
        idx = oid.split(".")[-1]
        descr_lower = descr.lower()
        alloc_unit = alloc_map.get(idx, 1024)
        total_b = size_map.get(idx, 0) * alloc_unit
        used_b = used_map.get(idx, 0) * alloc_unit

        if "ram" in descr_lower or "main memory" in descr_lower or "system memory" in descr_lower:
            result["memory_total_bytes"] = total_b
            result["memory_used_bytes"] = used_b
            if total_b > 0:
                result["memory_used_percent"] = round((used_b / total_b) * 100.0, 1)
        elif "flash" in descr_lower or "disk" in descr_lower or "storage" in descr_lower:
            result["storage_total_bytes"] = total_b
            result["storage_used_bytes"] = used_b

    # 4. Interfaces (Names, Status, Octets, Errors)
    if_descr_walk, _ = await snmp_walk_table(host=host, port=port, community=community, base_oid=OID_IF_DESCR_BASE, timeout=timeout)
    if_oper_walk, _ = await snmp_walk_table(host=host, port=port, community=community, base_oid=OID_IF_OPER_STATUS_BASE, timeout=timeout)
    if_admin_walk, _ = await snmp_walk_table(host=host, port=port, community=community, base_oid=OID_IF_ADMIN_STATUS_BASE, timeout=timeout)
    if_type_walk, _ = await snmp_walk_table(host=host, port=port, community=community, base_oid=OID_IF_TYPE_BASE, timeout=timeout)
    if_speed_walk, _ = await snmp_walk_table(host=host, port=port, community=community, base_oid=OID_IF_SPEED_BASE, timeout=timeout)
    if_hspeed_walk, _ = await snmp_walk_table(host=host, port=port, community=community, base_oid=OID_IF_HIGH_SPEED_BASE, timeout=timeout)
    if_hcin_walk, _ = await snmp_walk_table(host=host, port=port, community=community, base_oid=OID_IF_HC_IN_OCTETS_BASE, timeout=timeout)
    if_hcout_walk, _ = await snmp_walk_table(host=host, port=port, community=community, base_oid=OID_IF_HC_OUT_OCTETS_BASE, timeout=timeout)
    if_in_walk, _ = await snmp_walk_table(host=host, port=port, community=community, base_oid=OID_IF_IN_OCTETS_BASE, timeout=timeout)
    if_out_walk, _ = await snmp_walk_table(host=host, port=port, community=community, base_oid=OID_IF_OUT_OCTETS_BASE, timeout=timeout)
    if_in_err_walk, _ = await snmp_walk_table(host=host, port=port, community=community, base_oid=OID_IF_IN_ERRORS_BASE, timeout=timeout)
    if_out_err_walk, _ = await snmp_walk_table(host=host, port=port, community=community, base_oid=OID_IF_OUT_ERRORS_BASE, timeout=timeout)
    if_in_disc_walk, _ = await snmp_walk_table(host=host, port=port, community=community, base_oid=OID_IF_IN_DISCARDS_BASE, timeout=timeout)
    if_out_disc_walk, _ = await snmp_walk_table(host=host, port=port, community=community, base_oid=OID_IF_OUT_DISCARDS_BASE, timeout=timeout)

    oper_map = {oid.split(".")[-1]: val for oid, val in if_oper_walk}
    admin_map = {oid.split(".")[-1]: val for oid, val in if_admin_walk}
    type_map = {oid.split(".")[-1]: val for oid, val in if_type_walk}
    speed_map = {oid.split(".")[-1]: _safe_int(val, 0) for oid, val in if_speed_walk}
    hspeed_map = {oid.split(".")[-1]: _safe_int(val, 0) for oid, val in if_hspeed_walk}
    hcin_map = {oid.split(".")[-1]: _safe_int(val, -1) for oid, val in if_hcin_walk}
    hcout_map = {oid.split(".")[-1]: _safe_int(val, -1) for oid, val in if_hcout_walk}
    in_map = {oid.split(".")[-1]: _safe_int(val, 0) for oid, val in if_in_walk}
    out_map = {oid.split(".")[-1]: _safe_int(val, 0) for oid, val in if_out_walk}
    in_err_map = {oid.split(".")[-1]: _safe_int(val, 0) for oid, val in if_in_err_walk}
    out_err_map = {oid.split(".")[-1]: _safe_int(val, 0) for oid, val in if_out_err_walk}
    in_disc_map = {oid.split(".")[-1]: _safe_int(val, 0) for oid, val in if_in_disc_walk}
    out_disc_map = {oid.split(".")[-1]: _safe_int(val, 0) for oid, val in if_out_disc_walk}

    interfaces = []
    for oid, name in if_descr_walk:
        idx = oid.split(".")[-1]
        oper_val = oper_map.get(idx, "4")
        oper_str = "up" if oper_val == "1" else ("down" if oper_val == "2" else "unknown")
        admin_val = admin_map.get(idx, "1")
        admin_str = "disabled" if admin_val == "2" else "enabled"

        # Tentukan link speed ternegosiasi sebenarnya (hanya jika port operasional UP)
        h_bps = hspeed_map.get(idx, 0) * 1_000_000
        raw_speed = h_bps if h_bps > 0 else speed_map.get(idx, 0)

        negotiated_speed_bps = raw_speed if (oper_str == "up" and raw_speed > 0) else None
        speed_src = "snmp_if_speed" if negotiated_speed_bps is not None else "unknown"

        interfaces.append({
            "name": name,
            "type": "ethernet" if type_map.get(idx) == "6" else ("wireless" if type_map.get(idx) == "71" else "unknown"),
            "admin_status": admin_str,
            "oper_status": oper_str,
            "negotiated_speed_bps": negotiated_speed_bps,
            "maximum_capability_bps": None,
            "reported_speed_bps": negotiated_speed_bps,
            "speed_source": speed_src,
            "speed_updated_at": time.time() if negotiated_speed_bps is not None else None,
            "speed_bps": negotiated_speed_bps or 0,
            "duplex": "unknown",
            "in_octets": hcin_map.get(idx, -1) if hcin_map.get(idx, -1) >= 0 else in_map.get(idx, 0),
            "out_octets": hcout_map.get(idx, -1) if hcout_map.get(idx, -1) >= 0 else out_map.get(idx, 0),
            "in_errors": in_err_map.get(idx, 0),
            "out_errors": out_err_map.get(idx, 0),
            "in_drops": in_disc_map.get(idx, 0),
            "out_drops": out_disc_map.get(idx, 0),
        })

    result["interfaces"] = interfaces
    return result
