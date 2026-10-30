"""
tests/test_nms.py — Comprehensive Automated Verification Suite for AIRA OS
Network Management System & Live Topology Monitoring (NMS).

Covers:
1. Rate Calculation & Rollover Formulas (32-bit & 64-bit counter wraparound, spikes)
2. Availability State Machine Transitions (UP, SUSPECTED_DOWN, DOWN, DEGRADED, MONITORING_UNAVAILABLE, MAINTENANCE)
3. NmsEngine Database Schema, Migration & Persistence
4. Single-Flight Concurrency & Background Scheduler Lifecycle
5. Incident Generation, Deduplication, Acknowledgment & Automatic Resolution on Recovery
6. SNMP Setup Wizard (Detection, Secure Command Generation, Verification & Saving)
7. REST API Endpoints Contract via FastAPI TestClient (Overview, Settings, Devices, History, Incidents, Wizard)

Hermetic: Uses temporary SQLite databases and mocked ICMP / SNMP calls.
"""

from __future__ import annotations

import asyncio
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.routers.nms as nms_router_module
from core.nms_engine import NmsEngine
from core.nms_models import (
    DEFAULT_NMS_SETTINGS,
    UINT32_MAX,
    UINT64_MAX,
    calculate_traffic_rate,
    determine_device_availability,
    is_check_stale,
    resolve_device_display_name,
)
from core.topology_parsers import (
    parse_mikrotik_ethernet,
    parse_mikrotik_identity,
    parse_speed_to_bps,
)


class TestNmsRateCalculation(unittest.TestCase):
    """Test suite for bandwidth calculation, counter wraparound, and utilization metrics."""

    def test_normal_rate_calculation(self):
        # 1,000,000 bytes delta over 10 seconds = 100,000 B/s = 800,000 bps
        rate_bps, util = calculate_traffic_rate(
            curr_octets=2_000_000,
            prev_octets=1_000_000,
            curr_time=20.0,
            prev_time=10.0,
            speed_bps=10_000_000,  # 10 Mbps
        )
        self.assertEqual(rate_bps, 800_000.0)
        self.assertEqual(util, 8.0)  # 800k / 10M = 8%

    def test_zero_or_negative_time_delta_handled_safely(self):
        rate_bps, util = calculate_traffic_rate(
            curr_octets=2_000_000,
            prev_octets=1_000_000,
            curr_time=10.0,
            prev_time=10.0,
        )
        self.assertEqual(rate_bps, 0.0)
        self.assertIsNone(util)

    def test_none_octets_handled_safely(self):
        rate_bps, util = calculate_traffic_rate(
            curr_octets=None,
            prev_octets=1000,
            curr_time=15.0,
            prev_time=10.0,
        )
        self.assertEqual(rate_bps, 0.0)
        self.assertIsNone(util)

    def test_32bit_counter_rollover(self):
        # prev is near 2^32 - 1, curr wrapped around to 10,000
        prev_octets = UINT32_MAX - 5000  # 4294962295
        curr_octets = 10_000
        # Expected delta: (UINT32_MAX - prev) + curr + 1 = 5000 + 10000 + 1 = 15001 bytes
        rate_bps, _ = calculate_traffic_rate(
            curr_octets=curr_octets,
            prev_octets=prev_octets,
            curr_time=10.0,
            prev_time=9.0,  # 1 second
        )
        expected_bps = 15001 * 8.0
        self.assertEqual(rate_bps, expected_bps)

    def test_64bit_counter_rollover(self):
        # 64-bit high counter wrapped around
        prev_octets = UINT64_MAX - 10000
        curr_octets = 20000
        rate_bps, _ = calculate_traffic_rate(
            curr_octets=curr_octets,
            prev_octets=prev_octets,
            curr_time=2.0,
            prev_time=1.0,
        )
        expected_bps = (10000 + 20000 + 1) * 8.0
        self.assertEqual(rate_bps, expected_bps)

    def test_router_reboot_counter_reset_suppressed(self):
        # Massive drop that exceeds reasonable throughput (e.g. 100 Gbps threshold)
        rate_bps, _ = calculate_traffic_rate(
            curr_octets=100,
            prev_octets=1_000_000_000,
            curr_time=10.0,
            prev_time=9.0,  # 1 sec elapsed
        )
        # Should be gated to 0.0 to prevent false traffic spikes
        self.assertEqual(rate_bps, 0.0)


class TestNmsAvailabilityStateMachine(unittest.TestCase):
    """Test suite for device availability state machine transitions."""

    def test_transition_unknown_to_up(self):
        st, fails, succs = determine_device_availability(
            current_status="UNKNOWN",
            consecutive_failures=0,
            consecutive_successes=0,
            ping_ok=True,
            management_ok=True,
            is_managed=True,
        )
        self.assertEqual(st, "UP")
        self.assertEqual(fails, 0)
        self.assertEqual(succs, 1)

    def test_single_ping_failure_triggers_suspected_down(self):
        st, fails, succs = determine_device_availability(
            current_status="UP",
            consecutive_failures=0,
            consecutive_successes=5,
            ping_ok=False,
            management_ok=None,
            is_managed=True,
            failure_threshold=3,
        )
        self.assertEqual(st, "SUSPECTED_DOWN")
        self.assertEqual(fails, 1)
        self.assertEqual(succs, 0)

    def test_reaching_failure_threshold_triggers_down(self):
        st, fails, succs = determine_device_availability(
            current_status="SUSPECTED_DOWN",
            consecutive_failures=2,
            consecutive_successes=0,
            ping_ok=False,
            management_ok=None,
            is_managed=True,
            failure_threshold=3,
        )
        self.assertEqual(st, "DOWN")
        self.assertEqual(fails, 3)

    def test_down_requires_consecutive_successes_for_recovery(self):
        # 1 success < recovery_threshold (2) -> retains DOWN
        st, fails, succs = determine_device_availability(
            current_status="DOWN",
            consecutive_failures=3,
            consecutive_successes=0,
            ping_ok=True,
            management_ok=True,
            is_managed=True,
            recovery_threshold=2,
        )
        self.assertEqual(st, "DOWN")
        self.assertEqual(succs, 1)

        # 2nd success >= recovery_threshold -> recovers to UP
        st2, fails2, succs2 = determine_device_availability(
            current_status="DOWN",
            consecutive_failures=0,
            consecutive_successes=1,
            ping_ok=True,
            management_ok=True,
            is_managed=True,
            recovery_threshold=2,
        )
        self.assertEqual(st2, "UP")
        self.assertEqual(succs2, 2)

    def test_managed_device_with_management_down_reports_monitoring_unavailable(self):
        st, _, _ = determine_device_availability(
            current_status="UP",
            consecutive_failures=0,
            consecutive_successes=2,
            ping_ok=True,
            management_ok=False,  # Ping UP, but SNMP/API down
            is_managed=True,
        )
        self.assertEqual(st, "MONITORING_UNAVAILABLE")

    def test_maintenance_mode_overrides_status(self):
        st, _, _ = determine_device_availability(
            current_status="DOWN",
            consecutive_failures=5,
            consecutive_successes=0,
            ping_ok=False,
            management_ok=False,
            is_managed=True,
            is_maintenance=True,
        )
        self.assertEqual(st, "MAINTENANCE")

    def test_paused_device_returns_unknown(self):
        st, _, _ = determine_device_availability(
            current_status="UP",
            consecutive_failures=0,
            consecutive_successes=5,
            ping_ok=True,
            management_ok=True,
            is_managed=True,
            is_paused=True,
        )
        self.assertEqual(st, "UNKNOWN")


class TestNmsEngine(unittest.TestCase):
    """Test suite for NmsEngine database operations, polling cycle, incidents, and wizard."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self.temp_dir.name) / "test_nms.db"

        # Create topology_nodes in DB first to test automatic sync
        conn = sqlite3.connect(str(self.db_path))
        conn.executescript(
            """
            CREATE TABLE topology_nodes (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                identity TEXT,
                ip TEXT,
                mac TEXT,
                device_type TEXT DEFAULT 'router',
                ownership_status TEXT DEFAULT 'verified_owned',
                reachability_status TEXT DEFAULT 'online',
                pos_x REAL DEFAULT 0.0,
                pos_y REAL DEFAULT 0.0,
                last_seen REAL
            );
            INSERT INTO topology_nodes (id, name, identity, ip, mac, device_type)
            VALUES ('router_core', 'MikroTik CCR2004', 'CCR-Core', '192.168.88.1', '48:8F:5A:11:22:33', 'router');
            INSERT INTO topology_nodes (id, name, identity, ip, mac, device_type)
            VALUES ('switch_sw1', 'MikroTik CRS326', 'CRS-SW1', '192.168.88.2', '48:8F:5A:44:55:66', 'switch');
            """
        )
        conn.commit()
        conn.close()

        self.engine = NmsEngine(self.db_path)

    def tearDown(self):
        self.engine.stop_monitoring()
        self.temp_dir.cleanup()

    def test_init_db_and_sync_topology_nodes(self):
        overview = self.engine.get_overview()
        self.assertEqual(overview["total_devices"], 2)
        self.assertEqual(overview["unknown"], 2)
        self.assertEqual(overview["unmanaged"], 2)

    def test_settings_persistence(self):
        settings = self.engine.get_settings()
        self.assertEqual(settings["default_interval_sec"], 15)

        updated = self.engine.update_settings({"default_interval_sec": 30, "failure_threshold": 5})
        self.assertEqual(updated["default_interval_sec"], 30)
        self.assertEqual(updated["failure_threshold"], 5)

        fresh = self.engine.get_settings()
        self.assertEqual(fresh["default_interval_sec"], 30)
        self.assertEqual(fresh["failure_threshold"], 5)

    def test_update_and_get_device_detail(self):
        ok = self.engine.update_device_profile(
            "router_core",
            {
                "management_mode": "managed",
                "snmp_enabled": 1,
                "snmp_version": "v2c",
                "snmp_community": "secure-ro",
                "snmp_port": 161,
            },
        )
        self.assertTrue(ok)

        detail = self.engine.get_device_detail("router_core")
        self.assertIsNotNone(detail)
        self.assertEqual(detail["id"], "router_core")
        self.assertEqual(detail["profile"]["management_mode"], "managed")
        self.assertTrue(detail["profile"]["snmp_enabled"])
        self.assertTrue(detail["profile"]["has_community"])

    @patch("core.nms_engine.bounded_icmp_ping")
    @patch("core.nms_engine.poll_device_snmp_full")
    def test_poll_single_device_success(self, mock_snmp, mock_ping):
        mock_ping.return_value = {"alive": True, "rtt_ms": 2.4, "packet_loss_percent": 0.0}
        mock_snmp.return_value = {
            "success": True,
            "sys_descr": "RouterOS 7.16",
            "identity": "CCR-Core",
            "uptime_seconds": 36000,
            "cpu_load_percent": 14.5,
            "memory_used_bytes": 107374182,
            "memory_total_bytes": 1073741824,
            "memory_used_percent": 10.0,
            "storage_used_bytes": 5000000,
            "storage_total_bytes": 16000000,
            "temperature_celsius": 42.0,
            "interfaces": [
                {
                    "index": 1,
                    "name": "ether1",
                    "oper_status": "up",
                    "speed_bps": 1_000_000_000,
                    "in_octets": 100000,
                    "out_octets": 200000,
                    "in_errors": 0,
                    "out_errors": 0,
                }
            ],
        }

        # Set profile to managed
        self.engine.update_device_profile("router_core", {"management_mode": "managed", "snmp_enabled": 1})
        detail = self.engine.get_device_detail("router_core")

        asyncio.run(
            self.engine.poll_single_device(
                device_id="router_core",
                host="192.168.88.1",
                profile=detail["profile"],
                settings=self.engine.get_settings(),
            )
        )

        updated_detail = self.engine.get_device_detail("router_core")
        self.assertEqual(updated_detail["profile"]["status"], "UP")
        self.assertEqual(updated_detail["latest_metrics"]["cpu_load_percent"], 14.5)
        self.assertEqual(len(updated_detail["interfaces"]), 1)
        self.assertEqual(updated_detail["interfaces"][0]["interface_name"], "ether1")

    @patch("core.nms_engine.bounded_icmp_ping")
    def test_down_detection_creates_incident_and_recovery_resolves(self, mock_ping):
        settings = self.engine.get_settings()
        settings["failure_threshold"] = 2
        settings["recovery_threshold"] = 2
        self.engine.update_settings(settings)

        # 1. Ping fails once -> SUSPECTED_DOWN, no incident yet
        mock_ping.return_value = {"alive": False, "rtt_ms": 0.0, "packet_loss_percent": 100.0}
        dev = self.engine.get_device_detail("router_core")
        asyncio.run(self.engine.poll_single_device("router_core", "192.168.88.1", dev["profile"], settings))

        dev = self.engine.get_device_detail("router_core")
        self.assertEqual(dev["profile"]["status"], "SUSPECTED_DOWN")
        incidents = self.engine.list_incidents(status="open")
        self.assertEqual(len(incidents), 0)

        # 2. Ping fails 2nd time -> DOWN (>= threshold 2), incident created!
        asyncio.run(self.engine.poll_single_device("router_core", "192.168.88.1", dev["profile"], settings))
        dev = self.engine.get_device_detail("router_core")
        self.assertEqual(dev["profile"]["status"], "DOWN")
        incidents = self.engine.list_incidents(status="open")
        self.assertEqual(len(incidents), 1)
        self.assertEqual(incidents[0]["device_id"], "router_core")
        self.assertEqual(incidents[0]["incident_type"], "device_down")
        inc_id = incidents[0]["id"]

        # 3. Third failure -> Incident is deduplicated (still only 1 open incident)
        asyncio.run(self.engine.poll_single_device("router_core", "192.168.88.1", dev["profile"], settings))
        incidents_dup = self.engine.list_incidents(status="open")
        self.assertEqual(len(incidents_dup), 1)

        # 4. First success -> Still DOWN (needs 2 successes)
        mock_ping.return_value = {"alive": True, "rtt_ms": 1.2, "packet_loss_percent": 0.0}
        asyncio.run(self.engine.poll_single_device("router_core", "192.168.88.1", dev["profile"], settings))
        dev = self.engine.get_device_detail("router_core")
        self.assertEqual(dev["profile"]["status"], "DOWN")

        # 5. Second success -> Recovers to UP, incident automatically marked resolved!
        asyncio.run(self.engine.poll_single_device("router_core", "192.168.88.1", dev["profile"], settings))
        dev = self.engine.get_device_detail("router_core")
        self.assertEqual(dev["profile"]["status"], "UP")

        open_incs = self.engine.list_incidents(status="open")
        self.assertEqual(len(open_incs), 0)

        resolved_incs = self.engine.list_incidents(status="resolved")
        self.assertEqual(len(resolved_incs), 1)
        self.assertEqual(resolved_incs[0]["id"], inc_id)
        self.assertIn("RECOVERED", resolved_incs[0]["details"])

    def test_single_flight_lock_prevents_overlap(self):
        # Verify that _is_polling lock works cleanly
        self.engine._is_polling = True
        # If running a second poll while active, it returns immediately without error
        asyncio.run(self.engine.poll_all_devices_cycle())
        self.assertTrue(self.engine._is_polling)
        self.engine._is_polling = False

    def test_wizard_generate_commands(self):
        # Test v2c command generator
        cmds_v2 = self.engine.wizard_generate_commands(
            community_name="my-ro-snmp",
            allowed_collector_ip="10.10.10.0/24",
            use_v3=False,
        )
        self.assertTrue(any("/snmp set enabled=yes" in c for c in cmds_v2))
        self.assertTrue(any('name="my-ro-snmp"' in c and 'addresses="10.10.10.0/24"' in c for c in cmds_v2))
        self.assertTrue(any("read-access=yes write-access=no" in c for c in cmds_v2))

        # Test v3 command generator
        cmds_v3 = self.engine.wizard_generate_commands(
            community_name="v3-aira",
            allowed_collector_ip="10.10.10.5",
            use_v3=True,
            v3_user="secuser",
            v3_auth_key="MyAuthPass123",
            v3_priv_key="MyPrivPass456",
        )
        self.assertTrue(any("security=private" in c for c in cmds_v3))
        self.assertTrue(any('authentication-password="MyAuthPass123"' in c for c in cmds_v3))
        self.assertTrue(any('encryption-password="MyPrivPass456"' in c for c in cmds_v3))

    @patch("core.nms_engine.bounded_icmp_ping")
    @patch("core.nms_engine.snmp_get_multi")
    def test_wizard_detect_snmp(self, mock_snmp_get, mock_ping):
        # 1. Host unreachable via ping
        mock_ping.return_value = {"alive": False, "rtt_ms": 0.0}
        res_down = asyncio.run(self.engine.wizard_detect_snmp("192.168.1.100"))
        self.assertFalse(res_down["reachable"])
        self.assertFalse(res_down["snmp_responding"])

        # 2. Host reachable but SNMP timeout
        mock_ping.return_value = {"alive": True, "rtt_ms": 2.0}
        mock_snmp_get.return_value = ({}, "Request timeout")
        res_no_snmp = asyncio.run(self.engine.wizard_detect_snmp("192.168.1.100"))
        self.assertTrue(res_no_snmp["reachable"])
        self.assertFalse(res_no_snmp["snmp_responding"])

        # 3. Host reachable and SNMP responds
        mock_snmp_get.return_value = ({"sys_descr": "MikroTik RouterOS 7.16"}, None)
        res_ok = asyncio.run(self.engine.wizard_detect_snmp("192.168.1.100"))
        self.assertTrue(res_ok["reachable"])
        self.assertTrue(res_ok["snmp_responding"])
        self.assertEqual(res_ok["sys_descr"], "MikroTik RouterOS 7.16")

    def test_metric_retention_pruning(self):
        now = time.time()
        with self.engine._lock, closing(sqlite3.connect(str(self.db_path))) as conn:
            # Insert 1 fresh metric and 1 ancient metric (10 days old)
            conn.execute(
                "INSERT INTO nms_device_metrics (device_id, timestamp, cpu_load_percent) VALUES ('router_core', ?, 15.0)",
                (now,),
            )
            conn.execute(
                "INSERT INTO nms_device_metrics (device_id, timestamp, cpu_load_percent) VALUES ('router_core', ?, 25.0)",
                (now - (10 * 86400),),
            )
            conn.commit()

        # Prune older than 7 days
        self.engine.prune_expired_metrics(retention_days=7)

        with self.engine._lock, sqlite3.connect(str(self.db_path)) as conn:
            rows = conn.execute("SELECT * FROM nms_device_metrics WHERE device_id = 'router_core'").fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][3], 15.0)  # Only fresh metric remains

    def test_scheduler_start_stop_idempotent(self):
        async def _test():
            self.assertFalse(self.engine.is_running())
            res1 = self.engine.start_monitoring()
            self.assertTrue(res1)
            self.assertTrue(self.engine.is_running())
            # Duplicate start does not duplicate scheduler or crash
            res2 = self.engine.start_monitoring()
            self.assertTrue(res2)
            self.assertTrue(self.engine.is_running())
            # Stop monitoring
            stop_res = self.engine.stop_monitoring()
            self.assertTrue(stop_res)
            self.assertFalse(self.engine.is_running())
        asyncio.run(_test())

    def test_stale_indicator(self):
        now = time.time()
        # Fresh (within 3x interval = 45s)
        self.assertFalse(is_check_stale(now - 10, interval_sec=15))
        # Stale (> 45s)
        self.assertTrue(is_check_stale(now - 50, interval_sec=15))
        # Null timestamp is considered stale
        self.assertTrue(is_check_stale(None, interval_sec=15))

    def test_parse_mikrotik_identity_formats(self):
        # 1. Quoted name in KV
        out1 = ' 0 name="CCR-Edge-01"'
        self.assertEqual(parse_mikrotik_identity(out1), "CCR-Edge-01")

        # 2. Colon formatted name with license banner
        out2 = """
MikroTik RouterOS 7.16 (c) 1999-2024
  name: Verified-Core-Router
"""
        self.assertEqual(parse_mikrotik_identity(out2), "Verified-Core-Router")

        # 3. Unquoted name
        out3 = "name=Branch-SW1"
        self.assertEqual(parse_mikrotik_identity(out3), "Branch-SW1")

        # 4. Bad command / error output
        out4 = "bad command name identity (line 1 column 9)"
        self.assertIsNone(parse_mikrotik_identity(out4))

    @patch("core.nms_engine.bounded_icmp_ping")
    def test_user_override_display_name_survives_polling(self, mock_ping):
        mock_ping.return_value = {"alive": True, "rtt_ms": 1.2}

        # Put user override on node
        with self.engine._lock, sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "UPDATE topology_nodes SET user_overrides_json = ? WHERE id = 'router_core'",
                ('{"name": "Admin Custom Core"}',),
            )
            conn.commit()

        # Mock RouterOS returning identity "Hardware-CCR2004"
        with patch.object(self.engine, "poll_device_routeros", new_callable=AsyncMock) as mock_ros:
            mock_ros.return_value = {
                "success": True,
                "identity": "Hardware-CCR2004",
                "version": "7.16",
                "model": "CCR2004",
                "interfaces": [],
            }
            dev = self.engine.get_device_detail("router_core")
            settings = self.engine.get_settings()
            asyncio.run(self.engine.poll_single_device("router_core", "192.168.88.1", dev["profile"], settings))

        # Check detail: resolved name must remain user override!
        detail = self.engine.get_device_detail("router_core")
        self.assertEqual(detail["name"], "Admin Custom Core")
        self.assertEqual(detail["profile"]["name_source"], "user_override")
        self.assertEqual(detail["identity"], "Hardware-CCR2004")

    @patch("core.nms_engine.bounded_icmp_ping")
    def test_dynamic_interface_inventory_reflection(self, mock_ping):
        mock_ping.return_value = {"alive": True, "rtt_ms": 1.5}

        dynamic_ifaces = [
            {"name": "sfp-sfpplus1", "interface_type": "ether", "admin_status": "enabled", "oper_status": "up", "negotiated_speed_bps": 10_000_000_000, "in_octets": 500, "out_octets": 1000},
            {"name": "ether1", "interface_type": "ether", "admin_status": "enabled", "oper_status": "up", "negotiated_speed_bps": 100_000_000, "in_octets": 100, "out_octets": 200},
            {"name": "bridge1", "interface_type": "bridge", "admin_status": "enabled", "oper_status": "up", "negotiated_speed_bps": None, "in_octets": 600, "out_octets": 1200},
        ]

        with patch.object(self.engine, "poll_device_routeros", new_callable=AsyncMock) as mock_ros:
            mock_ros.return_value = {
                "success": True,
                "identity": "Test-Core",
                "version": "7.16",
                "model": "CCR",
                "interfaces": dynamic_ifaces,
            }
            dev = self.engine.get_device_detail("router_core")
            settings = self.engine.get_settings()
            asyncio.run(self.engine.poll_single_device("router_core", "192.168.88.1", dev["profile"], settings))

        detail = self.engine.get_device_detail("router_core")
        ifnames = [i["interface_name"] for i in detail["interfaces"]]
        self.assertEqual(ifnames, ["bridge1", "ether1", "sfp-sfpplus1"])

    def test_100mbps_port_speed_accuracy(self):
        eth_output = """Flags: X - disabled, R - running, S - slave 
 0 R  name="ether1" default-name="ether1" mtu=1500 mac-address=64:D1:54:11:22:33 auto-negotiation=yes rate=100Mbps full-duplex=yes 
 1 R  name="ether2" default-name="ether2" mtu=1500 mac-address=64:D1:54:11:22:34 auto-negotiation=yes rate=1Gbps full-duplex=yes 
"""
        parsed = parse_mikrotik_ethernet(eth_output)
        self.assertIn("ether1", parsed)
        self.assertEqual(parsed["ether1"]["negotiated_speed_bps"], 100_000_000)
        self.assertNotEqual(parsed["ether1"]["negotiated_speed_bps"], 1_000_000_000)
        self.assertEqual(parsed["ether2"]["negotiated_speed_bps"], 1_000_000_000)

    def test_unknown_interface_speed_remains_none(self):
        eth_output = """Flags: X - disabled, R - running, S - slave 
 0    name="ether3" default-name="ether3" mtu=1500 mac-address=64:D1:54:11:22:35 auto-negotiation=yes 
"""
        parsed = parse_mikrotik_ethernet(eth_output)
        self.assertIn("ether3", parsed)
        # Port is not running (no 'R' flag), speed must be None
        self.assertIsNone(parsed["ether3"]["negotiated_speed_bps"])

    def test_interface_admin_vs_oper_status_distinction(self):
        eth_output = """Flags: X - disabled, R - running, S - slave 
 0 X  name="ether1" default-name="ether1" rate=100Mbps 
 1    name="ether2" default-name="ether2" rate=1Gbps 
 2 R  name="ether3" default-name="ether3" rate=1Gbps 
"""
        parsed = parse_mikrotik_ethernet(eth_output)
        # ether1: disabled
        self.assertTrue(parsed["ether1"]["disabled"])
        self.assertFalse(parsed["ether1"]["running"])
        self.assertIsNone(parsed["ether1"]["negotiated_speed_bps"])

        # ether2: enabled but link down (not running)
        self.assertFalse(parsed["ether2"]["disabled"])
        self.assertFalse(parsed["ether2"]["running"])
        self.assertIsNone(parsed["ether2"]["negotiated_speed_bps"])

        # ether3: enabled and running
        self.assertFalse(parsed["ether3"]["disabled"])
        self.assertTrue(parsed["ether3"]["running"])
        self.assertEqual(parsed["ether3"]["negotiated_speed_bps"], 1_000_000_000)

    @patch("core.nms_engine.bounded_icmp_ping")
    def test_auto_sync_idempotence_no_duplicates(self, mock_ping):
        mock_ping.return_value = {"alive": True, "rtt_ms": 1.0}
        # Run poll_all_devices_cycle twice
        asyncio.run(self.engine.poll_all_devices_cycle())
        asyncio.run(self.engine.poll_all_devices_cycle())

        devices = self.engine.list_devices()
        # Exactly 2 devices in DB ('router_core', 'switch_sw1'), no duplicate rows
        self.assertEqual(len(devices), 2)


class TestNmsRestApi(unittest.TestCase):
    """Test suite for NMS REST API endpoints using FastAPI TestClient."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self.temp_dir.name) / "test_api_nms.db"

        # Prepare DB
        conn = sqlite3.connect(str(self.db_path))
        conn.executescript(
            """
            CREATE TABLE topology_nodes (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                identity TEXT,
                ip TEXT,
                mac TEXT,
                device_type TEXT DEFAULT 'router',
                ownership_status TEXT DEFAULT 'verified_owned',
                reachability_status TEXT DEFAULT 'online',
                pos_x REAL DEFAULT 0.0,
                pos_y REAL DEFAULT 0.0,
                last_seen REAL
            );
            INSERT INTO topology_nodes (id, name, identity, ip, mac, device_type)
            VALUES ('dev_r1', 'Core Router', 'CCR', '192.168.1.1', 'AA:BB:CC:DD:EE:01', 'router');
            """
        )
        conn.commit()
        conn.close()

        self.engine = NmsEngine(self.db_path)
        self.app = FastAPI()
        self.app.include_router(nms_router_module.router)

    def tearDown(self):
        self.engine.stop_monitoring()
        self.temp_dir.cleanup()

    def _client(self) -> TestClient:
        return TestClient(self.app)

    def test_api_overview_and_settings(self):
        with patch.object(nms_router_module, "get_nms_engine", return_value=self.engine):
            client = self._client()

            # Overview
            r_over = client.get("/api/nms/overview")
            self.assertEqual(r_over.status_code, 200)
            data = r_over.json()
            self.assertTrue(data["success"])
            self.assertEqual(data["overview"]["total_devices"], 1)

            # Settings GET
            r_set = client.get("/api/nms/settings")
            self.assertEqual(r_set.status_code, 200)
            self.assertEqual(r_set.json()["settings"]["default_interval_sec"], 15)

            # Settings PUT
            r_put = client.put("/api/nms/settings", json={"default_interval_sec": 60, "failure_threshold": 4})
            self.assertEqual(r_put.status_code, 200)
            self.assertEqual(r_put.json()["settings"]["default_interval_sec"], 60)

    def test_api_device_inventory_and_profile_update(self):
        with patch.object(nms_router_module, "get_nms_engine", return_value=self.engine):
            client = self._client()

            # List devices
            r_list = client.get("/api/nms/devices")
            self.assertEqual(r_list.status_code, 200)
            devices = r_list.json()["devices"]
            self.assertEqual(len(devices), 1)
            self.assertEqual(devices[0]["id"], "dev_r1")

            # Get device detail
            r_det = client.get("/api/nms/devices/dev_r1")
            self.assertEqual(r_det.status_code, 200)
            self.assertEqual(r_det.json()["device"]["name"], "Core Router")

            # 404 for unknown device
            self.assertEqual(client.get("/api/nms/devices/nonexistent").status_code, 404)

            # Update profile
            r_prof = client.put(
                "/api/nms/devices/dev_r1/profile",
                json={
                    "management_mode": "managed",
                    "snmp_enabled": True,
                    "snmp_community": "secret-snmp",
                },
            )
            self.assertEqual(r_prof.status_code, 200)

            # Verify updated profile
            fresh_det = client.get("/api/nms/devices/dev_r1").json()["device"]
            self.assertEqual(fresh_det["profile"]["management_mode"], "managed")
            self.assertTrue(fresh_det["profile"]["snmp_enabled"])

    def test_api_incidents_list_and_acknowledge(self):
        with patch.object(nms_router_module, "get_nms_engine", return_value=self.engine):
            client = self._client()

            # Insert test incident
            with self.engine._lock, closing(sqlite3.connect(str(self.db_path))) as conn:
                conn.execute(
                    """
                    INSERT INTO nms_incidents (device_id, incident_type, severity, title, details, status, started_at)
                    VALUES ('dev_r1', 'device_down', 'critical', 'Core Router DOWN', 'Test outage', 'open', ?)
                    """,
                    (time.time(),),
                )
                conn.commit()

            r_incs = client.get("/api/nms/incidents?status=open")
            self.assertEqual(r_incs.status_code, 200)
            incidents = r_incs.json()["incidents"]
            self.assertEqual(len(incidents), 1)
            inc_id = incidents[0]["id"]

            # Acknowledge incident
            r_ack = client.post(f"/api/nms/incidents/{inc_id}/acknowledge")
            self.assertEqual(r_ack.status_code, 200)

            # Verify acknowledged
            r_ack_list = client.get("/api/nms/incidents?status=acknowledged")
            self.assertEqual(len(r_ack_list.json()["incidents"]), 1)

    def test_api_wizard_endpoints(self):
        with patch.object(nms_router_module, "get_nms_engine", return_value=self.engine):
            client = self._client()

            # 1. Wizard Generate Commands
            r_gen = client.post(
                "/api/nms/wizard/generate-commands",
                json={"community_name": "aira-mon", "allowed_collector_ip": "10.0.0.0/24", "use_v3": False},
            )
            self.assertEqual(r_gen.status_code, 200)
            cmds = r_gen.json()["commands"]
            self.assertGreater(len(cmds), 0)
            self.assertTrue(any('name="aira-mon"' in c for c in cmds))

            # 2. Wizard Detect with Mock
            with patch.object(self.engine, "wizard_detect_snmp", new_callable=AsyncMock) as mock_detect:
                mock_detect.return_value = {
                    "reachable": True,
                    "snmp_responding": True,
                    "sys_descr": "MikroTik CCR2004",
                    "message": "SNMP aktif.",
                }
                r_det = client.post("/api/nms/wizard/detect", json={"host": "192.168.1.1"})
                self.assertEqual(r_det.status_code, 200)
                self.assertTrue(r_det.json()["detection"]["snmp_responding"])

            # 3. Wizard Verify and Save with Mock
            with patch.object(self.engine, "wizard_verify_and_save", new_callable=AsyncMock) as mock_verify:
                mock_verify.return_value = {
                    "success": True,
                    "identity": "CCR",
                    "cpu_load_percent": 12.0,
                    "memory_used_percent": 24.5,
                    "interfaces_count": 8,
                    "message": "Berhasil diverifikasi.",
                }
                r_ver = client.post(
                    "/api/nms/wizard/verify-and-save",
                    json={"device_id": "dev_r1", "host": "192.168.1.1", "community": "aira-mon"},
                )
                self.assertEqual(r_ver.status_code, 200)
                self.assertTrue(r_ver.json()["success"])


    def test_nms_websocket_endpoint_and_snapshot(self):
        from api.main import app
        with TestClient(app) as client:
            with client.websocket_connect("/ws/nms") as ws:
                msg = ws.receive_json()
                self.assertEqual(msg["type"], "nms_snapshot")
                self.assertIn("overview", msg["data"])
                self.assertIn("total_devices", msg["data"]["overview"])
                # Test ping-pong
                ws.send_json({"type": "ping"})
                pong = ws.receive_json()
                self.assertEqual(pong["type"], "pong")

    def test_nms_event_bus_emission_on_poll(self):
        from core.events import event_bus, EventNames, WILDCARD
        received_events = []
        token = event_bus.subscribe(WILDCARD, lambda e: received_events.append(e))

        async def _run():
            await self.engine.poll_all_devices_cycle()

        try:
            asyncio.run(_run())
            event_types = [e.event for e in received_events]
            self.assertIn(EventNames.NMS_CYCLE_COMPLETED, event_types)
        finally:
            event_bus.unsubscribe("nms.*", token)

if __name__ == "__main__":
    unittest.main()
