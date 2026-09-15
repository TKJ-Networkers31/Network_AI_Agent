"""
core/dio/tests/dio/test_validator.py — unit test SchemaValidator
(Phase 2.5).

Jalankan dari root AIRA_ECOSYSTEM/:
    python -m unittest core.dio.tests.dio.test_validator -v
"""

import unittest

from core.dio.models import InteractionSchema, Section, Field, Action
from core.dio.validator import SchemaValidator


class TestSchemaValidator(unittest.TestCase):

    def setUp(self):
        self.validator = SchemaValidator()

    def test_valid_schema_passes(self):
        schema = InteractionSchema(
            id="s1", mode="text",
            sections=[Section(id="sec1", fields=[Field(id="f1", type="text", label="Nama")])],
            actions=[Action(id="submit", label="Kirim", style="primary")],
        )
        result = self.validator.validate(schema)
        self.assertTrue(result.is_valid)

    def test_invalid_mode(self):
        schema = InteractionSchema(id="s1", mode="not_a_real_mode",
                                    sections=[Section(id="sec1", fields=[Field(id="f1", type="text", label="X")])])
        result = self.validator.validate(schema)
        self.assertFalse(result.is_valid)
        self.assertTrue(any(i.code == "invalid_mode" for i in result.issues))

    def test_duplicate_field_id(self):
        schema = InteractionSchema(id="s1", mode="form", sections=[Section(id="sec1", fields=[
            Field(id="dup", type="text", label="A"),
            Field(id="dup", type="text", label="B"),
        ])])
        result = self.validator.validate(schema)
        self.assertFalse(result.is_valid)
        self.assertTrue(any(i.code == "duplicate_field_id" for i in result.issues))

    def test_unsupported_component(self):
        schema = InteractionSchema(id="s1", mode="form", sections=[Section(id="sec1", fields=[
            Field(id="f1", type="not_a_component", label="X"),
        ])])
        result = self.validator.validate(schema)
        self.assertFalse(result.is_valid)
        self.assertTrue(any(i.code == "unsupported_component" for i in result.issues))

    def test_missing_label(self):
        schema = InteractionSchema(id="s1", mode="form", sections=[Section(id="sec1", fields=[
            Field(id="f1", type="text", label=None),
        ])])
        result = self.validator.validate(schema)
        self.assertFalse(result.is_valid)
        self.assertTrue(any(i.code == "missing_label" for i in result.issues))

    def test_empty_option_for_select(self):
        schema = InteractionSchema(id="s1", mode="form", sections=[Section(id="sec1", fields=[
            Field(id="f1", type="select", label="Pilih", options=[]),
        ])])
        result = self.validator.validate(schema)
        self.assertFalse(result.is_valid)
        self.assertTrue(any(i.code == "empty_option" for i in result.issues))

    def test_broken_section_no_fields(self):
        schema = InteractionSchema(id="s1", mode="form", sections=[Section(id="sec1", fields=[])])
        result = self.validator.validate(schema)
        self.assertFalse(result.is_valid)
        self.assertTrue(any(i.code == "broken_section" for i in result.issues))

    def test_no_sections_at_all(self):
        schema = InteractionSchema(id="s1", mode="display", sections=[])
        result = self.validator.validate(schema)
        self.assertFalse(result.is_valid)

    def test_invalid_visible_if(self):
        schema = InteractionSchema(id="s1", mode="form", sections=[Section(id="sec1", fields=[
            Field(id="f1", type="text", label="X", visible_if={"bad": "rule"}),
        ])])
        result = self.validator.validate(schema)
        self.assertFalse(result.is_valid)
        self.assertTrue(any(i.code == "invalid_visible_if" for i in result.issues))

    def test_validator_never_raises_on_garbage(self):
        schema = InteractionSchema(id="s1", mode="form", sections=None)  # type: ignore
        try:
            result = self.validator.validate(schema)
        except Exception as exc:  # pragma: no cover
            self.fail(f"validator tidak boleh raise, tapi raise: {exc}")
        self.assertFalse(result.is_valid)


if __name__ == "__main__":
    unittest.main()