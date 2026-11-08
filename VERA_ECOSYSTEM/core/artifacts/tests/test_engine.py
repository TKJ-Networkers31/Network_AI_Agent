import json
import tempfile
import unittest
from pathlib import Path

from core.artifacts.engine import ArtifactEngine
from core.artifacts.models import ArtifactStatus, ArtifactType
from core.artifacts.specs import (
    CsvSpec, DocumentSpec, PresentationSpec, SlideSection, SpreadsheetSpec, WorksheetSpec,
    heading, paragraph, bullet_list, table_block,
)
from core.artifacts.store import ArtifactStore


def _doc_spec() -> DocumentSpec:
    return DocumentSpec(title="Laporan", blocks=[
        heading("Ringkasan", 1), paragraph("Isi."), bullet_list(["a", "b"]),
        table_block(["X"], [["1"]]),
    ])


def _sheet_spec(n_sheets: int = 1) -> SpreadsheetSpec:
    sheets = [
        WorksheetSpec(name=f"Sheet{i}", headers=["A", "B"], rows=[["1", "2"]])
        for i in range(n_sheets)
    ]
    return SpreadsheetSpec(worksheets=sheets)


def _presentation_spec() -> PresentationSpec:
    return PresentationSpec(title="Deck", sections=[SlideSection(heading="Intro", content=["hi"])])


class ArtifactEngineTestBase(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace_root = Path(self.tmp.name) / "workspace"
        self.store = ArtifactStore(db_path=Path(self.tmp.name) / "artifacts_test.db")
        self.engine = ArtifactEngine(
            store=self.store,
            resolve_path=lambda rel: self.workspace_root / rel,
        )

    def tearDown(self):
        self.tmp.cleanup()


class TestEveryArtifactType(ArtifactEngineTestBase):

    def test_docx(self):
        self._assert_ready(self.engine.create_document(_doc_spec(), ArtifactType.DOCX), ".docx")

    def test_pdf(self):
        self._assert_ready(self.engine.create_document(_doc_spec(), ArtifactType.PDF), ".pdf")

    def test_markdown(self):
        self._assert_ready(self.engine.create_document(_doc_spec(), ArtifactType.MARKDOWN), ".md")

    def test_txt(self):
        self._assert_ready(self.engine.create_document(_doc_spec(), ArtifactType.TXT), ".txt")

    def test_xlsx(self):
        self._assert_ready(self.engine.create_spreadsheet(_sheet_spec(), ArtifactType.XLSX), ".xlsx")

    def test_csv_from_worksheet(self):
        self._assert_ready(self.engine.create_spreadsheet(_sheet_spec(), ArtifactType.CSV), ".csv")

    def test_csv_from_csv_spec_directly(self):
        spec = CsvSpec(headers=["A"], rows=[["1"]])
        self._assert_ready(self.engine.create_spreadsheet(spec, ArtifactType.CSV), ".csv")

    def test_pptx(self):
        self._assert_ready(self.engine.create_presentation(_presentation_spec(), ArtifactType.PPTX), ".pptx")

    def _assert_ready(self, result, suffix):
        self.assertTrue(result.success, result.errors)
        self.assertEqual(result.artifact.status, ArtifactStatus.READY.value)
        self.assertTrue(result.artifact.storage_reference.endswith(suffix))
        self.assertGreater(result.artifact.size, 0)

        absolute = self.workspace_root / result.artifact.storage_reference
        self.assertTrue(absolute.exists())
        self.assertEqual(absolute.stat().st_size, result.artifact.size)

        fetched = self.store.get(result.artifact.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.status, ArtifactStatus.READY.value)


class TestInvalidSpecs(ArtifactEngineTestBase):

    def test_empty_document_spec_rejected(self):
        result = self.engine.create_document(DocumentSpec(title="", blocks=[]), ArtifactType.DOCX)
        self.assertFalse(result.success)
        self.assertIsNone(result.artifact)
        self.assertTrue(result.errors)

    def test_table_column_mismatch_rejected(self):
        spec = DocumentSpec(title="T", blocks=[table_block(["A", "B"], [["1"]])])
        result = self.engine.create_document(spec, ArtifactType.DOCX)
        self.assertFalse(result.success)

    def test_empty_spreadsheet_rejected(self):
        result = self.engine.create_spreadsheet(SpreadsheetSpec(worksheets=[]), ArtifactType.XLSX)
        self.assertFalse(result.success)

    def test_unknown_artifact_type_rejected(self):
        result = self.engine.create_document(_doc_spec(), "not_a_type")
        self.assertFalse(result.success)
        self.assertIsNone(result.artifact)

    def test_no_worksheets_rejects_csv_conversion_before_drop(self):
        result = self.engine.create_spreadsheet(SpreadsheetSpec(worksheets=[]), ArtifactType.CSV)
        self.assertFalse(result.success)

    def test_invalid_presentation_rejected(self):
        result = self.engine.create_presentation(PresentationSpec(title="", sections=[]), ArtifactType.PPTX)
        self.assertFalse(result.success)


class TestMultiWorksheetToCsvDrops(ArtifactEngineTestBase):

    def test_extra_worksheets_recorded_in_metadata(self):
        result = self.engine.create_spreadsheet(_sheet_spec(n_sheets=3), ArtifactType.CSV)
        self.assertTrue(result.success, result.errors)
        self.assertEqual(result.artifact.metadata.get("dropped_worksheets"), ["Sheet1", "Sheet2"])


class TestStorageIntegration(ArtifactEngineTestBase):

    def test_uses_injected_resolver_and_subdir(self):
        result = self.engine.create_document(_doc_spec(), ArtifactType.TXT)
        self.assertTrue(result.success)
        self.assertTrue(result.artifact.storage_reference.startswith("Artifacts/"))

    def test_custom_subdir(self):
        engine = ArtifactEngine(
            store=self.store, resolve_path=lambda rel: self.workspace_root / rel,
            workspace_subdir="Documents/Generated",
        )
        result = engine.create_document(_doc_spec(), ArtifactType.TXT)
        self.assertTrue(result.artifact.storage_reference.startswith("Documents/Generated/"))

    def test_session_id_and_source_propagate(self):
        result = self.engine.create_document(
            _doc_spec(), ArtifactType.TXT, session_id="sess-1", source="ai_agent",
        )
        self.assertEqual(result.artifact.session_id, "sess-1")
        self.assertEqual(result.artifact.source, "ai_agent")


class TestFailureHandling(ArtifactEngineTestBase):

    def test_resolver_failure_is_reported_not_raised(self):
        def boom(_rel):
            raise RuntimeError("sandbox denied")

        engine = ArtifactEngine(store=self.store, resolve_path=boom)
        result = engine.create_document(_doc_spec(), ArtifactType.TXT)

        self.assertFalse(result.success)
        self.assertIsNotNone(result.artifact)
        self.assertEqual(result.artifact.status, ArtifactStatus.FAILED.value)
        self.assertTrue(result.errors)

        fetched = self.store.get(result.artifact.id)
        self.assertEqual(fetched.status, ArtifactStatus.FAILED.value)

    def test_generator_exception_is_caught(self):
        from core.artifacts import engine as engine_module

        original = engine_module._GENERATORS[ArtifactType.TXT.value]

        def bad_generator(spec, path):
            raise RuntimeError("disk full")

        engine_module._GENERATORS[ArtifactType.TXT.value] = bad_generator
        try:
            result = self.engine.create_document(_doc_spec(), ArtifactType.TXT)
            self.assertFalse(result.success)
            self.assertEqual(result.artifact.status, ArtifactStatus.FAILED.value)
        finally:
            engine_module._GENERATORS[ArtifactType.TXT.value] = original

    def test_artifact_serializable_after_failure(self):
        def boom(_rel):
            raise RuntimeError("nope")

        engine = ArtifactEngine(store=self.store, resolve_path=boom)
        result = engine.create_document(_doc_spec(), ArtifactType.TXT)
        data = result.to_dict()

        self.assertFalse(data["success"])
        self.assertEqual(data["artifact"]["status"], "failed")
        json.dumps(data)  # must not raise


class TestArtifactResultSerialization(ArtifactEngineTestBase):

    def test_success_result_is_json_safe(self):
        result = self.engine.create_document(_doc_spec(), ArtifactType.MARKDOWN)
        json.dumps(result.to_dict())

    def test_get_list_delete(self):
        result = self.engine.create_document(_doc_spec(), ArtifactType.TXT, session_id="s1")
        artifact_id = result.artifact.id

        self.assertIsNotNone(self.engine.get(artifact_id))
        self.assertEqual(len(self.engine.list(session_id="s1")), 1)
        self.assertTrue(self.engine.delete(artifact_id))
        self.assertIsNone(self.engine.get(artifact_id))


if __name__ == "__main__":
    unittest.main()