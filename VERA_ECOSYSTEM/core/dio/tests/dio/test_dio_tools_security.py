"""
core/dio/tests/dio/test_dio_tools_security.py — test validator di
request_structured_input, filter key sensitif, dan event tanpa nilai.

Jalankan dari root AIRA_ECOSYSTEM/:
    python -m unittest core.dio.tests.dio.test_dio_tools_security -v
"""

import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from core.dio.interaction_memory import InteractionMemory
from core.events import event_bus

import agents.rei.dio_tools as dio_tools


class TestValidatorWired(unittest.TestCase):

    def test_select_tanpa_options_dikembalikan_sebagai_gagal(self):
        result = dio_tools.request_structured_input(
            intent="pick_device",
            missing_fields=[{"key": "device", "data_type": "choice", "options": []}],
        )

        self.assertFalse(result["success"])
        self.assertIn("issues", result)
        self.assertTrue(any(i["code"] == "empty_option" for i in result["issues"]))

    def test_schema_valid_tetap_sukses(self):
        result = dio_tools.request_structured_input(
            intent="create_folder",
            missing_fields=[{"key": "folder_name", "label": "Nama Folder"}],
        )

        self.assertTrue(result["success"])
        self.assertIn("interaction_schema", result)


class TestSensitiveKeys(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.memory = InteractionMemory(db_path=Path(self.tmp.name) / "im.db")
        self.patch = mock.patch.object(dio_tools, "get_interaction_memory", return_value=self.memory)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_password_tidak_disimpan_tapi_host_disimpan_dengan_namespace(self):
        result = dio_tools.submit_structured_input(
            schema_id="schema_x", action_id="submit",
            values={"host": "10.0.0.1", "password": "rahasia", "snmp_community": "private"},
        )

        self.assertEqual(self.memory.load("schema_x:host"), "10.0.0.1")
        self.assertIsNone(self.memory.load("schema_x:password"))
        self.assertIsNone(self.memory.load("schema_x:snmp_community"))
        self.assertIsNone(self.memory.load("password"))
        self.assertEqual(result["saved_keys"], ["host"])

    def test_event_completed_tidak_membawa_nilai(self):
        received = []
        token = event_bus.subscribe("interaction.completed", lambda e: received.append(e.data))

        try:
            dio_tools.submit_structured_input(
                schema_id="schema_y", action_id="submit",
                values={"host": "10.0.0.1", "password": "rahasia"},
            )
            time.sleep(0.05)
        finally:
            event_bus.unsubscribe("interaction.completed", token)

        self.assertEqual(len(received), 1)
        self.assertNotIn("values", received[0])
        self.assertEqual(sorted(received[0]["keys"]), ["host", "password"])
        self.assertNotIn("rahasia", str(received[0]))

    def test_display_message_memasker_password(self):
        display, llm = dio_tools.build_submission_message(
            {"action_id": "submit", "values": {"host": "10.0.0.1", "password": "rahasia"}}
        )

        self.assertIn("password=***", display)
        self.assertNotIn("rahasia", display)
        self.assertIn("rahasia", llm)  # LLM tetap butuh nilai aslinya


class TestResolveSubmission(unittest.TestCase):

    def test_resolve_submission_form_biasa(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = InteractionMemory(db_path=Path(tmp) / "im.db")
            with mock.patch.object(dio_tools, "get_interaction_memory", return_value=memory):
                display, llm = dio_tools.resolve_submission({
                    "schema_id": "schema_z", "action_id": "submit",
                    "values": {"folder_name": "proyek"}, "cancelled": False,
                })

        self.assertIn("folder_name=proyek", display)
        self.assertIn("proyek", llm)


if __name__ == "__main__":
    unittest.main()