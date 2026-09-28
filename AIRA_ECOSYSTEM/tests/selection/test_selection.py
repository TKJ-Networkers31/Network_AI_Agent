"""
core/selection/tests/test_selection.py — unit test Selection Intelligence
(Sprint 2.7 / W4).

Jalankan dari root AIRA_ECOSYSTEM/:
    python -m unittest core.selection.tests.test_selection -v
"""

import tempfile
import time
import unittest
from pathlib import Path

from core.selection.builder import SelectionBuilder, build_context_packet, build_action_request, validate_action
from core.selection.models import SelectionContext, SelectionContextPacket, ContextActionRequest
from core.selection.store import SelectionStore
from core.selection.constants import VALID_ACTIONS


def fake_lookup(found=True):
    def _lookup(message_id, session_id):
        if not found:
            return None
        return {"id": message_id, "content": "VRRP menggunakan virtual IP dan prioritas master/backup untuk failover otomatis."}
    return _lookup


class TestSelectionCreation(unittest.TestCase):

    def test_create_selection_success(self):
        builder = SelectionBuilder(message_lookup=fake_lookup())
        result = builder.build(
            selected_text="VRRP menggunakan virtual IP",
            message_id="42", session_id="sess-1",
        )
        self.assertTrue(result.success)
        self.assertIsInstance(result.selection, SelectionContext)
        self.assertTrue(result.selection.selection_id.startswith("sel_"))

    def test_selection_metadata_preserved(self):
        builder = SelectionBuilder(message_lookup=fake_lookup())
        result = builder.build(
            selected_text="virtual IP", message_id="42", session_id="sess-1",
            metadata={"origin": "context_menu", "locale": "id"},
        )
        self.assertEqual(result.selection.metadata, {"origin": "context_menu", "locale": "id"})

    def test_message_association(self):
        builder = SelectionBuilder(message_lookup=fake_lookup())
        result = builder.build(selected_text="failover otomatis", message_id="42", session_id="sess-1")
        self.assertEqual(result.selection.message_id, "42")

    def test_session_association(self):
        builder = SelectionBuilder(message_lookup=fake_lookup())
        result = builder.build(
            selected_text="failover otomatis", message_id="42",
            session_id="sess-1", conversation_id="conv-1",
        )
        self.assertEqual(result.selection.session_id, "sess-1")
        self.assertEqual(result.selection.conversation_id, "conv-1")

    def test_conversation_id_defaults_to_session_id(self):
        builder = SelectionBuilder(message_lookup=fake_lookup())
        result = builder.build(selected_text="failover", message_id="42", session_id="sess-1")
        self.assertEqual(result.selection.conversation_id, "sess-1")

    def test_surrounding_context_extraction(self):
        builder = SelectionBuilder()
        full_text = "A" * 300 + "TARGET" + "B" * 300
        idx = full_text.index("TARGET")
        result = builder.build(
            selected_text="TARGET", full_text=full_text,
            start_offset=idx, end_offset=idx + len("TARGET"),
        )
        self.assertTrue(result.success)
        self.assertNotIn("TARGET", result.selection.surrounding_text)
        self.assertIn("A", result.selection.surrounding_text)
        self.assertIn("B", result.selection.surrounding_text)

    def test_surrounding_without_offsets_falls_back_to_find(self):
        builder = SelectionBuilder()
        full_text = "sebelum kalimat penting sesudah"
        result = builder.build(selected_text="kalimat penting", full_text=full_text)
        self.assertTrue(result.success)
        self.assertIn("sebelum", result.selection.surrounding_text)
        self.assertIn("sesudah", result.selection.surrounding_text)

    def test_empty_selection_rejected(self):
        builder = SelectionBuilder()
        result = builder.build(selected_text="   ")
        self.assertFalse(result.success)
        self.assertTrue(any("kosong" in e for e in result.errors))
        self.assertIsNone(result.selection)

    def test_invalid_message_rejected(self):
        builder = SelectionBuilder(message_lookup=fake_lookup(found=False))
        result = builder.build(selected_text="teks", message_id="999", session_id="sess-1")
        self.assertFalse(result.success)
        self.assertTrue(any("tidak ditemukan" in e for e in result.errors))

    def test_invalid_source_type_rejected(self):
        builder = SelectionBuilder()
        result = builder.build(selected_text="teks", source_type="document")
        self.assertFalse(result.success)


class TestActionRequest(unittest.TestCase):

    def test_validate_action_known_and_unknown(self):
        for action in VALID_ACTIONS:
            self.assertIsNone(validate_action(action))
        self.assertIsNotNone(validate_action("delete_everything"))

    def test_action_request_contract(self):
        selection = SelectionContext(selected_text="VRRP", surrounding_text="konteks sekitar")
        request, error = build_action_request(selection, "explain", user_question="jelaskan bagian ini")

        self.assertIsNone(error)
        self.assertIsInstance(request, ContextActionRequest)
        self.assertEqual(request.action, "explain")
        self.assertEqual(request.selection_id, selection.selection_id)

        data = request.to_dict()
        self.assertEqual(data["action"], "explain")
        self.assertEqual(data["packet"]["selected_text"], "VRRP")

    def test_action_request_rejects_unknown_action(self):
        selection = SelectionContext(selected_text="VRRP")
        request, error = build_action_request(selection, "not_real")
        self.assertIsNone(request)
        self.assertIsNotNone(error)


class TestContextPacket(unittest.TestCase):

    def test_build_context_packet_fields(self):
        selection = SelectionContext(
            selected_text="VRRP menggunakan virtual IP",
            surrounding_text="...router redundancy...",
            message_id="42", session_id="sess-1", conversation_id="sess-1",
        )
        packet = build_context_packet(selection, user_question="jelaskan bagian ini", action="explain")

        self.assertIsInstance(packet, SelectionContextPacket)
        self.assertEqual(packet.source, "selection")
        self.assertEqual(packet.message_id, "42")
        self.assertEqual(packet.selected_text, "VRRP menggunakan virtual IP")
        self.assertEqual(packet.user_question, "jelaskan bagian ini")
        self.assertEqual(packet.action, "explain")

    def test_to_llm_instruction_contains_selected_and_question(self):
        selection = SelectionContext(selected_text="VRRP menggunakan virtual IP", surrounding_text="router A dan B")
        packet = build_context_packet(selection, user_question="jelaskan bagian ini")
        instruction = packet.to_llm_instruction()

        self.assertIn("VRRP menggunakan virtual IP", instruction)
        self.assertIn("router A dan B", instruction)
        self.assertIn("jelaskan bagian ini", instruction)

    def test_to_llm_instruction_without_question_uses_default(self):
        selection = SelectionContext(selected_text="VRRP")
        packet = build_context_packet(selection)
        self.assertIn("Jelaskan/tindak-lanjuti", packet.to_llm_instruction())


class TestSerialization(unittest.TestCase):

    def test_selection_serialization_round_trip(self):
        original = SelectionContext(
            selected_text="VRRP", surrounding_text="konteks",
            message_id="42", session_id="sess-1", conversation_id="sess-1",
            start_offset=10, end_offset=14, metadata={"origin": "toolbar"},
        )
        restored = SelectionContext.from_dict(original.to_dict())

        self.assertEqual(original.selected_text, restored.selected_text)
        self.assertEqual(original.selection_id, restored.selection_id)
        self.assertEqual(original.metadata, restored.metadata)

    def test_from_dict_tolerates_garbage(self):
        restored = SelectionContext.from_dict({"selected_text": "x", "unknown_key": 1})
        self.assertEqual(restored.selected_text, "x")


class TestSelectionStore(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = SelectionStore(db_path=Path(self.tmp.name) / "selection_test.db")

    def tearDown(self):
        self.tmp.cleanup()

    def test_save_and_get(self):
        selection = SelectionContext(selected_text="VRRP", session_id="sess-1")
        self.store.save(selection)

        fetched = self.store.get(selection.selection_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.selected_text, "VRRP")
        self.assertEqual(fetched.session_id, "sess-1")

    def test_get_missing_returns_none(self):
        self.assertIsNone(self.store.get("sel_does_not_exist"))

    def test_ttl_expiry(self):
        selection = SelectionContext(selected_text="VRRP")
        self.store.save(selection, ttl_seconds=0.05)
        self.assertIsNotNone(self.store.get(selection.selection_id))
        time.sleep(0.1)
        self.assertIsNone(self.store.get(selection.selection_id))

    def test_ttl_zero_never_expires(self):
        selection = SelectionContext(selected_text="VRRP")
        self.store.save(selection, ttl_seconds=0)
        time.sleep(0.05)
        self.assertIsNotNone(self.store.get(selection.selection_id))

    def test_purge_expired(self):
        expiring = SelectionContext(selected_text="a")
        staying = SelectionContext(selected_text="b")
        self.store.save(expiring, ttl_seconds=0.05)
        self.store.save(staying, ttl_seconds=None)
        time.sleep(0.1)

        deleted = self.store.purge_expired()
        self.assertEqual(deleted, 1)
        self.assertIsNotNone(self.store.get(staying.selection_id))

    def test_delete(self):
        selection = SelectionContext(selected_text="VRRP")
        self.store.save(selection)
        self.assertTrue(self.store.delete(selection.selection_id))
        self.assertFalse(self.store.delete(selection.selection_id))


if __name__ == "__main__":
    unittest.main()