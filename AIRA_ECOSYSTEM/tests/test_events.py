"""
tests/test_events.py — unit test Event Bus (Worker 1).

Setiap test memakai EventBus BARU (bukan singleton global), jadi tidak
saling mengganggu dan tidak menyentuh subscriber aplikasi asli.

Jalankan dari root AIRA_ECOSYSTEM/:
    python -m unittest tests.test_events -v
"""

import asyncio
import json
import threading
import unittest
from dataclasses import FrozenInstanceError
from datetime import datetime
from pathlib import Path

from core.events import (
    Event,
    EventBus,
    EventNames,
    STANDARD_EVENTS,
    WILDCARD,
    current_event_context,
    event_scope,
    json_safe,
)

EVENTBUS_LOGGER = "aira.eventbus"


class TestEventContract(unittest.TestCase):

    def test_semua_field_kontrak_ada(self):
        bus = EventBus()

        event = bus.publish(
            EventNames.TOOL_START,
            source="AKANE", agent="AKANE", tool="ssh",
            data={"device": "R1"}, metadata={"env": "lab"},
        )

        payload = event.to_dict()

        for key in (
            "event_id", "correlation_id", "event", "source", "agent",
            "tool", "timestamp", "data", "metadata",
        ):
            self.assertIn(key, payload)

        self.assertEqual(payload["event"], "tool.start")
        self.assertEqual(payload["source"], "AKANE")
        self.assertEqual(payload["tool"], "ssh")
        self.assertEqual(payload["data"], {"device": "R1"})
        self.assertEqual(payload["metadata"], {"env": "lab"})

    def test_timestamp_utc(self):
        parsed = datetime.fromisoformat(EventBus().publish("x").timestamp)

        self.assertIsNotNone(parsed.tzinfo)
        self.assertEqual(parsed.utcoffset().total_seconds(), 0)

    def test_event_id_unik(self):
        bus = EventBus()
        self.assertNotEqual(bus.publish("x").event_id, bus.publish("x").event_id)

    def test_event_immutable(self):
        event = EventBus().publish("x", data={"a": 1})

        with self.assertRaises(FrozenInstanceError):
            event.event = "lain"

    def test_data_disalin_saat_publish(self):
        bus = EventBus()
        original = {"a": 1}

        event = bus.publish("x", data=original)
        original["a"] = 999

        self.assertEqual(event.data, {"a": 1})

    def test_event_names_lengkap(self):
        wajib = {
            "chat.received", "thinking.start", "thinking.finish",
            "task.classified", "task.started", "task.finished",
            "model.started", "model.finished", "model.failed",
            "model.switched", "model.selected", "model.fallback",
            "tool.start", "tool.progress", "tool.finish",
            "response.ready", "memory.saved",
            "interaction.requested", "interaction.completed",
            "interaction.cancelled",
            "location.updated", "location.cleared", "system.error",
        }
        self.assertTrue(wajib <= STANDARD_EVENTS, wajib - STANDARD_EVENTS)

    def test_event_kosong_ditolak(self):
        bus = EventBus()

        with self.assertRaises(ValueError):
            bus.publish("")

        with self.assertRaises(ValueError):
            bus.subscribe("", lambda e: None)

        with self.assertRaises(TypeError):
            bus.subscribe("x", "bukan-callable")


class TestSerialization(unittest.TestCase):

    def test_to_json_dict_menangani_objek_non_serializable(self):
        bus = EventBus()

        event = bus.publish("x", data={"path": Path("a/b"), "obj": object()})

        with self.assertRaises(TypeError):
            json.dumps(event.to_dict())

        hasil = event.to_json_dict()
        json.dumps(hasil)  # tidak boleh raise

        self.assertEqual(hasil["data"]["path"], str(Path("a/b")))

    def test_json_safe_fallback_untuk_struktur_rusak(self):
        self.assertIsInstance(json_safe({(1, 2): "kunci-tuple"}), str)
        self.assertEqual(json_safe({"a": [1, 2]}), {"a": [1, 2]})


class TestSubscribe(unittest.TestCase):

    def test_publish_subscribe_sinkron(self):
        bus = EventBus()
        received = []

        bus.subscribe(EventNames.TOOL_START, lambda e: received.append(e.event))
        bus.publish(EventNames.TOOL_START)

        # tanpa sleep: subscriber sync selesai sebelum publish() return
        self.assertEqual(received, ["tool.start"])

    def test_event_lain_tidak_diterima(self):
        bus = EventBus()
        received = []

        bus.subscribe("a", lambda e: received.append(e.event))
        bus.publish("b")

        self.assertEqual(received, [])

    def test_banyak_subscriber_urut_daftar(self):
        bus = EventBus()
        urutan = []

        bus.subscribe("x", lambda e: urutan.append("pertama"))
        bus.subscribe("x", lambda e: urutan.append("kedua"))
        bus.subscribe("x", lambda e: urutan.append("ketiga"))
        bus.publish("x")

        self.assertEqual(urutan, ["pertama", "kedua", "ketiga"])
        self.assertEqual(bus.subscriber_count("x"), 3)

    def test_wildcard_menerima_semua(self):
        bus = EventBus()
        received = []

        bus.subscribe(WILDCARD, lambda e: received.append(e.event))
        bus.publish("a")
        bus.publish("b")

        self.assertEqual(received, ["a", "b"])

    def test_spesifik_lalu_wildcard(self):
        bus = EventBus()
        urutan = []

        bus.subscribe(WILDCARD, lambda e: urutan.append("wildcard"))
        bus.subscribe("x", lambda e: urutan.append("spesifik"))
        bus.publish("x")

        self.assertEqual(urutan, ["spesifik", "wildcard"])

    def test_unsubscribe(self):
        bus = EventBus()
        received = []

        token = bus.subscribe("x", lambda e: received.append(1))

        self.assertTrue(bus.unsubscribe("x", token))
        self.assertFalse(bus.unsubscribe("x", token))

        bus.publish("x")
        self.assertEqual(received, [])
        self.assertEqual(bus.subscriber_count(), 0)

    def test_unsubscribe_hanya_yang_dituju(self):
        bus = EventBus()
        received = []

        token_a = bus.subscribe("x", lambda e: received.append("a"))
        bus.subscribe("x", lambda e: received.append("b"))
        bus.unsubscribe("x", token_a)
        bus.publish("x")

        self.assertEqual(received, ["b"])

    def test_clear(self):
        bus = EventBus()
        bus.subscribe("a", lambda e: None)
        bus.subscribe("b", lambda e: None)

        bus.clear("a")
        self.assertEqual(bus.subscriber_count(), 1)

        bus.clear()
        self.assertEqual(bus.subscriber_count(), 0)

    def test_subscriber_boleh_unsubscribe_diri_sendiri_saat_dispatch(self):
        bus = EventBus()
        received = []
        token_holder = {}

        def once(event):
            received.append(event.event)
            bus.unsubscribe("x", token_holder["token"])

        token_holder["token"] = bus.subscribe("x", once)

        bus.publish("x")
        bus.publish("x")

        self.assertEqual(received, ["x"])


class TestCorrelation(unittest.TestCase):

    def test_child_mewarisi_correlation_dan_metadata(self):
        bus = EventBus()

        induk = bus.publish(
            "chat.received", correlation_id="abc", source="BRAIN",
            metadata={"session_id": "s1"},
        )
        anak = induk.child("thinking.start", data={"m": 1})

        self.assertEqual(anak.correlation_id, "abc")
        self.assertEqual(anak.event, "thinking.start")
        self.assertEqual(anak.source, "BRAIN")
        self.assertEqual(anak.metadata["session_id"], "s1")
        self.assertNotEqual(anak.event_id, induk.event_id)

    def test_publish_tanpa_correlation_membuat_id_baru(self):
        bus = EventBus()
        self.assertNotEqual(
            bus.publish("x").correlation_id, bus.publish("x").correlation_id
        )

    def test_scope_menempelkan_correlation_dan_metadata(self):
        bus = EventBus()

        with event_scope(correlation_id="c1", session_id="s1", run_id="r1"):
            a = bus.publish("x")
            b = bus.publish("y")

        self.assertEqual(a.correlation_id, "c1")
        self.assertEqual(b.correlation_id, "c1")
        self.assertEqual(a.metadata, {"session_id": "s1", "run_id": "r1"})

    def test_scope_selesai_konteks_bersih(self):
        bus = EventBus()

        with event_scope(correlation_id="c1", session_id="s1"):
            pass

        event = bus.publish("x")

        self.assertNotEqual(event.correlation_id, "c1")
        self.assertEqual(event.metadata, {})
        self.assertEqual(current_event_context(), {})

    def test_correlation_eksplisit_menimpa_scope(self):
        bus = EventBus()

        with event_scope(correlation_id="dari-scope"):
            event = bus.publish("x", correlation_id="eksplisit")

        self.assertEqual(event.correlation_id, "eksplisit")

    def test_scope_bersarang_digabung(self):
        bus = EventBus()

        with event_scope(correlation_id="c1", session_id="s1"):
            with event_scope(run_id="r9"):
                event = bus.publish("x")

        self.assertEqual(event.correlation_id, "c1")
        self.assertEqual(event.metadata, {"session_id": "s1", "run_id": "r9"})

    def test_scope_ikut_ke_thread_pekerja(self):
        async def skenario():
            bus = EventBus()
            got = []
            bus.subscribe("x", got.append)

            with event_scope(correlation_id="c-thread", session_id="s1", run_id="r1"):
                await asyncio.to_thread(bus.publish, "x")

            return got

        got = asyncio.run(skenario())

        self.assertEqual(len(got), 1)
        self.assertEqual(got[0].correlation_id, "c-thread")
        self.assertEqual(got[0].metadata["session_id"], "s1")


class TestSubscriberErrors(unittest.TestCase):

    def test_error_sync_tidak_mengganggu_subscriber_lain(self):
        bus = EventBus()
        received = []

        def rusak(event):
            raise RuntimeError("sengaja")

        bus.subscribe("x", rusak)
        bus.subscribe("x", lambda e: received.append(e.event))

        with self.assertLogs(EVENTBUS_LOGGER, level="ERROR"):
            event = bus.publish("x")  # tidak boleh raise

        self.assertEqual(received, ["x"])
        self.assertEqual(event.event, "x")
        self.assertEqual(bus.stats()["failed_callbacks"], 1)

    def test_error_async_tidak_mengganggu(self):
        bus = EventBus()
        received = []

        async def rusak(event):
            raise RuntimeError("sengaja")

        bus.subscribe("x", rusak)
        bus.subscribe("x", lambda e: received.append(e.event))

        with self.assertLogs(EVENTBUS_LOGGER, level="ERROR"):
            bus.publish("x")

        self.assertEqual(received, ["x"])
        self.assertEqual(bus.stats()["failed_callbacks"], 1)

    def test_stats(self):
        bus = EventBus()
        bus.subscribe("x", lambda e: None)
        bus.publish("x")
        bus.publish("x")

        self.assertEqual(bus.stats()["published"], 2)

        bus.reset_stats()
        self.assertEqual(bus.stats()["published"], 0)


class TestAsyncDispatch(unittest.TestCase):

    def test_subscriber_async_tanpa_loop_selesai_sebelum_publish_return(self):
        bus = EventBus()
        received = []

        async def handler(event):
            received.append(event.event)

        bus.subscribe("x", handler)
        bus.publish("x")  # thread ini tidak punya loop -> fallback asyncio.run

        self.assertEqual(received, ["x"])

    def test_di_dalam_loop_subscriber_sync_tetap_inline(self):
        async def skenario():
            bus = EventBus()
            received = []
            bus.subscribe("x", lambda e: received.append(e.event))
            bus.publish("x")
            return list(received)  # tanpa await apa pun

        self.assertEqual(asyncio.run(skenario()), ["x"])

    def test_subscriber_async_dari_thread_pekerja_jalan_di_loop_terikat(self):
        thread_utama = threading.get_ident()

        async def skenario():
            loop = asyncio.get_running_loop()
            bus = EventBus()
            bus.bind_loop(loop)

            seen = {}
            selesai = asyncio.Event()

            async def handler(event):
                seen["loop"] = asyncio.get_running_loop()
                seen["thread"] = threading.get_ident()
                selesai.set()

            bus.subscribe("x", handler)

            await asyncio.to_thread(bus.publish, "x")
            await asyncio.wait_for(selesai.wait(), 2)

            self.assertIs(seen["loop"], loop)
            self.assertEqual(seen["thread"], thread_utama)

        asyncio.run(skenario())

    def test_subscriber_async_dipublish_dari_loop_sendiri_dijadwalkan(self):
        async def skenario():
            bus = EventBus()
            bus.bind_loop(asyncio.get_running_loop())
            selesai = asyncio.Event()

            async def handler(event):
                selesai.set()

            bus.subscribe("x", handler)
            bus.publish("x")

            await asyncio.wait_for(selesai.wait(), 2)

        asyncio.run(skenario())

    def test_publish_async_menunggu_subscriber_async(self):
        async def skenario():
            bus = EventBus()
            urutan = []

            async def lambat(event):
                await asyncio.sleep(0.05)
                urutan.append("async-selesai")

            bus.subscribe("x", lambat)
            bus.subscribe("x", lambda e: urutan.append("sync"))

            await bus.publish_async("x")
            urutan.append("publish-return")

            return urutan

        self.assertEqual(
            asyncio.run(skenario()),
            ["sync", "async-selesai", "publish-return"],
        )

    def test_unbind_loop(self):
        async def skenario():
            bus = EventBus()
            loop = asyncio.get_running_loop()

            bus.bind_loop(loop)
            self.assertIs(bus.loop, loop)

            bus.unbind_loop(loop)
            self.assertIsNone(bus.loop)

        asyncio.run(skenario())


if __name__ == "__main__":
    unittest.main()
