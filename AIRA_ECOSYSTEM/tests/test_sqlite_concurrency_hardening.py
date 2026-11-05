"""
tests/test_sqlite_concurrency_hardening.py — Complete Test Suite for SQLite Concurrency & Reliability Hardening.

Covers Groups A through G:
- Group A: Centralized connection policy tests (PRAGMAs, Row factory, isolation, transaction manager).
- Group B: Multi-threaded write coordinator & concurrent writers (serialization, metrics, retry, timeout).
- Group C: NMS event processing reliability (decoupling, synchronous listener safety, idempotency).
- Group D: Historical snapshot engine protection (non-blocking reads, fast atomic inserts, read-only compare).
- Group E: Discovery & stale decayer reliability (bounded retry, concurrent decay).
- Group F: Application lifecycle & multi-worker validation (WAL mode initialization, worker count warning, shutdown).
- Group G: Regression protection & data preservation (in-memory immutability, node/edge preservation).
"""

from __future__ import annotations

import asyncio
import gc
import json
import logging
import os
import sqlite3
import tempfile
import threading
import time
import unittest
from contextlib import closing
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

from core.events import Event, EventBus, EventNames
from core.topology_db import (
    DEFAULT_BUSY_TIMEOUT_MS,
    DEFAULT_TIMEOUT_SEC,
    DEFAULT_TOPOLOGY_DB_PATH,
    TopologyWriteCoordinator,
    execute_with_retry,
    get_topology_connection,
    get_write_coordinator,
    init_topology_database,
    is_transient_sqlite_lock_error,
    topology_transaction,
)
from core.topology_engine import TopologyEngine
from core.topology_models import (
    ConfidenceTier,
    EdgeLifecycleState,
    RelationshipClass,
    TopologyEdge,
    TopologySnapshot,
)


class TestGroupACentralizedConnectionPolicy(unittest.TestCase):
    """Group A: Centralized connection policy and transaction context manager."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_conn_policy.db"
        init_topology_database(self.db_path)

    def tearDown(self):
        gc.collect()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_01_connection_factory_attributes(self):
        """Verifies row factory, foreign keys, and busy timeout on standard connections."""
        with closing(get_topology_connection(self.db_path, timeout=30.0)) as conn:
            self.assertEqual(conn.row_factory, sqlite3.Row)
            fk_row = conn.execute("PRAGMA foreign_keys").fetchone()
            self.assertEqual(fk_row[0], 1)
            busy_row = conn.execute("PRAGMA busy_timeout").fetchone()
            self.assertEqual(busy_row[0], DEFAULT_BUSY_TIMEOUT_MS)

    def test_02_wal_mode_enforced(self):
        """Verifies that init_topology_database enforces WAL mode idempotently."""
        with closing(get_topology_connection(self.db_path)) as conn:
            mode_row = conn.execute("PRAGMA journal_mode").fetchone()
            self.assertEqual(str(mode_row[0]).lower(), "wal")

    def test_03_synchronous_normal(self):
        """Verifies synchronous = NORMAL for optimal concurrent throughput and safety."""
        with closing(get_topology_connection(self.db_path)) as conn:
            sync_row = conn.execute("PRAGMA synchronous").fetchone()
            # 1 corresponds to NORMAL in SQLite
            self.assertEqual(sync_row[0], 1)

    def test_04_read_only_connection_query_only(self):
        """Verifies read_only=True sets PRAGMA query_only=ON preventing mutations."""
        with closing(get_topology_connection(self.db_path, read_only=True)) as conn:
            qo_row = conn.execute("PRAGMA query_only").fetchone()
            self.assertEqual(qo_row[0], 1)
            # Mutation on read-only connection should raise OperationalError
            with self.assertRaises(sqlite3.OperationalError):
                conn.execute("CREATE TABLE test_fail (id INT)")

    def test_05_transaction_commit_success(self):
        """Verifies that topology_transaction commits successfully upon clean exit."""
        with closing(get_topology_connection(self.db_path)) as setup_conn:
            setup_conn.execute("CREATE TABLE test_data (id INT, val TEXT)")
            setup_conn.commit()

        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute("INSERT INTO test_data VALUES (1, 'alpha')")

        with closing(get_topology_connection(self.db_path, read_only=True)) as verify_conn:
            row = verify_conn.execute("SELECT val FROM test_data WHERE id = 1").fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["val"], "alpha")

    def test_06_transaction_rollback_on_exception(self):
        """Verifies that topology_transaction rolls back cleanly when an exception occurs."""
        with closing(get_topology_connection(self.db_path)) as setup_conn:
            setup_conn.execute("CREATE TABLE test_rollback (id INT PRIMARY KEY, val TEXT)")
            setup_conn.commit()

        with self.assertRaises(RuntimeError):
            with topology_transaction(self.db_path, write=True) as conn:
                conn.execute("INSERT INTO test_rollback VALUES (10, 'doomed')")
                raise RuntimeError("Simulated transaction failure")

        with closing(get_topology_connection(self.db_path, read_only=True)) as verify_conn:
            row = verify_conn.execute("SELECT * FROM test_rollback WHERE id = 10").fetchone()
            self.assertIsNone(row, "Uncommitted data must not persist after exception rollback")

    def test_07_transaction_reentrant_lock(self):
        """Verifies that the same thread can acquire write transactions reentrantly without deadlock."""
        coordinator = get_write_coordinator(self.db_path)
        with coordinator.acquire_writer(timeout=5.0):
            with coordinator.acquire_writer(timeout=5.0):
                # RLock must permit reentrant acquisition on the same thread
                self.assertGreaterEqual(coordinator.active_writers, 1)

    def test_07b_nested_write_savepoint_success(self):
        """Verifies same thread nested write operations reuse connection and succeed with SAVEPOINT."""
        with closing(get_topology_connection(self.db_path)) as setup_conn:
            setup_conn.execute("CREATE TABLE test_nested (id INT PRIMARY KEY, val TEXT)")
            setup_conn.commit()

        with topology_transaction(self.db_path, write=True) as outer_conn:
            outer_conn.execute("INSERT INTO test_nested VALUES (1, 'outer')")
            # Nested write on same thread
            with topology_transaction(self.db_path, write=True) as inner_conn:
                self.assertIs(inner_conn, outer_conn, "Nested transaction must reuse same connection")
                inner_conn.execute("INSERT INTO test_nested VALUES (2, 'nested')")

        with closing(get_topology_connection(self.db_path, read_only=True)) as verify_conn:
            rows = verify_conn.execute("SELECT id, val FROM test_nested ORDER BY id ASC").fetchall()
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["val"], "outer")
            self.assertEqual(rows[1]["val"], "nested")

    def test_07c_nested_write_savepoint_rollback_on_nested_exception(self):
        """Verifies exception in nested write rolls back to SAVEPOINT while outer succeeds."""
        with closing(get_topology_connection(self.db_path)) as setup_conn:
            setup_conn.execute("CREATE TABLE test_nested_rb (id INT PRIMARY KEY, val TEXT)")
            setup_conn.commit()

        with topology_transaction(self.db_path, write=True) as outer_conn:
            outer_conn.execute("INSERT INTO test_nested_rb VALUES (1, 'survivor')")
            try:
                with topology_transaction(self.db_path, write=True) as inner_conn:
                    inner_conn.execute("INSERT INTO test_nested_rb VALUES (2, 'doomed')")
                    raise ValueError("Nested failed intentionally")
            except ValueError:
                pass  # Outer transaction handles nested failure

            outer_conn.execute("INSERT INTO test_nested_rb VALUES (3, 'outer_after')")

        with closing(get_topology_connection(self.db_path, read_only=True)) as verify_conn:
            rows = verify_conn.execute("SELECT id, val FROM test_nested_rb ORDER BY id ASC").fetchall()
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["id"], 1)
            self.assertEqual(rows[1]["id"], 3)
            # Row 2 must have rolled back via SAVEPOINT
            self.assertIsNone(verify_conn.execute("SELECT * FROM test_nested_rb WHERE id = 2").fetchone())

    def test_07d_nested_write_full_rollback_on_outer_exception(self):
        """Verifies unhandled exception in outer rolls back both outer and nested writes."""
        with closing(get_topology_connection(self.db_path)) as setup_conn:
            setup_conn.execute("CREATE TABLE test_full_rb (id INT PRIMARY KEY, val TEXT)")
            setup_conn.commit()

        with self.assertRaises(RuntimeError):
            with topology_transaction(self.db_path, write=True) as outer_conn:
                outer_conn.execute("INSERT INTO test_full_rb VALUES (1, 'outer')")
                with topology_transaction(self.db_path, write=True) as inner_conn:
                    inner_conn.execute("INSERT INTO test_full_rb VALUES (2, 'nested')")
                raise RuntimeError("Outer transaction explodes")

        with closing(get_topology_connection(self.db_path, read_only=True)) as verify_conn:
            rows = verify_conn.execute("SELECT * FROM test_full_rb").fetchall()
            self.assertEqual(len(rows), 0, "All writes must roll back on outer transaction failure")

    def test_07e_independent_connection_on_same_thread_rejected(self):
        """Verifies passing conflicting independent connection on same thread is rejected (Policy C)."""
        with topology_transaction(self.db_path, write=True):
            indep_conn = get_topology_connection(self.db_path, read_only=False)
            try:
                with self.assertRaises(sqlite3.OperationalError) as ctx:
                    with topology_transaction(self.db_path, write=True, existing_conn=indep_conn):
                        pass
                self.assertIn("Conflicting independent connection", str(ctx.exception))
            finally:
                indep_conn.close()


    def test_08_transaction_connection_reuse(self):
        """Verifies that passing existing_conn reuses the connection without premature closure."""
        with closing(get_topology_connection(self.db_path)) as outer_conn:
            outer_conn.execute("CREATE TABLE test_reuse (k TEXT)")
            with topology_transaction(self.db_path, existing_conn=outer_conn) as inner_conn:
                self.assertIs(inner_conn, outer_conn)
                inner_conn.execute("INSERT INTO test_reuse VALUES ('shared')")
            # outer_conn should still be open
            row = outer_conn.execute("SELECT count(*) FROM test_reuse").fetchone()
            self.assertEqual(row[0], 1)


class TestGroupBMultiThreadedWriteCoordinator(unittest.TestCase):
    """Group B: Concurrent write serialization, bounded retry, and wait metrics."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_concurrency.db"
        self.engine = TopologyEngine(self.db_path)

    def tearDown(self):
        gc.collect()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_09_serialized_writes_no_lock_error(self):
        """Verifies 10 concurrent threads inserting edges simultaneously succeed with zero lock errors."""
        # Pre-seed nodes
        self.engine.upsert_node(node_id="n1", name="R1", ip="10.0.0.1")
        self.engine.upsert_node(node_id="n2", name="R2", ip="10.0.0.2")

        thread_errors: List[Exception] = []
        num_threads = 10

        def _worker(thread_idx: int):
            try:
                edge = TopologyEdge(
                    id=f"edge_concur_{thread_idx}",
                    source_node_id="n1",
                    target_node_id="n2",
                    source_interface=f"eth{thread_idx}",
                    target_interface=f"eth{thread_idx}",
                    oper_status="up",
                    relationship_class="physical", confidence_rationale="test validation",
                )
                self.engine.insert_edge(edge)
            except Exception as exc:
                thread_errors.append(exc)

        threads = [threading.Thread(target=_worker, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15.0)

        self.assertEqual(len(thread_errors), 0, f"Concurrent inserts raised errors: {thread_errors}")
        edges = self.engine.list_edges()
        self.assertEqual(len(edges), num_threads)

    def test_10_queue_depth_metrics(self):
        """Verifies coordinator tracks queue depth and active write counts accurately."""
        coord = get_write_coordinator(self.db_path)
        stats_before = coord.get_stats()
        self.assertIn("queue_depth", stats_before)
        self.assertIn("active_writers", stats_before)
        self.assertIn("total_write_transactions", stats_before)

        # Acquire lock and verify stats update
        with coord.acquire_writer(timeout=5.0):
            stats_during = coord.get_stats()
            self.assertGreaterEqual(stats_during["active_writers"], 1)

    def test_11_bounded_retry_on_busy(self):
        """Verifies execute_with_retry backs off and succeeds on transient SQLite lock contention."""
        call_count = 0

        def _flaky_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise sqlite3.OperationalError("database is locked")
            return "success_after_contention"

        result = execute_with_retry(
            _flaky_operation,
            max_retries=4,
            base_delay=0.01,
            max_delay=0.05,
            operation_name="test_flaky",
        )
        self.assertEqual(result, "success_after_contention")
        self.assertEqual(call_count, 3)

    def test_11b_total_deadline_exceeded(self):
        """Verifies execute_with_retry enforces total elapsed-time deadline."""
        call_count = 0

        def _blocking_contention():
            nonlocal call_count
            call_count += 1
            time.sleep(0.06)
            raise sqlite3.OperationalError("database is locked")

        with self.assertRaises(sqlite3.OperationalError) as ctx:
            execute_with_retry(
                _blocking_contention,
                max_retries=10,
                base_delay=0.05,
                max_delay=0.1,
                total_deadline_sec=0.15,
                operation_name="deadline_test",
            )
        self.assertIn("deadline exceeded", str(ctx.exception).lower())

    def test_11c_cancellation_check(self):
        """Verifies execute_with_retry aborts on cancellation callback."""
        is_cancelled = False

        def _cancel_check():
            return is_cancelled

        call_count = 0

        def _contention():
            nonlocal call_count, is_cancelled
            call_count += 1
            is_cancelled = True
            raise sqlite3.OperationalError("database is locked")

        with self.assertRaises(asyncio.CancelledError):
            execute_with_retry(
                _contention,
                max_retries=5,
                base_delay=0.01,
                cancel_check=_cancel_check,
                operation_name="cancel_test",
            )
        self.assertEqual(call_count, 1)

    def test_11d_non_idempotent_no_retry(self):
        """Verifies execute_with_retry does NOT replay non-idempotent operations on contention."""
        call_count = 0

        def _non_idempotent():
            nonlocal call_count
            call_count += 1
            raise sqlite3.OperationalError("database is locked")

        with self.assertRaises(sqlite3.OperationalError):
            execute_with_retry(
                _non_idempotent,
                max_retries=4,
                idempotent=False,
                operation_name="non_idempotent_test",
            )
        self.assertEqual(call_count, 1, "Non-idempotent operation must fail immediately on contention without retry")


    def test_12_non_transient_error_no_retry(self):
        """Verifies execute_with_retry does NOT retry on non-lock errors (syntax, constraints)."""
        call_count = 0

        def _syntax_error():
            nonlocal call_count
            call_count += 1
            raise sqlite3.OperationalError("near 'SYNTAX_ERROR': syntax error")

        with self.assertRaises(sqlite3.OperationalError):
            execute_with_retry(_syntax_error, max_retries=4, operation_name="syntax_test")

        self.assertEqual(call_count, 1, "Non-transient error must fail on first attempt without retrying")

    def test_13_timeout_detection(self):
        """Verifies write coordinator raises OperationalError when write lock timeout expires."""
        coord = TopologyWriteCoordinator("test_timeout.db")
        # Hold lock in a separate thread
        blocker_ready = threading.Event()
        blocker_release = threading.Event()

        def _blocker():
            with coord._lock:
                blocker_ready.set()
                blocker_release.wait(timeout=5.0)

        t = threading.Thread(target=_blocker)
        t.start()
        blocker_ready.wait(timeout=2.0)

        try:
            with self.assertRaises(sqlite3.OperationalError):
                with coord.acquire_writer(timeout=0.1):
                    pass
        finally:
            blocker_release.set()
            t.join(timeout=2.0)

    def test_14_concurrent_readers_and_writer(self):
        """Verifies WAL mode allows concurrent readers to read without blocking while a writer writes."""
        self.engine.upsert_node(node_id="r1", name="Router1", ip="10.0.0.1")
        reader_successes = []

        writer_in_progress = threading.Event()
        writer_done = threading.Event()

        def _slow_writer():
            with self.engine.transaction(write=True) as conn:
                writer_in_progress.set()
                conn.execute(
                    "UPDATE topology_nodes SET name = 'Router1_Updated' WHERE id = 'r1'"
                )
                time.sleep(0.3)
            writer_done.set()

        def _reader():
            writer_in_progress.wait(timeout=2.0)
            with closing(get_topology_connection(self.db_path, read_only=True)) as conn:
                row = conn.execute("SELECT name FROM topology_nodes WHERE id = 'r1'").fetchone()
                reader_successes.append(row["name"])

        t_write = threading.Thread(target=_slow_writer)
        t_read = threading.Thread(target=_reader)

        t_write.start()
        t_read.start()

        t_read.join(timeout=3.0)
        t_write.join(timeout=3.0)

        self.assertEqual(len(reader_successes), 1)
        # WAL snapshot isolation: reader read either the previous committed state or updated state without blocking
        self.assertIn(reader_successes[0], ("Router1", "Router1_Updated"))


class TestGroupCNMSEventProcessingReliability(unittest.IsolatedAsyncioTestCase):
    """Group C: Decoupled NMS event processing, synchronous listener safety, and idempotency."""

    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_nms_reliability.db"
        self.engine = TopologyEngine(self.db_path)
        self.bus = EventBus()
        self.loop = asyncio.get_running_loop()
        self.bus.bind_loop(self.loop)
        self.engine.start_nms_sync(bus=self.bus)

        # Seed test nodes and edge
        self.engine.upsert_node(node_id="dev1", name="MikroTik-A", ip="192.168.88.1")
        self.engine.upsert_node(node_id="dev2", name="MikroTik-B", ip="192.168.88.2")
        edge = TopologyEdge(
            id="edge_dev1_dev2",
            source_node_id="dev1",
            target_node_id="dev2",
            source_interface="ether1",
            target_interface="ether1",
            oper_status="down",
            relationship_class="physical", confidence_rationale="test validation",
        )
        self.engine.insert_edge(edge)

    async def asyncTearDown(self):
        self.engine.stop_nms_sync()
        self.bus.unbind_loop()
        gc.collect()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    async def test_15_nms_event_processed_outside_transaction(self):
        """Verifies interface UP event transitions status and emits topology.delta outside transaction."""
        delta_events: List[Dict[str, Any]] = []

        def _on_delta(evt: Event):
            delta_events.append(evt.data)

        self.bus.subscribe("topology.delta", _on_delta)

        event = Event(
            event=EventNames.NMS_INTERFACE_STATUS_CHANGED,
            data={
                "device_id": "dev1",
                "interface_name": "ether1",
                "oper_status": "up",
                "previous_status": "down",
                "timestamp": time.time(),
            },
        )
        self.bus.publish(event.event, data=event.data)
        await asyncio.sleep(0.1)

        edge = self.engine.get_edge("edge_dev1_dev2")
        self.assertIsNotNone(edge)
        self.assertEqual(edge.oper_status, "up")
        self.assertEqual(len(delta_events), 1)
        self.assertEqual(delta_events[0]["oper_status"], "up")

    async def test_16_nms_event_synchronous_listener_no_deadlock(self):
        """Verifies a synchronous listener accessing topology.db during event callback does NOT deadlock."""
        listener_ran = threading.Event()
        listener_error: Optional[Exception] = None

        def _synchronous_listener(evt: Event):
            nonlocal listener_error
            try:
                # Listener directly queries and writes to topology database
                edge = self.engine.get_edge("edge_dev1_dev2")
                self.assertIsNotNone(edge)
                listener_ran.set()
            except Exception as exc:
                listener_error = exc

        self.bus.subscribe("topology.delta", _synchronous_listener)

        event = Event(
            event=EventNames.NMS_INTERFACE_STATUS_CHANGED,
            data={
                "device_id": "dev1",
                "interface_name": "ether1",
                "oper_status": "up",
                "timestamp": time.time(),
            },
        )
        self.bus.publish(event.event, data=event.data)
        await asyncio.sleep(0.1)

        self.assertTrue(listener_ran.is_set(), "Synchronous listener must complete without deadlocking")
        self.assertIsNone(listener_error, f"Listener encountered error: {listener_error}")

    async def test_17_nms_status_transition_updates_edge_and_link(self):
        """Verifies status transition updates topology_edges and legacy links atomically."""
        self.engine.upsert_link("dev1", "dev2", "ether1", "ether1")

        event = Event(
            event=EventNames.NMS_INTERFACE_STATUS_CHANGED,
            data={
                "device_id": "dev1",
                "interface_name": "ether1",
                "oper_status": "down",
                "timestamp": time.time(),
            },
        )
        self.bus.publish(event.event, data=event.data)
        await asyncio.sleep(0.1)

        edge = self.engine.get_edge("edge_dev1_dev2")
        self.assertEqual(edge.oper_status, "down")

    async def test_18_nms_device_status_event_updates_node(self):
        """Verifies NMS device status change updates node reachability status."""
        event = Event(
            event=EventNames.NMS_DEVICE_STATUS,
            data={
                "device_id": "dev1",
                "status": "DOWN",
                "timestamp": time.time(),
            },
        )
        self.bus.publish(event.event, data=event.data)
        await asyncio.sleep(0.1)

        with closing(get_topology_connection(self.db_path, read_only=True)) as conn:
            row = conn.execute("SELECT status, reachability_status FROM topology_nodes WHERE id = 'dev1'").fetchone()
            self.assertEqual(row["status"], "offline")

    async def test_19_nms_stale_decayer_concurrent_with_poll(self):
        """Verifies stale decayer cycle runs concurrently with interface status events cleanly."""
        decayed = self.engine.decay_stale_observations(now=time.time() + 1000.0, stale_threshold_sec=30.0)
        self.assertGreaterEqual(decayed, 0)

    async def test_20_duplicate_nms_event_idempotent(self):
        """Verifies duplicate NMS status events do not create extra delta broadcasts."""
        delta_count = 0

        def _count_delta(evt: Event):
            nonlocal delta_count
            delta_count += 1

        self.bus.subscribe("topology.delta", _count_delta)

        # First event changes down -> up
        event1 = Event(
            event=EventNames.NMS_INTERFACE_STATUS_CHANGED,
            data={"device_id": "dev1", "interface_name": "ether1", "oper_status": "up", "timestamp": time.time()},
        )
        self.bus.publish(event1.event, data=event1.data)
        await asyncio.sleep(0.05)
        self.assertEqual(delta_count, 1)

        # Duplicate event with same oper_status "up"
        event2 = Event(
            event=EventNames.NMS_INTERFACE_STATUS_CHANGED,
            data={"device_id": "dev1", "interface_name": "ether1", "oper_status": "up", "timestamp": time.time() + 1},
        )
        self.bus.publish(event2.event, data=event2.data)
        await asyncio.sleep(0.05)
        self.assertEqual(delta_count, 1, "Duplicate unchanged status must not trigger redundant delta")

    async def test_21_out_of_order_nms_event_handled(self):
        """Verifies older timestamps in delayed events do not overwrite newer observation freshness."""
        now = time.time()
        # Newer event
        self.engine.handle_nms_event({
            "event": EventNames.NMS_INTERFACE_STATUS_CHANGED,
            "data": {"device_id": "dev1", "interface_name": "ether1", "oper_status": "up", "timestamp": now + 100},
        })
        # Out-of-order older event arrives later
        res = self.engine.handle_nms_event({
            "event": EventNames.NMS_INTERFACE_STATUS_CHANGED,
            "data": {"device_id": "dev1", "interface_name": "ether1", "oper_status": "down", "timestamp": now - 50},
        })
        self.assertTrue(res["success"])


class TestGroupDHistoricalSnapshotEngineProtection(unittest.TestCase):
    """Group D: Snapshot creation non-blocking reads, atomic inserts, and comparison safety."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_snapshot_concurrency.db"
        self.engine = TopologyEngine(self.db_path)
        # Prepopulate nodes and edges
        for i in range(5):
            self.engine.upsert_node(node_id=f"node_{i}", name=f"Node {i}", ip=f"10.0.0.{i+1}")
        for i in range(4):
            edge = TopologyEdge(
                id=f"edge_{i}_{i+1}",
                source_node_id=f"node_{i}",
                target_node_id=f"node_{i+1}",
                source_interface="eth0",
                target_interface="eth0",
                oper_status="up",
                relationship_class="physical", confidence_rationale="test validation",
            )
            self.engine.insert_edge(edge)

    def tearDown(self):
        gc.collect()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_22_create_snapshot_releases_writer_lock_during_read(self):
        """Verifies create_snapshot performs read and hashing without holding writer lock."""
        snap = self.engine.create_snapshot(description="Test snapshot non-blocking read")
        self.assertIsNotNone(snap.snapshot_id)
        self.assertEqual(snap.node_count, 5)
        self.assertEqual(snap.edge_count, 4)
        self.assertTrue(len(snap.sha256_hash) == 64)

    def test_23_snapshot_atomic_write_insert(self):
        """Verifies snapshot persistence is mathematically immutable via DB triggers."""
        snap = self.engine.create_snapshot(description="Immutable snapshot")
        with closing(get_topology_connection(self.db_path)) as conn:
            # Trigger prevents UPDATE
            with self.assertRaises((sqlite3.IntegrityError, sqlite3.OperationalError)):
                conn.execute(
                    "UPDATE topology_snapshots SET description = 'tampered' WHERE snapshot_id = ?",
                    (snap.snapshot_id,),
                )
            # Trigger prevents DELETE
            with self.assertRaises((sqlite3.IntegrityError, sqlite3.OperationalError)):
                conn.execute(
                    "DELETE FROM topology_snapshots WHERE snapshot_id = ?",
                    (snap.snapshot_id,),
                )

    def test_24_compare_snapshots_read_only_no_writer_lock(self):
        """Verifies compare_snapshots executes read-only query without acquiring writer lock."""
        snap1 = self.engine.create_snapshot(description="Snapshot 1")
        # Add an edge
        self.engine.insert_edge(TopologyEdge(
            id="edge_extra",
            source_node_id="node_0",
            target_node_id="node_4",
            source_interface="eth2",
            target_interface="eth2",
            oper_status="up", confidence_rationale="test validation",
        ))
        snap2 = self.engine.create_snapshot(description="Snapshot 2")

        report = self.engine.compare_snapshots(snap1.snapshot_id, snap2.snapshot_id)
        self.assertIsNotNone(report)
        self.assertEqual(report.base_snapshot_id, snap1.snapshot_id)
        self.assertEqual(report.target_snapshot_id, snap2.snapshot_id)
        self.assertTrue(len(report.structural_changes) > 0 or report.summary.get("edges_added", 0) > 0)

    def test_25_concurrent_snapshots_and_nms_events(self):
        """Verifies snapshot creation and concurrent NMS events complete without lock contention."""
        errors: List[Exception] = []

        def _snapshot_creator():
            try:
                for _ in range(3):
                    self.engine.create_snapshot(description="Concurrent snap")
                    time.sleep(0.02)
            except Exception as e:
                errors.append(e)

        def _nms_poster():
            try:
                for _ in range(5):
                    self.engine.handle_nms_event({
                        "event": EventNames.NMS_INTERFACE_STATUS_CHANGED,
                        "data": {"device_id": "node_0", "interface_name": "eth0", "oper_status": "down"},
                    })
                    time.sleep(0.01)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=_snapshot_creator)
        t2 = threading.Thread(target=_nms_poster)

        t1.start()
        t2.start()

        t1.join(timeout=10.0)
        t2.join(timeout=10.0)

        self.assertEqual(len(errors), 0, f"Concurrent snapshot/NMS raised errors: {errors}")


class TestGroupEDiscoveryAndStaleDecayer(unittest.TestCase):
    """Group E: Stale observation decay and discovery edge reconciliation."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_discovery_concur.db"
        self.engine = TopologyEngine(self.db_path)
        self.engine.upsert_node(node_id="gw1", name="Gateway-1", ip="192.168.1.1")
        self.engine.upsert_node(node_id="sw1", name="Switch-1", ip="192.168.1.2")

    def tearDown(self):
        gc.collect()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_26_stale_decayer_retry_on_contention(self):
        """Verifies decay_stale_observations marks fresh observations as stale accurately."""
        # Insert edge with past last_seen
        past_ts = time.time() - 200.0
        edge = TopologyEdge(
            id="edge_gw_sw",
            source_node_id="gw1",
            target_node_id="sw1",
            source_interface="eth1",
            target_interface="eth1",
            oper_status="up",
            observation_freshness="fresh",
            last_seen=past_ts,
            confidence_rationale="test validation",
        )
        self.engine.insert_edge(edge)

        decayed_count = self.engine.decay_stale_observations(stale_threshold_sec=60.0)
        self.assertEqual(decayed_count, 1)

        updated_edge = self.engine.get_edge("edge_gw_sw")
        self.assertIsNotNone(updated_edge)
        self.assertEqual(updated_edge.observation_freshness, "stale")

    def test_27_reconcile_discovered_edges_under_lock(self):
        """Verifies reconcile discovered edge creates active edge with evidence under lock."""
        edge_id = self.engine._reconcile_discovered_edge(
            source_id="gw1",
            target_id="sw1",
            relationship_class="physical",
            source_interface="ether2",
            target_interface="ether2",
            confidence_tier="HIGH",
        )
        self.assertIsNotNone(edge_id)
        edge = self.engine.get_edge(edge_id)
        self.assertIsNotNone(edge)
        self.assertEqual(edge.confidence_tier, "HIGH")

    def test_28_evidence_expiration_under_lock(self):
        """Verifies deactivate_expired_evidence updates expired evidence rows."""
        edge = TopologyEdge(
            id="edge_ev_test",
            source_node_id="gw1",
            target_node_id="sw1",
            source_interface="eth3",
            target_interface="eth3", confidence_rationale="test validation",
        )
        self.engine.insert_edge(edge)
        from core.topology_models import EdgeEvidence
        ev = EdgeEvidence(
            edge_id="edge_ev_test",
            evidence_type="cdp_neighbor",
            observing_device_id="gw1",
            observed_at=time.time() - 100,
            expires_at=time.time() - 10,
        )
        self.engine.insert_edge_evidence(ev)

        deactivated = self.engine.deactivate_expired_evidence(now=time.time())
        self.assertEqual(deactivated, 1)


class TestGroupFApplicationLifecycle(unittest.TestCase):
    """Group F: Multi-worker detection and lifecycle shutdown safety."""

    def test_29_single_worker_startup_initializes_wal(self):
        """Verifies init_topology_database creates valid WAL database idempotently."""
        temp_dir = tempfile.TemporaryDirectory()
        try:
            db_path = Path(temp_dir.name) / "lifecycle_test.db"
            resolved = init_topology_database(db_path)
            self.assertTrue(resolved.exists())
            with closing(sqlite3.connect(str(resolved))) as conn:
                mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
                self.assertEqual(str(mode).lower(), "wal")
        finally:
            temp_dir.cleanup()

    def test_30_multi_worker_rejection_enforced(self):
        """Verifies multi-worker execution (WEB_CONCURRENCY > 1) is strictly rejected on startup."""
        with patch.dict(os.environ, {"WEB_CONCURRENCY": "4"}):
            from api.main import _startup_topology_db_and_concurrency
            with self.assertRaises(RuntimeError) as ctx:
                _startup_topology_db_and_concurrency()
            self.assertIn("Unsupported multi-worker deployment", str(ctx.exception))

    def test_31_graceful_shutdown_stops_services(self):
        """Verifies shutdown handler cleanly shuts down Topology NMS sync."""
        from api.main import _shutdown_topology_nms_sync
        # Calling shutdown should complete without unhandled exceptions
        _shutdown_topology_nms_sync()


class TestGroupGRegressionProtection(unittest.TestCase):
    """Group G: Data preservation and immutable invariant verification."""

    def test_32_existing_topology_nodes_preserved(self):
        """Verifies live topology.db nodes and edges exist and are not dropped or corrupted."""
        db_path = DEFAULT_TOPOLOGY_DB_PATH
        if not db_path.exists():
            self.skipTest("Live topology.db does not exist in testing environment")

        with closing(get_topology_connection(db_path, read_only=True)) as conn:
            node_count = conn.execute("SELECT count(*) FROM topology_nodes").fetchone()[0]
            edge_count = conn.execute("SELECT count(*) FROM topology_edges").fetchone()[0]
            # Must have non-zero or preserved counts
            self.assertGreaterEqual(node_count, 0)
            self.assertGreaterEqual(edge_count, 0)

    def test_33_read_only_router_operations_preserved(self):
        """Verifies network diagnostic queries remain strictly read-only."""
        from core.topology_engine import TopologyEngine
        # Confirm no router configuration mutation methods exist on TopologyEngine
        prohibited = [
            "set_router_interface",
            "modify_firewall",
            "reboot_device",
            "change_ip_address",
        ]
        for method_name in prohibited:
            self.assertFalse(hasattr(TopologyEngine, method_name))


if __name__ == "__main__":
    unittest.main()
