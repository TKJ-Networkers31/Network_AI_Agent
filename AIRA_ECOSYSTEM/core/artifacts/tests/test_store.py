import tempfile
import unittest
from pathlib import Path

from core.artifacts.models import Artifact, ArtifactStatus
from core.artifacts.store import ArtifactStore


class TestArtifactStore(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ArtifactStore(db_path=Path(self.tmp.name) / "artifacts_test.db")

    def tearDown(self):
        self.tmp.cleanup()

    def test_save_and_get(self):
        artifact = Artifact(name="Report", artifact_type="docx", session_id="s1")
        self.store.save(artifact)

        fetched = self.store.get(artifact.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.name, "Report")
        self.assertEqual(fetched.session_id, "s1")
        self.assertEqual(fetched.artifact_type, "docx")

    def test_get_missing_returns_none(self):
        self.assertIsNone(self.store.get("does-not-exist"))

    def test_list_filters_by_session(self):
        self.store.save(Artifact(name="A", artifact_type="txt", session_id="s1"))
        self.store.save(Artifact(name="B", artifact_type="txt", session_id="s2"))

        results = self.store.list(session_id="s1")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "A")

    def test_list_filters_by_type(self):
        self.store.save(Artifact(name="A", artifact_type="pdf"))
        self.store.save(Artifact(name="B", artifact_type="csv"))

        results = self.store.list(artifact_type="csv")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "B")

    def test_metadata_round_trip(self):
        artifact = Artifact(name="A", artifact_type="xlsx", metadata={"rows": 5, "nested": {"x": 1}})
        self.store.save(artifact)
        fetched = self.store.get(artifact.id)
        self.assertEqual(fetched.metadata, {"rows": 5, "nested": {"x": 1}})

    def test_save_overwrites_existing_row(self):
        artifact = Artifact(name="A", artifact_type="txt", status=ArtifactStatus.PENDING.value)
        self.store.save(artifact)

        artifact.status = ArtifactStatus.READY.value
        artifact.size = 42
        self.store.save(artifact)

        fetched = self.store.get(artifact.id)
        self.assertEqual(fetched.status, "ready")
        self.assertEqual(fetched.size, 42)

    def test_delete(self):
        artifact = Artifact(name="A", artifact_type="txt")
        self.store.save(artifact)
        self.assertTrue(self.store.delete(artifact.id))
        self.assertFalse(self.store.delete(artifact.id))
        self.assertIsNone(self.store.get(artifact.id))


if __name__ == "__main__":
    unittest.main()