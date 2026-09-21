"""
tests/test_global_settings.py — unit tests for the Global Settings Engine
(Sprint 2.6, Worker 1).

Each test uses a TEMPORARY sqlite file (tempfile) - never touches
database/global_settings.db in a real checkout.

Run from AIRA_ECOSYSTEM/:
    python -m unittest tests.test_global_settings -v
"""

import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

from core.global_settings import (
    KNOWN_KEYS,
    SETTINGS_SCHEMA,
    GlobalSettingsStore,
    default_settings,
)


class TempStoreCase(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db_path = Path(self._tmp.name) / "global_settings_test.db"

    def store(self, **kwargs):
        return GlobalSettingsStore(self.db_path, **kwargs)


# ============================================================ defaults

class TestDefaults(TempStoreCase):

    def test_schema_covers_all_required_keys(self):
        required = {
            "display_name", "nickname", "assistant_name", "timezone",
            "language", "theme", "voice_enabled", "greeting_style",
        }
        self.assertEqual(required, KNOWN_KEYS)

    def test_default_settings_matches_schema_defaults(self):
        defaults = default_settings()
        for key, spec in SETTINGS_SCHEMA.items():
            self.assertEqual(defaults[key], spec["default"])

    def test_fresh_store_seeds_defaults(self):
        store = self.store()
        result = store.read_all()

        self.assertTrue(result["success"])
        self.assertEqual(result["settings"], default_settings())

    def test_seed_is_idempotent_and_does_not_touch_existing_value(self):
        store = self.store()
        store.write("nickname", "Rin-kun")

        # Re-open the store (re-triggers _seed_missing_defaults on init).
        reopened = self.store()

        self.assertEqual(reopened.read("nickname")["value"], "Rin-kun")


# ============================================================ read

class TestRead(TempStoreCase):

    def test_read_known_key(self):
        store = self.store()
        result = store.read("assistant_name")

        self.assertTrue(result["success"])
        self.assertEqual(result["value"], "AIRA")

    def test_read_unknown_key_fails(self):
        store = self.store()
        result = store.read("does_not_exist")

        self.assertFalse(result["success"])
        self.assertIn("tidak dikenal", result["error"])

    def test_read_all_returns_every_key(self):
        store = self.store()
        result = store.read_all()

        self.assertEqual(set(result["settings"].keys()), KNOWN_KEYS)
        self.assertEqual(set(result["updated_at"].keys()), KNOWN_KEYS)


# ============================================================ write / update

class TestWrite(TempStoreCase):

    def test_write_updates_value_and_persists(self):
        store = self.store()
        result = store.write("display_name", "Lingga W.")

        self.assertTrue(result["success"])
        self.assertEqual(store.read("display_name")["value"], "Lingga W.")

    def test_write_persists_across_store_instances(self):
        self.store().write("theme", "midnight-violet")

        self.assertEqual(self.store().read("theme")["value"], "midnight-violet")

    def test_write_strips_whitespace(self):
        store = self.store()
        store.write("nickname", "  Rin  ")

        self.assertEqual(store.read("nickname")["value"], "Rin")

    def test_write_boolean_accepts_bool_and_string(self):
        store = self.store()

        self.assertTrue(store.write("voice_enabled", False)["success"])
        self.assertFalse(store.read("voice_enabled")["value"])

        self.assertTrue(store.write("voice_enabled", "true")["success"])
        self.assertTrue(store.read("voice_enabled")["value"])

    def test_write_updates_updated_at(self):
        store = self.store()
        before = store.read("theme")["updated_at"]

        time.sleep(0.01)
        store.write("theme", "arctic-blue")

        after = store.read("theme")["updated_at"]
        self.assertGreater(after, before)

    def test_write_publishes_settings_changed_event(self):
        received = []

        try:
            from core.events import event_bus
        except ImportError:
            self.skipTest("core.events not importable in this environment")

        token = event_bus.subscribe("settings.changed", lambda e: received.append(e.data))
        try:
            self.store().write("nickname", "EventTest")
        finally:
            event_bus.unsubscribe("settings.changed", token)

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0], {"key": "nickname", "value": "EventTest"})


# ============================================================ validation

class TestValidation(TempStoreCase):

    def test_unknown_key_is_rejected(self):
        store = self.store()
        result = store.write("not_a_real_setting", "x")

        self.assertFalse(result["success"])
        self.assertIn("tidak dikenal", result["error"])

    def test_empty_string_rejected_for_plain_text_fields(self):
        store = self.store()
        for key in ("display_name", "nickname", "assistant_name"):
            result = store.write(key, "   ")
            self.assertFalse(result["success"], key)

    def test_string_too_long_rejected(self):
        store = self.store()
        result = store.write("display_name", "x" * 81)

        self.assertFalse(result["success"])

    def test_invalid_timezone_rejected(self):
        store = self.store()
        result = store.write("timezone", "Not/AZone")

        self.assertFalse(result["success"])
        self.assertIn("timezone", result["error"])

    def test_valid_timezone_accepted(self):
        store = self.store()
        result = store.write("timezone", "America/New_York")

        self.assertTrue(result["success"])

    def test_invalid_language_rejected(self):
        store = self.store()
        result = store.write("language", "indonesian")

        self.assertFalse(result["success"])

    def test_valid_language_accepted(self):
        store = self.store()
        self.assertTrue(store.write("language", "en")["success"])
        self.assertTrue(store.write("language", "en-US")["success"])

    def test_invalid_theme_rejected(self):
        store = self.store()
        result = store.write("theme", "Not A Theme!")

        self.assertFalse(result["success"])

    def test_valid_theme_accepted(self):
        store = self.store()
        self.assertTrue(store.write("theme", "arctic-blue")["success"])

    def test_invalid_greeting_style_rejected(self):
        store = self.store()
        result = store.write("greeting_style", "sarcastic")

        self.assertFalse(result["success"])
        self.assertIn("greeting_style", result["error"])

    def test_valid_greeting_style_choices_accepted(self):
        store = self.store()
        for value in ("default", "casual", "formal"):
            self.assertTrue(store.write("greeting_style", value)["success"])

    def test_non_boolean_value_rejected_for_boolean_field(self):
        store = self.store()
        result = store.write("voice_enabled", "not-a-bool")

        self.assertFalse(result["success"])

    def test_non_string_value_rejected_for_string_field(self):
        store = self.store()
        result = store.write("nickname", 12345)

        self.assertFalse(result["success"])

    def test_failed_write_does_not_change_stored_value(self):
        store = self.store()
        store.write("theme", "arctic-blue")

        store.write("theme", "INVALID THEME")

        self.assertEqual(store.read("theme")["value"], "arctic-blue")


# ============================================================ missing keys / reset

class TestMissingKeysAndReset(TempStoreCase):

    def test_read_unseeded_key_falls_back_to_default_without_writing(self):
        store = self.store(seed=False)

        result = store.read("assistant_name")

        self.assertTrue(result["success"])
        self.assertEqual(result["value"], "AIRA")
        self.assertIsNone(result["updated_at"])

        # NOTE: sqlite3.Connection used as `with conn:` only commits/rolls
        # back the transaction - it does NOT close the connection. Without
        # closing() here, the underlying file handle stays open and
        # tempfile's cleanup fails on Windows (WinError 32: file in use).
        with closing(store._connect()) as conn:  # noqa: SLF001 - white-box check for this test only
            row = conn.execute("SELECT COUNT(*) AS c FROM global_settings").fetchone()
            self.assertEqual(row["c"], 0)

    def test_reset_to_defaults(self):
        store = self.store()
        store.write("nickname", "Changed")
        store.write("voice_enabled", False)

        result = store.reset_to_defaults()

        self.assertEqual(result["settings"], default_settings())


if __name__ == "__main__":
    unittest.main()