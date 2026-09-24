import unittest

from core.artifacts.specs import (
    CsvSpec, DocumentSpec, PresentationSpec, SpreadsheetSpec, WorksheetSpec,
    heading, paragraph, bullet_list, table_block,
)
from core.artifacts.validator import (
    validate_csv_spec, validate_document_spec, validate_for_type,
    validate_presentation_spec, validate_spreadsheet_spec,
)


class TestDocumentSpecParsing(unittest.TestCase):

    def test_from_dict_flat_shape(self):
        spec = DocumentSpec.from_dict({
            "title": "Laporan",
            "headings": [{"text": "Bab 1", "level": 1}],
            "paragraphs": [{"text": "Isi paragraf."}],
            "lists": [{"items": ["a", "b"]}],
            "tables": [{"headers": ["X", "Y"], "rows": [["1", "2"]]}],
        })
        self.assertEqual(spec.title, "Laporan")
        self.assertEqual(len(spec.headings), 1)
        self.assertEqual(len(spec.paragraphs), 1)
        self.assertEqual(len(spec.lists), 1)
        self.assertEqual(len(spec.tables), 1)

    def test_from_dict_blocks_shape_preserves_order(self):
        spec = DocumentSpec.from_dict({
            "title": "T",
            "blocks": [
                {"type": "heading", "text": "H1", "level": 1},
                {"type": "paragraph", "text": "P1"},
                {"type": "heading", "text": "H2", "level": 2},
            ],
        })
        self.assertEqual([b.type for b in spec.blocks], ["heading", "paragraph", "heading"])

    def test_tolerant_of_garbage(self):
        spec = DocumentSpec.from_dict("not a dict")
        self.assertEqual(spec.title, "Untitled Document")
        self.assertEqual(spec.blocks, [])

    def test_helper_constructors(self):
        spec = DocumentSpec(title="T", blocks=[
            heading("H", 2), paragraph("P"), bullet_list(["a", "b"], ordered=True),
            table_block(["A"], [["1"]]),
        ])
        result = validate_document_spec(spec)
        self.assertTrue(result.is_valid, result.messages())


class TestDocumentValidation(unittest.TestCase):

    def test_valid_spec_passes(self):
        spec = DocumentSpec(title="OK", blocks=[heading("H", 1), paragraph("P")])
        self.assertTrue(validate_document_spec(spec).is_valid)

    def test_missing_title_fails(self):
        spec = DocumentSpec(title="", blocks=[paragraph("P")])
        result = validate_document_spec(spec)
        self.assertFalse(result.is_valid)
        self.assertTrue(any(i.field == "title" for i in result.issues))

    def test_empty_blocks_fails(self):
        result = validate_document_spec(DocumentSpec(title="T", blocks=[]))
        self.assertFalse(result.is_valid)

    def test_invalid_heading_level_fails(self):
        spec = DocumentSpec(title="T", blocks=[heading("H", 9)])
        result = validate_document_spec(spec)
        self.assertFalse(result.is_valid)

    def test_table_row_width_mismatch_fails(self):
        spec = DocumentSpec(title="T", blocks=[table_block(["A", "B"], [["1"]])])
        result = validate_document_spec(spec)
        self.assertFalse(result.is_valid)

    def test_empty_list_items_fails(self):
        spec = DocumentSpec(title="T", blocks=[bullet_list([])])
        result = validate_document_spec(spec)
        self.assertFalse(result.is_valid)

    def test_unknown_block_type_fails(self):
        from core.artifacts.specs import DocumentBlock
        spec = DocumentSpec(title="T", blocks=[DocumentBlock(type="video", text="x")])
        self.assertFalse(validate_document_spec(spec).is_valid)

    def test_non_document_spec_rejected(self):
        result = validate_document_spec("not a spec")
        self.assertFalse(result.is_valid)


class TestSpreadsheetValidation(unittest.TestCase):

    def test_valid_multi_sheet_spec(self):
        spec = SpreadsheetSpec(worksheets=[
            WorksheetSpec(name="Data", headers=["A", "B"], rows=[["1", "2"]]),
        ])
        self.assertTrue(validate_spreadsheet_spec(spec).is_valid)

    def test_no_worksheets_fails(self):
        result = validate_spreadsheet_spec(SpreadsheetSpec(worksheets=[]))
        self.assertFalse(result.is_valid)

    def test_duplicate_worksheet_names_fails(self):
        spec = SpreadsheetSpec(worksheets=[
            WorksheetSpec(name="S", headers=["A"], rows=[]),
            WorksheetSpec(name="S", headers=["A"], rows=[]),
        ])
        result = validate_spreadsheet_spec(spec)
        self.assertFalse(result.is_valid)

    def test_row_width_mismatch_fails(self):
        spec = SpreadsheetSpec(worksheets=[WorksheetSpec(name="S", headers=["A", "B"], rows=[["1"]])])
        self.assertFalse(validate_spreadsheet_spec(spec).is_valid)

    def test_unknown_column_format_fails(self):
        spec = SpreadsheetSpec(worksheets=[
            WorksheetSpec(name="S", headers=["A"], rows=[["1"]], column_formats={"A": "bogus"}),
        ])
        self.assertFalse(validate_spreadsheet_spec(spec).is_valid)

    def test_column_format_for_unknown_header_fails(self):
        spec = SpreadsheetSpec(worksheets=[
            WorksheetSpec(name="S", headers=["A"], rows=[["1"]], column_formats={"Z": "number"}),
        ])
        self.assertFalse(validate_spreadsheet_spec(spec).is_valid)

    def test_shorthand_single_sheet_parsing(self):
        spec = SpreadsheetSpec.from_dict({"headers": ["A"], "rows": [["1"]]})
        self.assertEqual(len(spec.worksheets), 1)


class TestCsvValidation(unittest.TestCase):

    def test_valid_csv(self):
        spec = CsvSpec(headers=["A", "B"], rows=[["1", "2"]])
        self.assertTrue(validate_csv_spec(spec).is_valid)

    def test_missing_headers_fails(self):
        self.assertFalse(validate_csv_spec(CsvSpec(headers=[], rows=[["1"]])).is_valid)

    def test_row_width_mismatch_fails(self):
        self.assertFalse(validate_csv_spec(CsvSpec(headers=["A", "B"], rows=[["1"]])).is_valid)

    def test_from_worksheet(self):
        worksheet = WorksheetSpec(name="S", headers=["A"], rows=[["1"]])
        spec = CsvSpec.from_worksheet(worksheet)
        self.assertEqual(spec.headers, ["A"])
        self.assertEqual(spec.rows, [["1"]])


class TestPresentationValidation(unittest.TestCase):

    def test_valid_presentation(self):
        spec = PresentationSpec.from_dict({
            "title": "Deck",
            "sections": [{"heading": "Intro", "content": ["point 1"]}],
            "conclusion": "Terima kasih",
        })
        self.assertTrue(validate_presentation_spec(spec).is_valid)

    def test_missing_sections_fails(self):
        spec = PresentationSpec(title="Deck", sections=[])
        self.assertFalse(validate_presentation_spec(spec).is_valid)

    def test_missing_section_heading_fails(self):
        spec = PresentationSpec.from_dict({"title": "Deck", "sections": [{"heading": "", "content": ["x"]}]})
        self.assertFalse(validate_presentation_spec(spec).is_valid)

    def test_table_row_width_mismatch_fails(self):
        spec = PresentationSpec.from_dict({
            "title": "Deck",
            "sections": [{"heading": "H", "table": {"headers": ["A", "B"], "rows": [["1"]]}}],
        })
        self.assertFalse(validate_presentation_spec(spec).is_valid)


class TestValidateForType(unittest.TestCase):

    def test_dispatches_by_family(self):
        doc = DocumentSpec(title="T", blocks=[paragraph("P")])
        self.assertTrue(validate_for_type(doc, "docx").is_valid)
        self.assertTrue(validate_for_type(doc, "markdown").is_valid)

        sheet = SpreadsheetSpec(worksheets=[WorksheetSpec(name="S", headers=["A"], rows=[["1"]])])
        self.assertTrue(validate_for_type(sheet, "xlsx").is_valid)

    def test_unknown_type_fails(self):
        result = validate_for_type(DocumentSpec(title="T", blocks=[paragraph("p")]), "wat")
        self.assertFalse(result.is_valid)


if __name__ == "__main__":
    unittest.main()