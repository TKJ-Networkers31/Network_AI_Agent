from tools.ssh.client import ssh_execute


COMMANDS = {

    "get_interfaces":
        "/interface print",

    "get_ip_addresses":
        "/ip address print",

    "get_routes":
        "/ip route print",

    "get_firewall":
        "/ip firewall filter print",

    "get_resources":
        "/system resource print",

    "get_identity":
        "/system identity print",

    "get_dns":
        "/ip dns print",

    "get_dhcp_client":
        "/ip dhcp-client print",

    "get_dhcp_server":
        "/ip dhcp-server print",

    "get_nat":
        "/ip firewall nat print",

    "get_neighbors":
        "/ip neighbor print",

    "get_arp":
        "/ip arp print",

}


def execute_mikrotik_tool(
    tool_name,
    device_name
):

    if tool_name not in COMMANDS:

        return {
            "success": False,
            "error": (
                f"Tool MikroTik "
                f"'{tool_name}' tidak tersedia."
            )
        }

    command = COMMANDS[
        tool_name
    ]

    result = ssh_execute(
        device_name,
        command
    )

    return {
        **result,
        "tool": tool_name,
        "category": "mikrotik"
    }


def get_interfaces(device_name):
    return execute_mikrotik_tool(
        "get_interfaces",
        device_name
    )


def get_ip_addresses(device_name):
    return execute_mikrotik_tool(
        "get_ip_addresses",
        device_name
    )


def get_routes(device_name):
    return execute_mikrotik_tool(
        "get_routes",
        device_name
    )


def get_firewall(device_name):
    return execute_mikrotik_tool(
        "get_firewall",
        device_name
    )


def get_resources(device_name):
    return execute_mikrotik_tool(
        "get_resources",
        device_name
    )


def get_identity(device_name):
    return execute_mikrotik_tool(
        "get_identity",
        device_name
    )


def get_dns(device_name):
    return execute_mikrotik_tool(
        "get_dns",
        device_name
    )


def get_dhcp_client(device_name):
    return execute_mikrotik_tool(
        "get_dhcp_client",
        device_name
    )


def get_dhcp_server(device_name):
    return execute_mikrotik_tool(
        "get_dhcp_server",
        device_name
    )


def get_nat(device_name):
    return execute_mikrotik_tool(
        "get_nat",
        device_name
    )


def get_neighbors(device_name):
    return execute_mikrotik_tool(
        "get_neighbors",
        device_name
    )


def get_arp(device_name):
    return execute_mikrotik_tool(
        "get_arp",
        device_name
    )