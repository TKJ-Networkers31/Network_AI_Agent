"""
core/dio/tests/dio/test_analyzer.py — unit test DIOAnalyzer (Phase 2.1).

Jalankan dari root AIRA_ECOSYSTEM/:
    python -m unittest core.dio.tests.dio.test_analyzer -v
"""

import tempfile
import unittest
from pathlib import Path

from core.dio.analyzer import DIOAnalyzer
from core.dio.interaction_memory import InteractionMemory
from core.dio.constants import MODE_TEXT, MODE_DISPLAY


class TestDIOAnalyzer(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.tmp_dir.name) / "interaction_memory_test.db"
        self.memory = InteractionMemory(db_path=db_path)
        self.analyzer = DIOAnalyzer(memory=self.memory)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_basic_intent_and_missing(self):
        planner_output = {
            "intent": "create_folder",
            "confidence": 0.9,
            "known_data": {"workspace": "Projects"},
            "missing_data": [{"key": "folder_name", "label": "Nama Folder"}],
        }
        plan = self.analyzer.analyze("buat folder baru", planner_output)
        self.assertEqual(plan.intent, "create_folder")
        self.assertEqual(len(plan.missing_data), 1)
        self.assertEqual(plan.suggested_mode, MODE_TEXT)

    def test_interaction_memory_closes_gap(self):
        self.memory.save("folder_name", "sudah-pernah-diisi")

        planner_output = {
            "intent": "create_folder",
            "missing_data": [{"key": "folder_name", "label": "Nama Folder"}],
        }
        plan = self.analyzer.analyze("buat folder baru", planner_output)

        self.assertEqual(len(plan.missing_data), 0)
        self.assertEqual(plan.known_data.get("folder_name"), "sudah-pernah-diisi")
        self.assertEqual(plan.suggested_mode, MODE_DISPLAY)

    def test_danger_flag_propagates(self):
        planner_output = {"intent": "delete_rule", "danger": True}
        plan = self.analyzer.analyze("hapus rule", planner_output)
        self.assertTrue(plan.danger)

    def test_string_shortcut_for_missing_field(self):
        planner_output = {"intent": "rename_file", "missing_data": ["new_name"]}
        plan = self.analyzer.analyze("rename file", planner_output)
        self.assertEqual(plan.missing_data[0].key, "new_name")


if __name__ == "__main__":
    unittest.main()