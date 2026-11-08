"""
tests/test_networking_iii_inventory.py — Unit tests for Phase Networking III Multi-Device Inventory.
"""

import time
import pytest
from core.canonical_network import (
    CanonicalDevice,
    CanonicalNetworkRegistry,
)
from core.inventory_store import get_inventory_store


def test_canonical_device_multi_device_attributes():
    dev = CanonicalDevice(
        device_id="dev_chr_01",
        inventory_name="CHR-Core",
        observed_identity="MikroTik-RouterOS-v7",
        hostname="chr-core.lab.local",
        management_ip="192.168.43.30",
        management_port=22,
        management_protocol="ssh",
        all_ips=["192.168.43.30", "10.0.0.1"],
        primary_mac="08:00:27:CC:21:02",
        all_macs=["08:00:27:CC:21:02", "00:00:00:00:00:00"],
        device_type="mikrotik",
        vendor="MikroTik",
        manufacturer="MikroTik SIA",
        model="CHR innotek GmbH VirtualBox",
        platform="x86_64",
        os_version="7.23.8 (long-term)",
        ros_major_version=7,
        connection_status="connected",
        device_role="core_router",
        tags=["lab", "chr", "v7"],
        location="Lab Rack 1",
        site="HQ",
        description="Core CHR test appliance",
        notes="Primary RouterOS v7 target",
        user_overrides={"custom_name": "Primary-CHR"},
        discovered_metadata={"firmware": "7.23.8", "cpu_count": 1},
    )

    # 1. User override takes precedence for display_name
    assert dev.display_name == "Primary-CHR"
    assert dev.inventory_name == "CHR-Core"
    assert dev.observed_identity == "MikroTik-RouterOS-v7"

    # 2. Serialization includes all conceptual multi-device fields
    d_dict = dev.to_dict()
    assert d_dict["device_id"] == "dev_chr_01"
    assert d_dict["hostname"] == "chr-core.lab.local"
    assert d_dict["vendor"] == "MikroTik"
    assert d_dict["manufacturer"] == "MikroTik SIA"
    assert d_dict["model"] == "CHR innotek GmbH VirtualBox"
    assert d_dict["platform"] == "x86_64"
    assert d_dict["ros_major_version"] == 7
    assert d_dict["device_role"] == "core_router"
    assert "lab" in d_dict["tags"]
    assert d_dict["location"] == "Lab Rack 1"
    assert d_dict["discovered_metadata"]["cpu_count"] == 1


def _ensure_chr_device():
    inv = get_inventory_store()
    if not inv.get_device("CHR").get("success"):
        inv.create_device(
            name="CHR",
            host="192.168.43.30",
            port=22,
            username="admin",
            device_type="mikrotik",
        )


def test_canonical_network_registry_batch_resolution():
    _ensure_chr_device()
    reg = CanonicalNetworkRegistry()
    devices = reg.list_devices()
    assert len(devices) > 0

    queries = ["CHR", "non-existent-device-999"]
    resolved = reg.resolve_devices_batch(queries)

    # Expect found device returned, unknown omitted, no duplicates
    assert len(resolved) >= 1
    resolved_names = [d.inventory_name for d in resolved]
    assert "CHR" in resolved_names


def test_inventory_store_batch_lookup_and_validation():
    _ensure_chr_device()
    inv = get_inventory_store()

    # 1. Payload validation
    ok, err = inv.validate_device_payload("Valid-R1", "10.10.10.1", 22, "admin")
    assert ok is True
    assert err is None

    # Invalid payload (empty name)
    ok_bad, err_bad = inv.validate_device_payload("", "10.10.10.1")
    assert ok_bad is False
    assert "nama device" in str(err_bad).lower()

    # Invalid port
    ok_port, err_port = inv.validate_device_payload("R-Port", "10.10.10.1", 99999)
    assert ok_port is False

    # 2. Batch device retrieval
    batch_res = inv.get_devices_batch(["CHR", "Ghost-Device-999"])
    assert batch_res["success"] is True
    assert batch_res["count"] == 1
    names = [d["name"] for d in batch_res["devices"]]
    assert "CHR" in names
    assert "Ghost-Device-999" in batch_res["missing"]


def test_duplicate_device_registration_safety():
    _ensure_chr_device()
    inv = get_inventory_store()
    # Attempting to register existing device 'CHR' must fail gracefully
    dup_res = inv.create_device(
        name="CHR",
        host="192.168.43.30",
        port=22,
        username="admin",
    )
    assert dup_res.get("success") is False
    err_msg = str(dup_res.get("error")).lower()
    assert "sudah ada" in err_msg or "sudah terdaftar" in err_msg or "unique" in err_msg
