"""
core/artifacts/validator.py - structural validation for artifact specs
(Sprint 2.7 / W5).

Same split as core/dio (builder tolerant, validator strict) and
core/plugins (manifest.py builds, validator.py checks): specs.py never
raises on bad input, this module is what decides whether a spec is safe to
hand to a generator. Never raises itself.
"""
from __future__ import annotations

from typing import Optional

from core.artifacts.models import ArtifactType, DOCUMENT_TYPES, SPREADSHEET_TYPES, PRESENTATION_TYPES
from core.artifacts.specs import (
    CsvSpec, DocumentSpec, PresentationSpec, SpreadsheetSpec, VALID_COLUMN_FORMATS,
)


class ValidationIssue:
    __slots__ = ("field", "message")

    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message

    def to_dict(self) -> dict:
        return {"field": self.field, "message": self.message}

    def __repr__(self) -> str:
        return f"{self.field}: {self.message}"


class ValidationResult:
    __slots__ = ("is_valid", "issues")

    def __init__(self, is_valid: bool, issues: Optional[list] = None):
        self.is_valid = is_valid
        self.issues = issues or []

    def to_dict(self) -> dict:
        return {"is_valid": self.is_valid, "issues": [i.to_dict() for i in self.issues]}

    def messages(self) -> list[str]:
        return [str(i) for i in self.issues]


def _result(issues: list) -> ValidationResult:
    return ValidationResult(is_valid=not issues, issues=issues)


# ------------------------------------------------------------ document

def validate_document_spec(spec: DocumentSpec) -> ValidationResult:
    issues: list[ValidationIssue] = []

    if not isinstance(spec, DocumentSpec):
        return ValidationResult(False, [ValidationIssue("spec", "harus berupa DocumentSpec.")])

    if not spec.title or not spec.title.strip():
        issues.append(ValidationIssue("title", "title wajib diisi."))

    if not spec.blocks:
        issues.append(ValidationIssue("blocks", "dokumen butuh minimal satu block (heading/paragraph/list/table)."))

    for index, block in enumerate(spec.blocks):
        prefix = f"blocks[{index}]"

        if block.type not in ("heading", "paragraph", "list", "table"):
            issues.append(ValidationIssue(prefix, f"tipe block '{block.type}' tidak dikenal."))
            continue

        if block.type == "heading":
            if not block.text.strip():
                issues.append(ValidationIssue(f"{prefix}.text", "heading butuh teks."))
            if not 1 <= block.level <= 6:
                issues.append(ValidationIssue(f"{prefix}.level", "level heading harus 1-6."))

        elif block.type == "paragraph":
            if not block.text.strip():
                issues.append(ValidationIssue(f"{prefix}.text", "paragraph butuh teks."))

        elif block.type == "list":
            if not block.items:
                issues.append(ValidationIssue(f"{prefix}.items", "list butuh minimal satu item."))

        elif block.type == "table":
            if not block.headers:
                issues.append(ValidationIssue(f"{prefix}.headers", "table butuh minimal satu header."))
            for row_index, row in enumerate(block.rows):
                if len(row) != len(block.headers):
                    issues.append(ValidationIssue(
                        f"{prefix}.rows[{row_index}]",
                        f"jumlah kolom ({len(row)}) tidak sama dengan jumlah header ({len(block.headers)}).",
                    ))

    return _result(issues)


# ------------------------------------------------------------ spreadsheet

def validate_spreadsheet_spec(spec: SpreadsheetSpec) -> ValidationResult:
    issues: list[ValidationIssue] = []

    if not isinstance(spec, SpreadsheetSpec):
        return ValidationResult(False, [ValidationIssue("spec", "harus berupa SpreadsheetSpec.")])

    if not spec.worksheets:
        issues.append(ValidationIssue("worksheets", "spreadsheet butuh minimal satu worksheet."))

    seen_names: set[str] = set()

    for index, sheet in enumerate(spec.worksheets):
        prefix = f"worksheets[{index}]"

        if not sheet.name or not sheet.name.strip():
            issues.append(ValidationIssue(f"{prefix}.name", "nama worksheet wajib diisi."))
        elif sheet.name in seen_names:
            issues.append(ValidationIssue(
                f"{prefix}.name", f"nama worksheet '{sheet.name}' dipakai lebih dari sekali.",
            ))
        else:
            seen_names.add(sheet.name)

        if not sheet.headers:
            issues.append(ValidationIssue(f"{prefix}.headers", "worksheet butuh minimal satu header."))

        for row_index, row in enumerate(sheet.rows):
            if len(row) != len(sheet.headers):
                issues.append(ValidationIssue(
                    f"{prefix}.rows[{row_index}]",
                    f"jumlah kolom ({len(row)}) tidak sama dengan jumlah header ({len(sheet.headers)}).",
                ))

        for column, fmt in sheet.column_formats.items():
            if fmt not in VALID_COLUMN_FORMATS:
                issues.append(ValidationIssue(
                    f"{prefix}.column_formats.{column}",
                    f"format '{fmt}' tidak dikenal. Pilihan: {sorted(VALID_COLUMN_FORMATS)}.",
                ))
            if column not in sheet.headers:
                issues.append(ValidationIssue(
                    f"{prefix}.column_formats.{column}",
                    f"kolom '{column}' tidak ada di headers worksheet ini.",
                ))

    return _result(issues)


def validate_csv_spec(spec: CsvSpec) -> ValidationResult:
    issues: list[ValidationIssue] = []

    if not isinstance(spec, CsvSpec):
        return ValidationResult(False, [ValidationIssue("spec", "harus berupa CsvSpec.")])

    if not spec.headers:
        issues.append(ValidationIssue("headers", "csv butuh minimal satu header."))

    for row_index, row in enumerate(spec.rows):
        if len(row) != len(spec.headers):
            issues.append(ValidationIssue(
                f"rows[{row_index}]",
                f"jumlah kolom ({len(row)}) tidak sama dengan jumlah header ({len(spec.headers)}).",
            ))

    return _result(issues)


# ------------------------------------------------------------ presentation

def validate_presentation_spec(spec: PresentationSpec) -> ValidationResult:
    issues: list[ValidationIssue] = []

    if not isinstance(spec, PresentationSpec):
        return ValidationResult(False, [ValidationIssue("spec", "harus berupa PresentationSpec.")])

    if not spec.title or not spec.title.strip():
        issues.append(ValidationIssue("title", "title wajib diisi."))

    if not spec.sections:
        issues.append(ValidationIssue("sections", "presentasi butuh minimal satu section."))

    for index, section in enumerate(spec.sections):
        prefix = f"sections[{index}]"

        if not section.heading or not section.heading.strip():
            issues.append(ValidationIssue(f"{prefix}.heading", "section butuh heading."))

        if section.table is not None:
            headers = section.table.get("headers") or []
            for row_index, row in enumerate(section.table.get("rows") or []):
                if len(row) != len(headers):
                    issues.append(ValidationIssue(
                        f"{prefix}.table.rows[{row_index}]",
                        f"jumlah kolom ({len(row)}) tidak sama dengan jumlah header ({len(headers)}).",
                    ))

    return _result(issues)


def validate_for_type(spec, artifact_type: str) -> ValidationResult:
    """Dispatch by artifact_type family - used by ArtifactEngine before it
    ever calls a generator."""
    try:
        artifact_type = ArtifactType.coerce(artifact_type).value
    except ValueError as exc:
        return ValidationResult(False, [ValidationIssue("artifact_type", str(exc))])

    if artifact_type == ArtifactType.CSV.value and isinstance(spec, CsvSpec):
        return validate_csv_spec(spec)
    if artifact_type in SPREADSHEET_TYPES:
        return validate_spreadsheet_spec(spec)
    if artifact_type in PRESENTATION_TYPES:
        return validate_presentation_spec(spec)
    if artifact_type in DOCUMENT_TYPES:
        return validate_document_spec(spec)

    return ValidationResult(False, [ValidationIssue(
        "artifact_type", f"'{artifact_type}' tidak dikenal oleh validator.",
    )])