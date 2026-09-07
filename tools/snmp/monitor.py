from tools.snmp.client import snmp_get, snmp_walk
from tools.snmp import oids as O


def get_system_info(device_name):

    base_result = snmp_get(
        device_name,
        O.SYSTEM_OIDS
    )

    if not base_result.get("success"):

        return {
            **base_result,
            "tool": "get_system_info",
            "category": "snmp",
        }

    values = base_result["values"]

    cpu_walk = snmp_walk(
        device_name,
        O.CPU_LOAD_BASE_OID
    )

    cpu_cores = []

    if cpu_walk.get("success"):

        for _, value in cpu_walk["values"]:

            try:
                cpu_cores.append(int(value))
            except ValueError:
                pass

    avg_cpu = (
        round(sum(cpu_cores) / len(cpu_cores), 1)
        if cpu_cores else None
    )

    memory_info = _get_memory_usage(
        device_name
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


def _get_memory_usage(device_name):

    descr_walk = snmp_walk(device_name, O.STORAGE_DESCR_BASE_OID)
    size_walk = snmp_walk(device_name, O.STORAGE_SIZE_BASE_OID)
    used_walk = snmp_walk(device_name, O.STORAGE_USED_BASE_OID)

    if not (
        descr_walk.get("success")
        and size_walk.get("success")
        and used_walk.get("success")
    ):
        return None

    for (
        (_, descr_val),
        (_, size_val),
        (_, used_val)
    ) in zip(
        descr_walk["values"],
        size_walk["values"],
        used_walk["values"],
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

    descr_walk = snmp_walk(
        device_name,
        O.IF_DESCR_BASE_OID
    )

    if not descr_walk.get("success"):

        return {
            **descr_walk,
            "tool": "get_interface_traffic",
            "category": "snmp",
        }

    status_walk = snmp_walk(device_name, O.IF_OPER_STATUS_BASE_OID)
    in_walk = snmp_walk(device_name, O.IF_IN_OCTETS_BASE_OID)
    out_walk = snmp_walk(device_name, O.IF_OUT_OCTETS_BASE_OID)

    interfaces = []

    for i, (_, descr_val) in enumerate(descr_walk["values"]):

        status_val = (
            status_walk["values"][i][1]
            if status_walk.get("success")
            and i < len(status_walk["values"])
            else None
        )

        in_val = (
            in_walk["values"][i][1]
            if in_walk.get("success")
            and i < len(in_walk["values"])
            else None
        )

        out_val = (
            out_walk["values"][i][1]
            if out_walk.get("success")
            and i < len(out_walk["values"])
            else None
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