import os
import asyncio

from pysnmp.hlapi.v3arch.asyncio import (
    SnmpEngine,
    CommunityData,
    UdpTransportTarget,
    ContextData,
    ObjectType,
    ObjectIdentity,
    get_cmd,
    next_cmd,
)

from tools.ssh.client import load_inventory, resolve_device_name


SNMP_TIMEOUT = 5
SNMP_RETRIES = 1


def _get_device(device_name):

    inventory = load_inventory()
    devices = inventory.get("devices", {})

    resolved_name = resolve_device_name(
        device_name,
        devices
    )

    if resolved_name is None:

        available = ", ".join(devices.keys()) or "(kosong)"

        return None, {
            "success": False,
            "error": (
                f"Device '{device_name}' tidak ditemukan. "
                f"Device yang terdaftar: {available}."
            )
        }

    return devices[resolved_name], None


def _get_community(device):

    return (
        device.get("snmp_community")
        or os.getenv("SNMP_COMMUNITY")
        or "public"
    )


async def _snmp_get_async(engine, transport, community, oid_map):

    labels = list(oid_map.keys())
    oids = list(oid_map.values())

    object_types = [
        ObjectType(ObjectIdentity(oid)) for oid in oids
    ]

    error_indication, error_status, error_index, var_binds = await get_cmd(
        engine,
        community,
        transport,
        ContextData(),
        *object_types
    )

    if error_indication:
        return None, str(error_indication)

    if error_status:
        return None, error_status.prettyPrint()

    result = {}

    for label, var_bind in zip(labels, var_binds):
        result[label] = str(var_bind[1])

    return result, None


async def _snmp_walk_async(engine, transport, community, base_oid):

    results = []
    current = ObjectType(ObjectIdentity(base_oid))

    while True:

        error_indication, error_status, error_index, var_binds = await next_cmd(
            engine,
            community,
            transport,
            ContextData(),
            current
        )

        if error_indication:
            return results, str(error_indication)

        if error_status:
            return results, error_status.prettyPrint()

        if not var_binds:
            break

        var_bind = var_binds[0]
        oid_str = str(var_bind[0])

        # Berhenti kalau OID sudah keluar dari subtree base_oid
        # (tanda SNMP walk sudah sampai akhir tabel).
        if not (
            oid_str == base_oid
            or oid_str.startswith(base_oid + ".")
        ):
            break

        results.append((
            oid_str,
            str(var_bind[1])
        ))

        current = ObjectType(ObjectIdentity(oid_str))

    return results, None


async def _run_batch(host, port, community, gets, walks):
    """
    Menjalankan beberapa operasi GET/WALK sekaligus secara
    CONCURRENT dalam satu SnmpEngine + satu transport, bukan
    satu per satu (sequential asyncio.run per operasi seperti
    sebelumnya). Ini yang paling mempercepat get_system_info
    dan get_interface_traffic, karena aslinya masing-masing
    butuh 4-5 round-trip SNMP yang tadinya dieksekusi berurutan.
    """

    engine = SnmpEngine()

    community_data = CommunityData(
        community,
        mpModel=1  # mpModel=1 -> SNMPv2c
    )

    transport = await UdpTransportTarget.create(
        (host, port),
        timeout=SNMP_TIMEOUT,
        retries=SNMP_RETRIES
    )

    tasks = {}

    for key, oid_map in gets.items():
        tasks[key] = asyncio.create_task(
            _snmp_get_async(engine, transport, community_data, oid_map)
        )

    for key, base_oid in walks.items():
        tasks[key] = asyncio.create_task(
            _snmp_walk_async(engine, transport, community_data, base_oid)
        )

    results = {}

    for key, task in tasks.items():
        value, err = await task
        results[key] = {"value": value, "error": err}

    try:
        engine.close_dispatcher()
    except Exception:
        pass

    return results


def snmp_batch(device_name, gets=None, walks=None):
    """
    Menjalankan beberapa operasi SNMP GET/WALK sekaligus terhadap
    satu device dalam satu koneksi, secara concurrent.

    gets: dict {key: {label: oid, ...}}
    walks: dict {key: base_oid}

    Return:
      {"success": True, "results": {key: {"value":..., "error":...}}}
      atau {"success": False, "error": "..."}
    """

    device, error = _get_device(device_name)

    if error:
        return error

    community = _get_community(device)
    port = device.get("snmp_port", 161)

    gets = gets or {}
    walks = walks or {}

    try:

        results = asyncio.run(
            _run_batch(
                device["host"],
                port,
                community,
                gets,
                walks
            )
        )

    except Exception as exc:

        return {
            "success": False,
            "error": str(exc)
        }

    return {
        "success": True,
        "results": results
    }


# -------------------------------------------------------------
# Helper sederhana untuk satu operasi saja (dipertahankan untuk
# kompatibilitas / kebutuhan ad-hoc satu OID/table).
# -------------------------------------------------------------

def snmp_get(device_name, oid_map):

    result = snmp_batch(device_name, gets={"_single": oid_map})

    if not result.get("success"):
        return result

    entry = result["results"]["_single"]

    if entry["error"]:
        return {"success": False, "error": entry["error"]}

    return {"success": True, "values": entry["value"]}


def snmp_walk(device_name, base_oid):

    result = snmp_batch(device_name, walks={"_single": base_oid})

    if not result.get("success"):
        return result

    entry = result["results"]["_single"]

    if entry["error"]:
        return {"success": False, "error": entry["error"]}

    return {"success": True, "values": entry["value"]}