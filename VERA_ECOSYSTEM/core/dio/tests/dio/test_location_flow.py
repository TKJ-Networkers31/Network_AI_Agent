"""
core/dio/tests/dio/test_location_flow.py — unit test alur DIO
location_permission (Worker 3: DIO + Location).

Jalankan dari root AIRA_ECOSYSTEM/:
    python -m unittest core.dio.tests.dio.test_location_flow -v
"""

import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from core.dio.constants import MODE_LOCATION_PERMISSION, EVENT_INTERACTION_REQUESTED
from core.dio.interaction_memory import InteractionMemory
from core.location.models import SOURCE_BROWSER
from core.location.service import LocationService
from core.location.store import HostLocationStore
from core.events import event_bus

import agents.rei.dio_tools as dio_tools


def _make_env(tmp_dir):
    interaction_memory = InteractionMemory(db_path=Path(tmp_dir) / "interaction_memory_test.db")
    host_store = HostLocationStore(db_path=Path(tmp_dir) / "location_test.db")
    location_service = LocationService(store=host_store)
    return interaction_memory, location_service


class TestLocationPermissionRequest(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.memory, self.location_service = _make_env(self.tmp_dir.name)

        self.patches = [
            mock.patch.object(dio_tools, "get_interaction_memory", return_value=self.memory),
            mock.patch.object(dio_tools, "location_service", self.location_service),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp_dir.cleanup()

    def test_missing_location_triggers_permission_schema(self):
        result = dio_tools.request_location_permission(
            original_request="aku ada di mana sekarang?",
            reason="Untuk menjawab lokasimu.",
            session_id="sess-1",
        )

        self.assertTrue(result["success"])
        schema = result["interaction_schema"]
        self.assertEqual(schema["mode"], MODE_LOCATION_PERMISSION)

        pending_key = f"{dio_tools.LOCATION_PENDING_KEY_PREFIX}{schema['id']}"
        pending = self.memory.load(pending_key)

        self.assertIsNotNone(pending)
        self.assertEqual(pending["original_request"], "aku ada di mana sekarang?")
        self.assertEqual(pending["session_id"], "sess-1")
        self.assertIn("created_at", pending)

    def test_grant_permission_persists_location_and_resumes(self):
        created = dio_tools.request_location_permission(
            original_request="cuaca di sekitarku gimana?",
            session_id="sess-2",
        )
        schema_id = created["interaction_schema"]["id"]

        submit_result = dio_tools.submit_structured_input(
            schema_id=schema_id,
            action_id="grant_location",
            values={"latitude": -6.9, "longitude": 107.6, "accuracy": 15},
        )

        self.assertTrue(submit_result["success"])
        self.assertTrue(submit_result["location_result"]["granted"])

        access = self.location_service.get_access("sess-2", resolve=False)
        self.assertIsNotNone(access)
        self.assertAlmostEqual(access.latitude, -6.9)
        self.assertAlmostEqual(access.longitude, 107.6)
        self.assertEqual(access.source, SOURCE_BROWSER)

        display, llm_message = dio_tools.build_submission_message(
            {"schema_id": schema_id, "action_id": "grant_location", "values": {}},
            pending_location=submit_result["pending_location"],
            location_result=submit_result["location_result"],
        )
        self.assertIn("cuaca di sekitarku gimana?", llm_message)

        # Pending request harus sudah dibersihkan (sekali pakai).
        self.assertIsNone(self.memory.load(f"{dio_tools.LOCATION_PENDING_KEY_PREFIX}{schema_id}"))

    def test_deny_permission_does_not_persist_location(self):
        created = dio_tools.request_location_permission(
            original_request="restoran terdekat apa?", session_id="sess-3",
        )
        schema_id = created["interaction_schema"]["id"]

        submit_result = dio_tools.submit_structured_input(
            schema_id=schema_id, action_id="deny_location", values={},
        )

        self.assertFalse(submit_result["location_result"]["granted"])
        self.assertIsNone(self.location_service.get_access("sess-3", resolve=False))

        display, llm_message = dio_tools.build_submission_message(
            {"schema_id": schema_id, "action_id": "deny_location", "values": {}},
            pending_location=submit_result["pending_location"],
            location_result=submit_result["location_result"],
        )
        self.assertIn("TIDAK", llm_message)
        self.assertIn("restoran terdekat apa?", llm_message)

    def test_invalid_coordinates_rejected(self):
        created = dio_tools.request_location_permission(
            original_request="aku di mana?", session_id="sess-4",
        )
        schema_id = created["interaction_schema"]["id"]

        submit_result = dio_tools.submit_structured_input(
            schema_id=schema_id, action_id="grant_location",
            values={"latitude": 999, "longitude": 107.6},
        )

        self.assertFalse(submit_result["location_result"]["granted"])
        self.assertEqual(submit_result["location_result"]["reason"], "invalid_coordinates")
        self.assertIsNone(self.location_service.get_access("sess-4", resolve=False))

    def test_malformed_non_numeric_coordinates_rejected(self):
        created = dio_tools.request_location_permission(
            original_request="aku di mana?", session_id="sess-5",
        )
        schema_id = created["interaction_schema"]["id"]

        submit_result = dio_tools.submit_structured_input(
            schema_id=schema_id, action_id="grant_location",
            values={"latitude": "bukan-angka", "longitude": 107.6},
        )

        self.assertFalse(submit_result["location_result"]["granted"])
        self.assertEqual(submit_result["location_result"]["reason"], "invalid_coordinates")

    def test_missing_session_id_is_handled_gracefully(self):
        created = dio_tools.request_location_permission(
            original_request="aku di mana?", session_id=None,
        )
        schema_id = created["interaction_schema"]["id"]

        submit_result = dio_tools.submit_structured_input(
            schema_id=schema_id, action_id="grant_location",
            values={"latitude": -6.9, "longitude": 107.6},
        )

        self.assertFalse(submit_result["location_result"]["granted"])
        self.assertEqual(submit_result["location_result"]["reason"], "missing_session")

    def test_pending_request_expires_after_ttl(self):
        created = dio_tools.request_location_permission(
            original_request="aku di mana?", session_id="sess-6",
        )
        schema_id = created["interaction_schema"]["id"]
        pending_key = f"{dio_tools.LOCATION_PENDING_KEY_PREFIX}{schema_id}"

        current = self.memory.load(pending_key)
        self.memory.save(pending_key, current, ttl_seconds=0.01)
        time.sleep(0.05)

        submit_result = dio_tools.submit_structured_input(
            schema_id=schema_id, action_id="grant_location",
            values={"latitude": -6.9, "longitude": 107.6},
        )

        # Pending sudah expired -> diperlakukan sebagai submission generik,
        # bukan location grant.
        self.assertIsNone(submit_result["location_result"])


class TestLocationEventPublication(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.memory, self.location_service = _make_env(self.tmp_dir.name)

        self.patches = [
            mock.patch.object(dio_tools, "get_interaction_memory", return_value=self.memory),
            mock.patch.object(dio_tools, "location_service", self.location_service),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp_dir.cleanup()

    def test_interaction_requested_event_published(self):
        received = []
        token = event_bus.subscribe(EVENT_INTERACTION_REQUESTED, lambda e: received.append(e.data))

        try:
            dio_tools.request_location_permission(
                original_request="aku di mana?", session_id="sess-evt",
            )
            time.sleep(0.1)
            self.assertTrue(any(d.get("intent") == "location_permission" for d in received))
        finally:
            event_bus.unsubscribe(EVENT_INTERACTION_REQUESTED, token)

    def test_location_updated_event_published_on_grant(self):
        received = []
        token = event_bus.subscribe("location.updated", lambda e: received.append(e.data))

        try:
            created = dio_tools.request_location_permission(
                original_request="aku di mana?", session_id="sess-evt2",
            )
            schema_id = created["interaction_schema"]["id"]

            dio_tools.submit_structured_input(
                schema_id=schema_id, action_id="grant_location",
                values={"latitude": -6.9, "longitude": 107.6},
            )
            time.sleep(0.1)
            self.assertTrue(any(d.get("session_id") == "sess-evt2" for d in received))
        finally:
            event_bus.unsubscribe("location.updated", token)


class TestNormalChatDoesNotTriggerLocation(unittest.TestCase):
    """
    Tool lokasi murni opt-in oleh LLM (dipanggil hanya lewat tool-call
    eksplisit) - memastikan tool DIO lain yang tidak berhubungan dengan
    lokasi TIDAK PERNAH memicu event permintaan izin lokasi.
    """

    def test_generic_interaction_does_not_publish_location_requested_event(self):
        received = []
        token = event_bus.subscribe(EVENT_INTERACTION_REQUESTED, lambda e: received.append(e.data))

        try:
            with tempfile.TemporaryDirectory() as tmp:
                memory, _ = _make_env(tmp)
                with mock.patch.object(dio_tools, "get_interaction_memory", return_value=memory):
                    dio_tools.request_structured_input(
                        intent="create_folder",
                        missing_fields=[{"key": "folder_name"}],
                    )
            time.sleep(0.1)
            self.assertEqual(received, [])
        finally:
            event_bus.unsubscribe(EVENT_INTERACTION_REQUESTED, token)


if __name__ == "__main__":
    unittest.main()