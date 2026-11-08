"""
core/dio/tests/dio/test_reasoning.py — unit test mode selection
(Phase 2.2).

Jalankan dari root AIRA_ECOSYSTEM/:
    python -m unittest core.dio.tests.dio.test_reasoning -v
"""

import unittest

from core.dio.models import InteractionPlan, MissingField, ChoiceOption
from core.dio.reasoning import select_mode
from core.dio.constants import (
    MODE_DISPLAY, MODE_TEXT, MODE_CHOICE, MODE_MIXED,
    MODE_FORM, MODE_WIZARD, MODE_APPROVAL, MODE_REVIEW,
)


def _plan(**kwargs) -> InteractionPlan:
    defaults = dict(intent="test_intent")
    defaults.update(kwargs)
    return InteractionPlan(**defaults)


class TestModeSelection(unittest.TestCase):

    def test_no_missing_data_is_display(self):
        plan = _plan(missing_data=[])
        self.assertEqual(select_mode(plan), MODE_DISPLAY)

    def test_single_missing_text_field_is_text(self):
        plan = _plan(missing_data=[MissingField(key="folder_name")])
        self.assertEqual(select_mode(plan), MODE_TEXT)

    def test_choices_only_is_choice(self):
        plan = _plan(
            missing_data=[],
            choices=[ChoiceOption(value="ssh", label="SSH"), ChoiceOption(value="snmp", label="SNMP")],
        )
        self.assertEqual(select_mode(plan), MODE_CHOICE)

    def test_choice_plus_manual_input_is_mixed(self):
        plan = _plan(
            missing_data=[MissingField(key="custom_note")],
            choices=[ChoiceOption(value="ssh", label="SSH")],
        )
        self.assertEqual(select_mode(plan), MODE_MIXED)

    def test_more_than_two_missing_is_form(self):
        plan = _plan(missing_data=[
            MissingField(key="a"), MissingField(key="b"), MissingField(key="c"),
        ])
        self.assertEqual(select_mode(plan), MODE_FORM)

    def test_wizard_context_flag(self):
        plan = _plan(
            missing_data=[MissingField(key="a"), MissingField(key="b"), MissingField(key="c")],
            context={"wizard": True},
        )
        self.assertEqual(select_mode(plan), MODE_WIZARD)

    def test_danger_flag_forces_approval(self):
        plan = _plan(missing_data=[], danger=True)
        self.assertEqual(select_mode(plan), MODE_APPROVAL)

    def test_needs_review_forces_review(self):
        plan = _plan(missing_data=[], needs_review=True)
        self.assertEqual(select_mode(plan), MODE_REVIEW)

    def test_danger_overrides_needs_review(self):
        plan = _plan(missing_data=[], danger=True, needs_review=True)
        self.assertEqual(select_mode(plan), MODE_APPROVAL)


if __name__ == "__main__":
    unittest.main()