"""
tests/test_ws_bridge.py — unit test bridge Event Bus -> WebSocket (Worker 1).

Memakai EventBus baru + sender palsu (tanpa FastAPI/WebSocket asli), jadi
yang diuji adalah: pemetaan event, filter sesi/run, pengiriman dari thread
pekerja, urutan, isolasi error sender, dan lifecycle bridge.

Jalankan dari root AIRA_ECOSYSTEM/:
    python -m unittest tests.test_ws_bridge -v
"""

import asyncio
import json
import unittest
from pathlib import Path

from api.ws_bridge import DEFAULT_WS_EVENT_MAP, WebSocketEventBridge
from core.events import EventBus, EventNames, event_scope


class FakeSender:

    def __init__(self, fail_first: int = 0):
        self.sent: list[tuple[str, dict]] = []
        self._fail_first = fail_first

    async def __call__(self, session_id: str, payload: dict) -> None:
        if self._fail_first > 0:
            self._fail_first -= 1
            raise RuntimeError("socket putus (sengaja)")
        self.sent.append((session_id, payload))

    def types(self, session_id=None):
        return [
            payload["type"]
            for sid, payload in self.sent
            if session_id is None or sid == session_id
        ]


def make_bridge(fail_first: int = 0):
    bus = EventBus()
    sender = FakeSender(fail_first)
    return bus, sender, WebSocketEventBridge(bus=bus, sender=sender)


class TestTranslate(unittest.TestCase):

    def _translate(self, event_name, data=None, **scope):
        bus, _, bridge = make_bridge()

        with event_scope(**scope):
            event = bus.publish(event_name, data=data)

        return bridge.translate(event)

    def test_peta_ke_protokol_lama(self):
        harapan = {
            EventNames.THINKING_START: "thinking",
            EventNames.TOOL_START: "tool_start",
            EventNames.TOOL_PROGRESS: "tool_progress",
            EventNames.TOOL_FINISH: "tool_finish",
            EventNames.SYSTEM_ERROR: "error",
        }
        self.assertEqual(DEFAULT_WS_EVENT_MAP, harapan)

        for nama_bus, tipe_ws in harapan.items():
            hasil = self._translate(nama_bus, {"x": 1}, session_id="s1", run_id="r1")
            self.assertEqual(hasil[1]["type"], tipe_ws)

    def test_payload_membawa_session_dan_run_id(self):
        session_id, payload = self._translate(
            EventNames.TOOL_START,
            {"name": "ping", "category": "network", "arguments": {"target": "8.8.8.8"}},
            session_id="s1", run_id="r1", correlation_id="c1",
        )

        self.assertEqual(session_id, "s1")
        self.assertEqual(payload["type"], "tool_start")
        self.assertEqual(payload["data"]["name"], "ping")
        self.assertEqual(payload["data"]["session_id"], "s1")
        self.assertEqual(payload["data"]["run_id"], "r1")
        self.assertEqual(payload["correlation_id"], "c1")
        self.assertIn("ts", payload)

    def test_tanpa_run_id_tidak_diteruskan(self):
        # giliran REST (/api/chat): ada session tapi tidak ada run_id
        self.assertIsNone(
            self._translate(EventNames.TOOL_START, {}, session_id="s1")
        )

    def test_tanpa_konteks_tidak_diteruskan(self):
        self.assertIsNone(self._translate(EventNames.TOOL_START, {}))

    def test_event_tak_terpetakan_tidak_diteruskan(self):
        for nama in (
            EventNames.RESPONSE_READY, EventNames.TASK_STARTED,
            EventNames.MODEL_FAILED, EventNames.THINKING_FINISH,
        ):
            self.assertIsNone(
                self._translate(nama, {}, session_id="s1", run_id="r1")
            )

    def test_data_json_safe(self):
        _, payload = self._translate(
            EventNames.TOOL_FINISH,
            {"path": Path("a/b"), "obj": object()},
            session_id="s1", run_id="r1",
        )

        json.dumps(payload)  # tidak boleh raise
        self.assertEqual(payload["data"]["path"], str(Path("a/b")))


class TestDelivery(unittest.IsolatedAsyncioTestCase):

    async def test_event_dari_thread_pekerja_sampai_ke_sender(self):
        bus, sender, bridge = make_bridge()
        bridge.start(asyncio.get_running_loop())

        def worker():
            with event_scope(session_id="s1", run_id="r1", correlation_id="c1"):
                bus.publish(EventNames.THINKING_START, data={"message": "Berpikir..."})
                bus.publish(EventNames.TOOL_START, data={"name": "ping"})
                bus.publish(EventNames.TOOL_FINISH, data={"name": "ping", "success": True})

        await asyncio.to_thread(worker)
        self.assertTrue(await bridge.flush())

        self.assertEqual(sender.types(), ["thinking", "tool_start", "tool_finish"])
        self.assertTrue(all(sid == "s1" for sid, _ in sender.sent))

        await bridge.stop()

    async def test_flush_menjamin_event_tool_tiba_sebelum_response(self):
        bus, sender, bridge = make_bridge()
        bridge.start(asyncio.get_running_loop())

        def worker():
            with event_scope(session_id="s1", run_id="r1"):
                for i in range(50):
                    bus.publish(EventNames.TOOL_PROGRESS, data={"i": i})

        await asyncio.to_thread(worker)
        await bridge.flush()

        # meniru ws.py: "response" dikirim langsung SETELAH flush
        await sender("s1", {"type": "response", "data": {}})

        self.assertEqual(sender.types()[:-1], ["tool_progress"] * 50)
        self.assertEqual(sender.types()[-1], "response")
        self.assertEqual([p["data"]["i"] for _, p in sender.sent[:-1]], list(range(50)))

        await bridge.stop()

    async def test_filter_sesi_event_tidak_tertukar(self):
        bus, sender, bridge = make_bridge()
        bridge.start(asyncio.get_running_loop())

        def worker(session_id, run_id, nama):
            with event_scope(session_id=session_id, run_id=run_id):
                bus.publish(EventNames.TOOL_START, data={"name": nama})

        await asyncio.gather(
            asyncio.to_thread(worker, "s1", "r1", "ping-s1"),
            asyncio.to_thread(worker, "s2", "r2", "ping-s2"),
        )
        await bridge.flush()

        nama_s1 = [p["data"]["name"] for sid, p in sender.sent if sid == "s1"]
        nama_s2 = [p["data"]["name"] for sid, p in sender.sent if sid == "s2"]

        self.assertEqual(nama_s1, ["ping-s1"])
        self.assertEqual(nama_s2, ["ping-s2"])

        await bridge.stop()

    async def test_giliran_tanpa_run_id_tidak_bocor(self):
        bus, sender, bridge = make_bridge()
        bridge.start(asyncio.get_running_loop())

        with event_scope(session_id="s1"):  # REST: tidak ada run_id
            bus.publish(EventNames.TOOL_START, data={"name": "ping"})

        await bridge.flush()

        self.assertEqual(sender.sent, [])

        await bridge.stop()

    async def test_error_sender_tidak_mematikan_consumer(self):
        bus, sender, bridge = make_bridge(fail_first=1)
        bridge.start(asyncio.get_running_loop())

        with event_scope(session_id="s1", run_id="r1"):
            with self.assertLogs("aira.ws.bridge", level="ERROR"):
                bus.publish(EventNames.TOOL_START, data={"name": "a"})
                bus.publish(EventNames.TOOL_START, data={"name": "b"})
                await bridge.flush()

        # event pertama gagal terkirim, event kedua tetap sampai
        self.assertEqual([p["data"]["name"] for _, p in sender.sent], ["b"])

        await bridge.stop()


class TestLifecycle(unittest.IsolatedAsyncioTestCase):

    async def test_start_idempotent(self):
        bus, sender, bridge = make_bridge()
        loop = asyncio.get_running_loop()

        bridge.start(loop)
        bridge.start(loop)
        bridge.ensure_started(loop)

        self.assertEqual(bus.subscriber_count("*"), 1)
        self.assertIs(bus.loop, loop)

        await bridge.stop()

    async def test_stop_berhenti_menerima_event(self):
        bus, sender, bridge = make_bridge()
        bridge.start(asyncio.get_running_loop())
        self.assertTrue(bridge.is_started)

        await bridge.stop()

        self.assertFalse(bridge.is_started)
        self.assertEqual(bus.subscriber_count("*"), 0)
        self.assertIsNone(bus.loop)

        with event_scope(session_id="s1", run_id="r1"):
            bus.publish(EventNames.TOOL_START, data={"name": "ping"})

        self.assertEqual(sender.sent, [])

    async def test_flush_sebelum_start_langsung_true(self):
        _, _, bridge = make_bridge()
        self.assertTrue(await bridge.flush())

    async def test_restart_di_loop_baru_tidak_menggandakan_subscriber(self):
        bus, sender, bridge = make_bridge()
        loop = asyncio.get_running_loop()

        bridge.start(loop)
        await bridge.stop()
        bridge.start(loop)

        self.assertEqual(bus.subscriber_count("*"), 1)

        await bridge.stop()


if __name__ == "__main__":
    unittest.main()
