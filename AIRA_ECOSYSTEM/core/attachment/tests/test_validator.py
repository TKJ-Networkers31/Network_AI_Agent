import unittest

from core.attachments.validator import (
    validate_for_create,
    validate_mime_and_extension,
    validate_name,
    validate_session,
    validate_size,
)
from core.attachments.models import ValidationIssue


def _always_true(_session_id):
    return True


def _always_false(_session_id):
    return False


class TestValidateName(unittest.TestCase):

    def test_valid_name_passes(self):
        issues = []
        self.assertEqual(validate_name("report.pdf", issues), "report.pdf")
        self.assertEqual(issues, [])

    def test_empty_name_rejected(self):
        issues = []
        self.assertIsNone(validate_name("   ", issues))
        self.assertTrue(issues)

    def test_none_name_rejected(self):
        issues = []
        self.assertIsNone(validate_name(None, issues))
        self.assertTrue(issues)

    def test_path_separator_rejected(self):
        issues = []
        self.assertIsNone(validate_name("../../etc/passwd", issues))
        self.assertTrue(any("path" in i.message for i in issues))

    def test_backslash_rejected(self):
        issues = []
        self.assertIsNone(validate_name("folder\\file.txt", issues))
        self.assertTrue(issues)

    def test_dot_dot_rejected(self):
        issues = []
        self.assertIsNone(validate_name("..", issues))
        self.assertTrue(issues)

    def test_null_byte_rejected(self):
        issues = []
        self.assertIsNone(validate_name("bad\x00name.txt", issues))
        self.assertTrue(issues)

    def test_too_long_rejected(self):
        issues = []
        self.assertIsNone(validate_name("a" * 300 + ".txt", issues))
        self.assertTrue(issues)


class TestValidateMimeAndExtension(unittest.TestCase):

    def test_infers_mime_from_extension(self):
        issues = []
        self.assertEqual(validate_mime_and_extension("photo.png", None, issues), "image/png")
        self.assertEqual(issues, [])

    def test_matching_mime_and_extension_passes(self):
        issues = []
        result = validate_mime_and_extension("doc.pdf", "application/pdf", issues)
        self.assertEqual(result, "application/pdf")
        self.assertEqual(issues, [])

    def test_mismatched_mime_and_extension_rejected(self):
        issues = []
        result = validate_mime_and_extension("doc.pdf", "image/png", issues)
        self.assertIsNone(result)
        self.assertTrue(issues)

    def test_unsupported_extension_rejected(self):
        issues = []
        result = validate_mime_and_extension("archive.zip", None, issues)
        self.assertIsNone(result)
        self.assertTrue(issues)

    def test_unsupported_mime_rejected(self):
        issues = []
        result = validate_mime_and_extension("file.txt", "application/x-made-up", issues)
        self.assertIsNone(result)
        self.assertTrue(issues)

    def test_no_extension_rejected(self):
        issues = []
        result = validate_mime_and_extension("noextension", None, issues)
        self.assertIsNone(result)
        self.assertTrue(issues)

    def test_blocked_extension_rejected_even_with_plausible_mime(self):
        issues = []
        result = validate_mime_and_extension("virus.exe", "text/plain", issues)
        self.assertIsNone(result)
        self.assertTrue(any("executable" in i.message for i in issues))

    def test_case_insensitive_extension_and_mime(self):
        issues = []
        result = validate_mime_and_extension("Photo.PNG", "IMAGE/PNG", issues)
        self.assertEqual(result, "image/png")
        self.assertEqual(issues, [])


class TestValidateSize(unittest.TestCase):

    def test_valid_size_passes(self):
        issues = []
        self.assertEqual(validate_size(1024, issues), 1024)
        self.assertEqual(issues, [])

    def test_zero_size_rejected(self):
        issues = []
        self.assertIsNone(validate_size(0, issues))
        self.assertTrue(issues)

    def test_negative_size_rejected(self):
        issues = []
        self.assertIsNone(validate_size(-1, issues))
        self.assertTrue(issues)

    def test_oversized_rejected(self):
        issues = []
        self.assertIsNone(validate_size(999_999_999_999, issues))
        self.assertTrue(issues)

    def test_non_numeric_rejected(self):
        issues = []
        self.assertIsNone(validate_size("banyak", issues))
        self.assertTrue(issues)


class TestValidateSession(unittest.TestCase):

    def test_missing_session_id_rejected(self):
        issues = []
        self.assertIsNone(validate_session(None, issues, session_lookup=_always_true))
        self.assertTrue(issues)

    def test_empty_session_id_rejected(self):
        issues = []
        self.assertIsNone(validate_session("   ", issues, session_lookup=_always_true))
        self.assertTrue(issues)

    def test_nonexistent_session_rejected(self):
        issues = []
        self.assertIsNone(validate_session("sess-1", issues, session_lookup=_always_false))
        self.assertTrue(issues)

    def test_existing_session_accepted(self):
        issues = []
        self.assertEqual(validate_session("sess-1", issues, session_lookup=_always_true), "sess-1")
        self.assertEqual(issues, [])

    def test_lookup_exception_reported_not_raised(self):
        def boom(_session_id):
            raise RuntimeError("db down")

        issues = []
        self.assertIsNone(validate_session("sess-1", issues, session_lookup=boom))
        self.assertTrue(issues)


class TestValidateForCreate(unittest.TestCase):

    def test_all_valid_passes(self):
        result = validate_for_create(
            name="report.pdf", mime_type="application/pdf", size=2048,
            session_id="sess-1", source="user_upload", session_lookup=_always_true,
        )
        self.assertTrue(result.is_valid)

    def test_invalid_source_rejected(self):
        result = validate_for_create(
            name="report.pdf", mime_type="application/pdf", size=2048,
            session_id="sess-1", source="not_a_source", session_lookup=_always_true,
        )
        self.assertFalse(result.is_valid)

    def test_multiple_failures_all_reported(self):
        result = validate_for_create(
            name="", mime_type="bad/type", size=-1,
            session_id=None, source="user_upload", session_lookup=_always_true,
        )
        self.assertFalse(result.is_valid)
        fields = {i.field for i in result.issues}
        self.assertIn("name", fields)
        self.assertIn("size", fields)
        self.assertIn("session_id", fields)

    def test_extension_check_skipped_when_name_already_invalid(self):
        # A rejected name shouldn't ALSO produce a confusing extension error.
        result = validate_for_create(
            name="", mime_type=None, size=10,
            session_id="sess-1", source="user_upload", session_lookup=_always_true,
        )
        fields = [i.field for i in result.issues]
        self.assertEqual(fields.count("name"), 1)


if __name__ == "__main__":
    unittest.main()
