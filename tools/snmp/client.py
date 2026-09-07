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


async def _snmp_get_async(host, port, community, oid_map):

    engine = SnmpEngine()

    labels = list(oid_map.keys())
    oids = list(oid_map.values())

    object_types = [
        ObjectType(ObjectIdentity(oid)) for oid in oids
    ]

    transport = await UdpTransportTarget.create(
        (host, port),
        timeout=SNMP_TIMEOUT,
        retries=SNMP_RETRIES
    )

    error_indication, error_status, error_index, var_binds = await get_cmd(
        engine,
        CommunityData(community, mpModel=1),  # mpModel=1 -> SNMPv2c
        transport,
        ContextData(),
        *object_types
    )

    _close_engine(engine)

    if error_indication:
        return None, str(error_indication)

    if error_status:
        return None, error_status.prettyPrint()

    result = {}

    for label, var_bind in zip(labels, var_binds):
        result[label] = str(var_bind[1])

    return result, None


async def _snmp_walk_async(host, port, community, base_oid):

    engine = SnmpEngine()

    transport = await UdpTransportTarget.create(
        (host, port),
        timeout=SNMP_TIMEOUT,
        retries=SNMP_RETRIES
    )

    community_data = CommunityData(community, mpModel=1)
    context = ContextData()

    results = []
    current = ObjectType(ObjectIdentity(base_oid))

    while True:

        error_indication, error_status, error_index, var_binds = await next_cmd(
            engine,
            community_data,
            transport,
            context,
            current
        )

        if error_indication:
            _close_engine(engine)
            return results, str(error_indication)

        if error_status:
            _close_engine(engine)
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

    _close_engine(engine)

    return results, None


def _close_engine(engine):

    try:
        engine.close_dispatcher()
    except Exception:
        pass


def snmp_get(device_name, oid_map):
    """
    oid_map: dict {label: oid_string}
    Mengambil beberapa OID sekaligus dalam satu request GET.
    """

    device, error = _get_device(device_name)

    if error:
        return error

    community = _get_community(device)
    port = device.get("snmp_port", 161)

    try:

        result, err = asyncio.run(
            _snmp_get_async(
                device["host"],
                port,
                community,
                oid_map
            )
        )

    except Exception as exc:

        return {
            "success": False,
            "error": str(exc)
        }

    if err:

        return {
            "success": False,
            "error": err
        }

    return {
        "success": True,
        "values": result
    }


def snmp_walk(device_name, base_oid):
    """
    Melakukan SNMP walk dari base_oid.
    Mengembalikan list of (oid_str, value).
    """

    device, error = _get_device(device_name)

    if error:
        return error

    community = _get_community(device)
    port = device.get("snmp_port", 161)

    try:

        results, err = asyncio.run(
            _snmp_walk_async(
                device["host"],
                port,
                community,
                base_oid
            )
        )

    except Exception as exc:

        return {
            "success": False,
            "error": str(exc)
        }

    if err:

        return {
            "success": False,
            "error": err
        }

    return {
        "success": True,
        "values": results
    }