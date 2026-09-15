"""
core/dio/validator.py — SchemaValidator, Phase 2.5.

Validasi InteractionSchema SEBELUM dikirim ke Companion Renderer.
TIDAK PERNAH raise/crash — selalu mengembalikan ValidationResult, bahkan
untuk schema yang parah rusak (defense-in-depth via try/except).
"""

from core.dio.models import InteractionSchema, ValidationIssue, ValidationResult
from core.dio.constants import (
    SUPPORTED_MODES, SUPPORTED_COMPONENTS,
    LABEL_OPTIONAL_COMPONENTS, OPTION_REQUIRED_COMPONENTS,
)


class SchemaValidator:

    def validate(self, schema: InteractionSchema) -> ValidationResult:
        issues: list[ValidationIssue] = []

        try:
            self._check_mode(schema, issues)
            self._check_sections(schema, issues)
        except Exception as exc:  # validator TIDAK PERNAH crash caller
            issues.append(ValidationIssue(code="internal_error", message=str(exc)))

        return ValidationResult(is_valid=len(issues) == 0, issues=issues)

    def _check_mode(self, schema: InteractionSchema, issues: list[ValidationIssue]) -> None:
        if schema.mode not in SUPPORTED_MODES:
            issues.append(ValidationIssue(
                code="invalid_mode", message=f"Mode '{schema.mode}' tidak didukung.",
            ))

    def _check_sections(self, schema: InteractionSchema, issues: list[ValidationIssue]) -> None:
        seen_field_ids: set[str] = set()

        if not schema.sections:
            issues.append(ValidationIssue(
                code="broken_section", message="Schema tidak punya section sama sekali.",
            ))
            return

        for section in schema.sections:
            if not section.fields:
                issues.append(ValidationIssue(
                    code="broken_section", section_id=section.id,
                    message=f"Section '{section.id}' tidak punya field.",
                ))
                continue

            for f in section.fields:
                self._check_field(f, section, seen_field_ids, issues)

    def _check_field(self, f, section, seen_field_ids: set[str], issues: list[ValidationIssue]) -> None:
        if f.id in seen_field_ids:
            issues.append(ValidationIssue(
                code="duplicate_field_id", section_id=section.id, field_id=f.id,
                message=f"Field id '{f.id}' dipakai lebih dari sekali.",
            ))
        seen_field_ids.add(f.id)

        if f.type not in SUPPORTED_COMPONENTS:
            issues.append(ValidationIssue(
                code="unsupported_component", section_id=section.id, field_id=f.id,
                message=f"Tipe komponen '{f.type}' tidak didukung.",
            ))
            return

        if f.type not in LABEL_OPTIONAL_COMPONENTS and not f.label:
            issues.append(ValidationIssue(
                code="missing_label", section_id=section.id, field_id=f.id,
                message=f"Field '{f.id}' (tipe {f.type}) wajib punya label.",
            ))

        if f.type in OPTION_REQUIRED_COMPONENTS and not f.options:
            issues.append(ValidationIssue(
                code="empty_option", section_id=section.id, field_id=f.id,
                message=f"Field '{f.id}' (tipe {f.type}) butuh minimal satu option.",
            ))

        if f.visible_if is not None and not self._is_valid_visible_if(f.visible_if):
            issues.append(ValidationIssue(
                code="invalid_visible_if", section_id=section.id, field_id=f.id,
                message=f"visible_if pada field '{f.id}' tidak valid - butuh key 'field' dan 'equals'.",
            ))

    @staticmethod
    def _is_valid_visible_if(rule) -> bool:
        return isinstance(rule, dict) and "field" in rule and "equals" in rule