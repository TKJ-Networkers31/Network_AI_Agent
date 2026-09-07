from tools.snmp.client import snmp_batch
from tools.snmp import oids as O


def get_system_info(device_name):

    batch = snmp_batch(
        device_name,
        gets={
            "system": O.SYSTEM_OIDS,
        },
        walks={
            "cpu": O.CPU_LOAD_BASE_OID,
            "mem_descr": O.STORAGE_DESCR_BASE_OID,
            "mem_size": O.STORAGE_SIZE_BASE_OID,
            "mem_used": O.STORAGE_USED_BASE_OID,
        }
    )

    if not batch.get("success"):

        return {
            **batch,
            "tool": "get_system_info",
            "category": "snmp",
        }

    results = batch["results"]
    system_entry = results["system"]

    if system_entry["error"]:

        return {
            "success": False,
            "tool": "get_system_info",
            "category": "snmp",
            "error": system_entry["error"],
        }

    values = system_entry["value"] or {}

    cpu_cores = []

    if not results["cpu"]["error"]:

        for _, value in (results["cpu"]["value"] or []):

            try:
                cpu_cores.append(int(value))
            except ValueError:
                pass

    avg_cpu = (
        round(sum(cpu_cores) / len(cpu_cores), 1)
        if cpu_cores else None
    )

    memory_info = _extract_memory_usage(
        results["mem_descr"],
        results["mem_size"],
        results["mem_used"],
    )

    return {
        "success": True,
        "tool": "get_system_info",
        "category": "snmp",
        "device": device_name,
        "system_description": values.get("sys_description"),
        "system_name": values.get("sys_name"),
        "uptime_ticks": values.get("sys_uptime"),
        "cpu_load_percent_per_core": cpu_cores,
        "cpu_load_percent_avg": avg_cpu,
        "memory": memory_info,
    }


def _extract_memory_usage(descr_entry, size_entry, used_entry):

    if descr_entry["error"] or size_entry["error"] or used_entry["error"]:
        return None

    descr_walk = descr_entry["value"] or []
    size_walk = size_entry["value"] or []
    used_walk = used_entry["value"] or []

    for (
        (_, descr_val),
        (_, size_val),
        (_, used_val)
    ) in zip(
        descr_walk,
        size_walk,
        used_walk,
    ):

        if (
            "memory" in descr_val.lower()
            or "ram" in descr_val.lower()
        ):

            try:
                size = int(size_val)
                used = int(used_val)
            except ValueError:
                continue

            return {
                "description": descr_val,
                "used_units": used,
                "size_units": size,
                "used_percent": (
                    round(used / size * 100, 1)
                    if size else None
                ),
            }

    return None


def get_interface_traffic(device_name):

    batch = snmp_batch(
        device_name,
        walks={
            "descr": O.IF_DESCR_BASE_OID,
            "status": O.IF_OPER_STATUS_BASE_OID,
            "in": O.IF_IN_OCTETS_BASE_OID,
            "out": O.IF_OUT_OCTETS_BASE_OID,
        }
    )

    if not batch.get("success"):

        return {
            **batch,
            "tool": "get_interface_traffic",
            "category": "snmp",
        }

    results = batch["results"]
    descr_entry = results["descr"]

    if descr_entry["error"]:

        return {
            "success": False,
            "tool": "get_interface_traffic",
            "category": "snmp",
            "error": descr_entry["error"],
        }

    descr_walk = descr_entry["value"] or []

    status_walk = (
        results["status"]["value"] or []
        if not results["status"]["error"] else []
    )

    in_walk = (
        results["in"]["value"] or []
        if not results["in"]["error"] else []
    )

    out_walk = (
        results["out"]["value"] or []
        if not results["out"]["error"] else []
    )

    interfaces = []

    for i, (_, descr_val) in enumerate(descr_walk):

        status_val = (
            status_walk[i][1] if i < len(status_walk) else None
        )

        in_val = (
            in_walk[i][1] if i < len(in_walk) else None
        )

        out_val = (
            out_walk[i][1] if i < len(out_walk) else None
        )

        interfaces.append({
            "name": descr_val,
            "status": O.IF_OPER_STATUS_LABEL.get(
                status_val,
                status_val
            ),
            "in_octets": in_val,
            "out_octets": out_val,
        })

    return {
        "success": True,
        "tool": "get_interface_traffic",
        "category": "snmp",
        "device": device_name,
        "interfaces": interfaces,
    }