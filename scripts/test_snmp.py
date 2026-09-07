from tools.snmp.monitor import (
    get_system_info,
    get_interface_traffic,
)


print("=== System Info ===")
info = get_system_info("R1")
print(info)

print()
print("=== Interface Traffic ===")
traffic = get_interface_traffic("R1")
print(traffic)