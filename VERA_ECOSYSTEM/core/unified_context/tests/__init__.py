"""
core/unified_context/tests/test_unified_context.py — unit tests for
Unified Context (Sprint 2.7 / Wave 2 / W9).

A fully-stubbed core.context.ContextBuilder is injected (no database/disk
access - same technique core/context/builder.py's own DI supports), plus
stub attachment/artifact providers, so these tests never touch a real
Workspace, SQLite database, or network.

Run from AIRA_ECOSYSTEM/:
    python -m unittest core.unified_context.tests.test_unified_context -v
"""

import json
import unittest

from core.context import ContextBuilder
from core.selection.models import SelectionContext
from core.unified_context import (
    ALL_SOURCES,
    SOURCE_ARTIFACT,
    SOURCE_ATTACHMENT,
    SOURCE_CONVERSATION,
    SOURCE_LOCATION,
    SOURCE_PERMISSION,
    SOURCE_SELECTION,
    UnifiedContext,
    UnifiedContextBuilder,
)


def _stub_persona_state():
    return {
        "profile": {"assistant_name": "AIRA", "language": "id", "timezone": "Asia/Jakarta"},
        "behavior": {"professionalism": 86},
    }


def _stub_prompt_composer(extra_context: str) -> str:
    return ("=== SYSTEM ===\n" + extra_context).strip()


def _make_context_builder(*, with_location=True, with_tools=True) -> ContextBuilder:
    return ContextBuilder(
        persona_state=_stub_persona_state,
        prompt_composer=_stub_prompt_composer,
        memory_text=lambda: "Fakta: router utama R1.",
        runtime_text=lambda: "Waktu saat ini: Jumat, 25 September 2026.",
        location_text=(lambda sid: "Lokasi user: Bandung." if (sid and with_location) else None),
        tool_summary=(lambda: {"count": 1, "names": ["ping"], "categories": {"ping": "network"}}) if with_tools else None,
    )


class _FakeAttachment:
    def __init__(self, id_, status="available", is_deleted=False):
        self.id = id_
        self.session_id = "s1"
        self.message_id = None
        self.name = f"{id_}.pdf"
        self.mime_type = "application/pdf"
        self.size = 10
        self.storage_reference = f"Attachments/{id_}.pdf"
        self.source = "user_upload"
        self.status = status
        self.created_at = 0.0
        self.is_deleted = is_deleted

    def to_dict(self):
        return {
            "id": self.id, "session_id": self.session_id, "message_id": self.message_id,
            "name": self.name, "mime_type": self.mime_type, "size": self.size,
            "storage_reference": self.storage_reference, "source": self.source,
            "status": self.status, "created_at": self.created_at,
        }


class _FakeArtifact:
    def __init__(self, id_, status="ready"):
        self.id = id_
        self.session_id = "s1"
        self.name = f"{id_}.docx"
        self.artifact_type = "docx"
        self.mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        self.size = 500
        self.storage_reference = f"Artifacts/{id_}.docx"
        self.source = "generated"
        self.status = status
        self.created_at = 0.0
        self.metadata = {}

    def to_dict(self):
        return {
            "id": self.id, "session_id": self.session_id, "name": self.name,
            "artifact_type": self.artifact_type, "mime_type": self.mime_type,
            "size": self.size, "storage_reference": self.storage_reference,
            "source": self.source, "status": self.status,
            "created_at": self.created_at, "metadata": self.metadata,
        }


def _builder(**kwargs) -> UnifiedContextBuilder:
    return UnifiedContextBuilder(
        context_builder=kwargs.pop("context_builder", _make_context_builder()),
        attachments_provider=kwargs.pop("attachments_provider", lambda sid: []),
        artifacts_provider=kwargs.pop("artifacts_provider", lambda sid: []),
    )


# ============================================================ INDIVIDUAL SOURCES

class TestConversationSourceOnly(unittest.TestCase):

    def test_conversation_and_location_present(self):
        unified = _builder().build("cek R1", session_id="s1")

        self.assertIn(SOURCE_CONVERSATION, unified.present_sources())
        self.assertIn(SOURCE_LOCATION, unified.present_sources())
        self.assertNotIn(SOURCE_ATTACHMENT, unified.present_sources())
        self.assertNotIn(SOURCE_SELECTION, unified.present_sources())
        self.assertNotIn(SOURCE_ARTIFACT, unified.present_sources())
        self.assertNotIn(SOURCE_PERMISSION, unified.present_sources())

    def test_system_prompt_matches_underlying_context_builder(self):
        cb = _make_context_builder()
        expected = cb.build("cek R1", session_id="s1").system_prompt

        unified = _builder(context_builder=_make_context_builder()).build("cek R1", session_id="s1")

        self.assertEqual(unified.system_prompt, expected)

    def test_conversation_items_carry_provenance_and_source(self):
        unified = _builder().build("cek R1", session_id="s1")
        items = unified.items(SOURCE_CONVERSATION)

        self.assertTrue(items)
        for item in items:
            self.assertEqual(item.source, SOURCE_CONVERSATION)
            self.assertIn("origin", item.provenance)

    def test_location_item_is_separate_from_conversation(self):
        unified = _builder().build("dimana aku?", session_id="s1")
        location_items = unified.items(SOURCE_LOCATION)

        self.assertEqual(len(location_items), 1)
        self.assertEqual(location_items[0].id, "location")
        self.assertIn("Bandung", location_items[0].text)
        # location must not also appear inside the conversation source's items
        conv_ids = {i.id for i in unified.items(SOURCE_CONVERSATION)}
        self.assertNotIn("location", conv_ids)


class TestAttachmentSourceOnly(unittest.TestCase):

    def test_explicit_attachments_populate_source(self):
        unified = _builder().build(
            "lihat file ini", session_id="s1",
            attachments=[_FakeAttachment("att_1")],
        )

        self.assertIn(SOURCE_ATTACHMENT, unified.present_sources())
        items = unified.items(SOURCE_ATTACHMENT)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].id, "att_1")
        self.assertEqual(items[0].data["storage_reference"], "Attachments/att_1.pdf")

    def test_deleted_attachment_excluded(self):
        unified = _builder().build(
            "x", session_id="s1",
            attachments=[_FakeAttachment("att_1", is_deleted=True)],
        )
        self.assertEqual(unified.items(SOURCE_ATTACHMENT), [])

    def test_default_provider_used_when_not_explicit(self):
        calls = []

        def provider(session_id):
            calls.append(session_id)
            return [_FakeAttachment("att_default")]

        unified = _builder(attachments_provider=provider).build("x", session_id="s1")

        self.assertEqual(calls, ["s1"])
        self.assertEqual(unified.items(SOURCE_ATTACHMENT)[0].id, "att_default")

    def test_no_binary_content_in_attachment_item(self):
        unified = _builder().build("x", session_id="s1", attachments=[_FakeAttachment("att_1")])
        item = unified.items(SOURCE_ATTACHMENT)[0]

        self.assertNotIn("content", item.data)
        self.assertNotIn("bytes", item.data)


class TestSelectionSourceOnly(unittest.TestCase):

    def test_explicit_selection_populates_source(self):
        selection = SelectionContext(selected_text="VRRP pakai virtual IP", session_id="s1")
        unified = _builder().build("jelaskan ini", session_id="s1", selections=[selection])

        items = unified.items(SOURCE_SELECTION)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].id, selection.selection_id)
        self.assertEqual(items[0].text, "VRRP pakai virtual IP")

    def test_no_default_lookup_selection_always_absent_unless_passed(self):
        unified = _builder().build("x", session_id="s1")
        self.assertEqual(unified.items(SOURCE_SELECTION), [])
        self.assertNotIn(SOURCE_SELECTION, unified.present_sources())


class TestArtifactSourceOnly(unittest.TestCase):

    def test_explicit_artifacts_populate_source(self):
        unified = _builder().build("x", session_id="s1", artifacts=[_FakeArtifact("artifact_1")])
        items = unified.items(SOURCE_ARTIFACT)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].data["storage_reference"], "Artifacts/artifact_1.docx")


class TestPermissionSourceOnly(unittest.TestCase):

    def test_pending_and_confirmed_permissions(self):
        unified = _builder().build(
            "x", session_id="s1",
            pending_permissions=[{"id": "workspace.write_file", "reason": "butuh simpan file"}],
            confirmed_permissions=["net.ping"],
        )

        items = unified.items(SOURCE_PERMISSION)
        ids = {i.id for i in items}

        self.assertIn("workspace.write_file", ids)
        self.assertIn("__confirmed__", ids)
        confirmed_item = next(i for i in items if i.id == "__confirmed__")
        self.assertEqual(confirmed_item.data["confirmed_ids"], ["net.ping"])

    def test_string_shortcut_for_pending_permission(self):
        unified = _builder().build("x", session_id="s1", pending_permissions=["net.ping"])
        self.assertEqual(unified.items(SOURCE_PERMISSION)[0].id, "net.ping")


# ============================================================ MIXED SOURCES

class TestMixedSources(unittest.TestCase):

    def test_all_six_sources_together(self):
        selection = SelectionContext(selected_text="teks terpilih", session_id="s1")

        unified = _builder().build(
            "tolong bantu", session_id="s1",
            attachments=[_FakeAttachment("att_1")],
            selections=[selection],
            artifacts=[_FakeArtifact("artifact_1")],
            pending_permissions=[{"id": "workspace.write_file"}],
            confirmed_permissions=["net.ping"],
        )

        self.assertEqual(set(unified.present_sources()), set(ALL_SOURCES))
        self.assertEqual(
            set(unified.context_types()),
            {"conversation", "attachment", "selection", "artifact", "location", "permission"},
        )

    def test_all_items_flattens_every_present_source(self):
        unified = _builder().build(
            "x", session_id="s1",
            attachments=[_FakeAttachment("att_1")],
            artifacts=[_FakeArtifact("artifact_1")],
        )
        flat = unified.all_items()
        sources_seen = {item.source for item in flat}

        self.assertIn(SOURCE_ATTACHMENT, sources_seen)
        self.assertIn(SOURCE_ARTIFACT, sources_seen)
        self.assertIn(SOURCE_CONVERSATION, sources_seen)

    def test_for_discovery_matches_context_types(self):
        unified = _builder().build("x", session_id="s1", attachments=[_FakeAttachment("att_1")])
        self.assertEqual(unified.for_discovery(), {"context": unified.context_types()})


# ============================================================ MISSING SOURCES

class TestMissingSources(unittest.TestCase):

    def test_no_session_id_drops_location_and_default_lookups(self):
        unified = _builder().build("halo", session_id=None)

        self.assertNotIn(SOURCE_LOCATION, unified.present_sources())
        self.assertNotIn(SOURCE_ATTACHMENT, unified.present_sources())
        self.assertNotIn(SOURCE_ARTIFACT, unified.present_sources())
        # conversation still works without a session (terminal mode)
        self.assertIn(SOURCE_CONVERSATION, unified.present_sources())

    def test_explicit_empty_list_means_none_not_default_lookup(self):
        calls = []

        def provider(session_id):
            calls.append(session_id)
            return [_FakeAttachment("should_not_appear")]

        unified = _builder(attachments_provider=provider).build(
            "x", session_id="s1", attachments=[],
        )

        self.assertEqual(calls, [])  # default provider never invoked
        self.assertEqual(unified.items(SOURCE_ATTACHMENT), [])

    def test_conversation_source_failure_is_isolated(self):
        class BoomBuilder:
            def build(self, *a, **k):
                raise RuntimeError("classifier down")

        unified = _builder(context_builder=BoomBuilder()).build("x", session_id="s1")

        conv = unified.get(SOURCE_CONVERSATION)
        self.assertFalse(conv.available)
        self.assertTrue(any("conversation" in w for w in unified.warnings))
        # other sources still build fine
        self.assertEqual(unified.system_prompt, "")

    def test_attachment_source_failure_does_not_break_others(self):
        def boom(session_id):
            raise RuntimeError("db down")

        unified = _builder(attachments_provider=boom).build("x", session_id="s1")

        att_source = unified.get(SOURCE_ATTACHMENT)
        self.assertFalse(att_source.available)
        self.assertIn(SOURCE_CONVERSATION, unified.present_sources())
        self.assertTrue(any(w.startswith("attachment:") for w in unified.warnings))


# ============================================================ DEDUPLICATION

class TestDeduplication(unittest.TestCase):

    def test_duplicate_attachment_ids_collapse(self):
        unified = _builder().build(
            "x", session_id="s1",
            attachments=[_FakeAttachment("att_1"), _FakeAttachment("att_1")],
        )
        items = unified.items(SOURCE_ATTACHMENT)

        self.assertEqual(len(items), 1)
        self.assertIn("duplicate_origins", items[0].provenance)


# ============================================================ SERIALIZATION

class TestSerialization(unittest.TestCase):

    def test_to_dict_is_json_dumpable(self):
        unified = _builder().build(
            "x", session_id="s1",
            attachments=[_FakeAttachment("att_1")],
            artifacts=[_FakeArtifact("artifact_1")],
        )
        json.dumps(unified.to_dict())  # must not raise

    def test_to_json_round_trip_preserves_sources(self):
        unified = _builder().build(
            "x", session_id="s1",
            attachments=[_FakeAttachment("att_1")],
            selections=[SelectionContext(selected_text="abc", session_id="s1")],
        )
        restored = UnifiedContext.from_dict(json.loads(unified.to_json()))

        self.assertEqual(set(restored.present_sources()), set(unified.present_sources()))
        self.assertEqual(restored.system_prompt, unified.system_prompt)
        self.assertEqual(
            [i.id for i in restored.items(SOURCE_ATTACHMENT)],
            [i.id for i in unified.items(SOURCE_ATTACHMENT)],
        )

    def test_include_prompt_false_omits_system_prompt(self):
        unified = _builder().build("x", session_id="s1")
        data = unified.to_dict(include_prompt=False)
        self.assertNotIn("system_prompt", data)

    def test_from_dict_tolerates_garbage(self):
        restored = UnifiedContext.from_dict({"sources": "not a dict", "task": "also wrong"})
        self.assertEqual(restored.sources, {})
        self.assertIsNone(restored.task)

    def test_from_dict_of_non_mapping_does_not_raise(self):
        restored = UnifiedContext.from_dict(None)
        self.assertEqual(restored.present_sources(), [])


# ============================================================ BACKWARD COMPATIBILITY

class TestBackwardCompatibility(unittest.TestCase):

    def test_underlying_context_builder_still_works_standalone(self):
        """core.context.ContextBuilder itself must be completely untouched -
        building an AIRAContext directly, with no Unified Context involved
        at all, must behave exactly as before."""
        cb = _make_context_builder()
        context = cb.build("halo", session_id="s1")

        self.assertTrue(context.system_prompt)
        self.assertIsNotNone(context.identity)
        self.assertIsNotNone(context.location)

    def test_conversation_context_escape_hatch_matches_original_shape(self):
        cb = _make_context_builder()
        original = cb.build("halo", session_id="s1")

        unified = _builder(context_builder=_make_context_builder()).build("halo", session_id="s1")

        self.assertEqual(
            unified.conversation_context["identity"],
            original.to_dict(include_prompt=False)["identity"],
        )

    def test_unified_context_with_zero_optional_sources_still_serializes(self):
        """A caller that never passes attachments/selections/artifacts/
        permissions (i.e. code written before those existed) still gets a
        fully valid, serializable UnifiedContext."""
        unified = _builder().build("halo", session_id=None)
        data = unified.to_dict()

        json.dumps(data)
        self.assertEqual(data["present_sources"], [SOURCE_CONVERSATION])


if __name__ == "__main__":
    unittest.main()