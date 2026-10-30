"""
Unit tests for core/canonical_network.py
"""

import pytest
from core.canonical_network import (
    CanonicalDevice,
    CanonicalNetworkRegistry,
    parse_routeros_major_version,
)


def test_parse_routeros_major_version():
    assert parse_routeros_major_version("7.14.3 (stable)") == 7
    assert parse_routeros_major_version("v7.12") == 7
    assert parse_routeros_major_version("6.49.10") == 6
    assert parse_routeros_major_version("RouterOS 6.48.6") == 6
    assert parse_routeros_major_version("Linux 5.15") is None
    assert parse_routeros_major_version("") is None


def test_canonical_device_display_name_precedence():
    # 1. Custom override wins
    d1 = CanonicalDevice(
        device_id="dev_r1",
        inventory_name="R1",
        observed_identity="MikroTik-Main",
        management_ip="192.168.1.1",
        user_overrides={"custom_name": "Gateway-Office"},
    )
    assert d1.display_name == "Gateway-Office"

    # 2. Inventory name wins over observed identity
    d2 = CanonicalDevice(
        device_id="dev_r1",
        inventory_name="R1",
        observed_identity="MikroTik-Main",
        management_ip="192.168.1.1",
    )
    assert d2.display_name == "R1"

    # 3. Observed identity used when no inventory name
    d3 = CanonicalDevice(
        device_id="dev_r1",
        inventory_name="",
        observed_identity="MikroTik-Main",
        management_ip="192.168.1.1",
    )
    assert d3.display_name == "MikroTik-Main"

    # 4. Fallback to IP or device_id
    d4 = CanonicalDevice(
        device_id="dev_r1",
        inventory_name="",
        observed_identity="",
        management_ip="192.168.1.1",
    )
    assert d4.display_name == "192.168.1.1"


def test_canonical_device_to_dict():
    dev = CanonicalDevice(
        device_id="dev_test",
        inventory_name="Test-Router",
        management_ip="10.10.10.1",
        primary_mac="00:11:22:33:44:55",
        all_macs=["00:11:22:33:44:55", "00:11:22:33:44:56"],
        os_version="7.13",
        ros_major_version=7,
    )
    data = dev.to_dict()
    assert data["device_id"] == "dev_test"
    assert data["display_name"] == "Test-Router"
    assert data["management_ip"] == "10.10.10.1"
    assert data["ros_major_version"] == 7
    assert len(data["all_macs"]) == 2


def test_canonical_registry_resolution():
    registry = CanonicalNetworkRegistry()
    devs = registry.list_devices(force_refresh=True)
    assert isinstance(devs, list)

    # Resolution by name or IP
    r1 = registry.resolve_device("R1")
    if r1:
        assert r1.inventory_name == "R1"
        by_ip = registry.resolve_device(r1.management_ip)
        assert by_ip is not None
        assert by_ip.device_id == r1.device_id
