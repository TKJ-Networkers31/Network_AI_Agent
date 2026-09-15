"""
core/dio/tests/dio/test_builder.py — unit test SchemaBuilder (Phase 2.3).

Jalankan dari root AIRA_ECOSYSTEM/:
    python -m unittest core.dio.tests.dio.test_builder -v
"""

import unittest

from core.dio.models import InteractionPlan, MissingField, ChoiceOption
from core.dio.builder import SchemaBuilder
from core.dio.validator import SchemaValidator
from core.dio.constants import (
    MODE_DISPLAY, MODE_TEXT, MODE_CHOICE, MODE_MIXED,
    MODE_FORM, MODE_APPROVAL, MODE_REVIEW,
)


class TestSchemaBuilder(unittest.TestCase):

    def setUp(self):
        self.builder = SchemaBuilder()
        self.validator = SchemaValidator()

    def _assert_valid(self, schema):
        result = self.validator.validate(schema)
        self.assertTrue(result.is_valid, msg=[i.message for i in result.issues])

    def test_build_display(self):
        plan = InteractionPlan(intent="show_status", known_data={"cpu": "12%"}, missing_data=[])
        plan.suggested_mode = MODE_DISPLAY
        schema = self.builder.build_schema(plan)
        self.assertEqual(schema.mode, MODE_DISPLAY)
        self._assert_valid(schema)

    def test_build_text(self):
        plan = InteractionPlan(intent="create_folder",
                                missing_data=[MissingField(key="folder_name", label="Nama Folder")])
        plan.suggested_mode = MODE_TEXT
        schema = self.builder.build_schema(plan)
        self.assertEqual(schema.mode, MODE_TEXT)
        self.assertEqual(len(schema.sections[0].fields), 1)
        self._assert_valid(schema)

    def test_build_choice(self):
        plan = InteractionPlan(
            intent="pick_connection_mode",
            choices=[ChoiceOption(value="ssh", label="SSH"), ChoiceOption(value="snmp", label="SNMP")],
        )
        plan.suggested_mode = MODE_CHOICE
        schema = self.builder.build_schema(plan)
        self.assertEqual(schema.mode, MODE_CHOICE)
        self._assert_valid(schema)

    def test_build_mixed(self):
        plan = InteractionPlan(
            intent="pick_device",
            choices=[ChoiceOption(value="r1", label="R1")],
            missing_data=[MissingField(key="note", required=False)],
        )
        plan.suggested_mode = MODE_MIXED
        schema = self.builder.build_schema(plan)
        self.assertEqual(schema.mode, MODE_MIXED)
        self._assert_valid(schema)

    def test_build_form(self):
        plan = InteractionPlan(intent="add_device", missing_data=[
            MissingField(key="name"), MissingField(key="host"), MissingField(key="username"),
        ])
        plan.suggested_mode = MODE_FORM
        schema = self.builder.build_schema(plan)
        self.assertEqual(schema.mode, MODE_FORM)
        self.assertEqual(len(schema.sections[0].fields), 3)
        self._assert_valid(schema)

    def test_build_approval(self):
        plan = InteractionPlan(intent="delete_firewall_rule", missing_data=[], danger=True)
        plan.suggested_mode = MODE_APPROVAL
        schema = self.builder.build_schema(plan)
        self.assertEqual(schema.mode, MODE_APPROVAL)
        self.assertIn("confirm", {a.id for a in schema.actions})
        self._assert_valid(schema)

    def test_build_review(self):
        plan = InteractionPlan(
            intent="review_devices", known_data={"r1": "192.168.1.1"},
            missing_data=[], needs_review=True,
        )
        plan.suggested_mode = MODE_REVIEW
        schema = self.builder.build_schema(plan)
        self.assertEqual(schema.mode, MODE_REVIEW)
        self._assert_valid(schema)

    def test_schema_is_serializable_dict(self):
        plan = InteractionPlan(intent="add_device", missing_data=[MissingField(key="name")])
        schema = self.builder.build_schema(plan)
        data = schema.to_dict()
        self.assertIsInstance(data, dict)
        self.assertIn("sections", data)


if __name__ == "__main__":
    unittest.main()