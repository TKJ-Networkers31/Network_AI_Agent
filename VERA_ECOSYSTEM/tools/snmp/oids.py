# OID standar (MIB-2 / HOST-RESOURCES-MIB / IF-MIB) yang
# didukung RouterOS SNMP agent secara default.

SYSTEM_OIDS = {
    "sys_description": "1.3.6.1.2.1.1.1.0",
    "sys_uptime": "1.3.6.1.2.1.1.3.0",
    "sys_name": "1.3.6.1.2.1.1.5.0",
}

# HOST-RESOURCES-MIB: hrProcessorLoad (per core, di-walk)
CPU_LOAD_BASE_OID = "1.3.6.1.2.1.25.3.3.1.2"

# HOST-RESOURCES-MIB: hrStorage table (dipakai untuk cari memory)
STORAGE_DESCR_BASE_OID = "1.3.6.1.2.1.25.2.3.1.3"
STORAGE_SIZE_BASE_OID = "1.3.6.1.2.1.25.2.3.1.5"
STORAGE_USED_BASE_OID = "1.3.6.1.2.1.25.2.3.1.6"

# IF-MIB: interface table
IF_DESCR_BASE_OID = "1.3.6.1.2.1.2.2.1.2"
IF_OPER_STATUS_BASE_OID = "1.3.6.1.2.1.2.2.1.8"
IF_IN_OCTETS_BASE_OID = "1.3.6.1.2.1.2.2.1.10"
IF_OUT_OCTETS_BASE_OID = "1.3.6.1.2.1.2.2.1.16"

IF_OPER_STATUS_LABEL = {
    "1": "up",
    "2": "down",
    "3": "testing",
    "4": "unknown",
    "5": "dormant",
    "6": "notPresent",
    "7": "lowerLayerDown",
}