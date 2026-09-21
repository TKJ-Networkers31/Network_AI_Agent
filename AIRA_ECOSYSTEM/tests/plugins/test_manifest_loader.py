"""
tests/plugins/test_manifest_loader.py — unit test Phase 1.2 Plugin Foundation:
Manifest Loader (core/plugins/loader.py) dan Manifest Validator
(core/plugins/validator.py).

Cakupan:
  Loader    : manifest valid -> PluginManifest, file tidak ada, path bukan file,
              file kosong, YAML malformed (dengan baris/kolom), root bukan mapping,
              non-UTF-8, BOM, batas ukuran, tag YAML berbahaya, tidak pernah raise,
              loader TIDAK memvalidasi.
  Validator : field wajib, plugin ID, version, description, author, api_version,
              compatibility, capabilities, permissions, dependencies (id +
              version constraint), tipe data, mode strict, jalur objek
              PluginManifest, valid vs invalid pada PluginValidationResult.
  Alignment : PluginManifest sebagai representasi kanonik (api_version,
              capabilities, permissions dibawa model), jalur objek memakai
              skema yang sama dengan jalur raw, tidak ada field valid yang
              hilang dari raw -> objek, jalur raw tetap mendeteksi input cacat.
  Batas     : tanggung jawab loader/validator terpisah; tidak mengimpor
              agents/api/tools/Event Bus/dst.

Semua test memakai folder SEMENTARA dan tanpa jaringan.

Jalankan dari root AIRA_ECOSYSTEM/:
    python -m unittest tests.plugins.test_manifest_loader -v
"""

import ast
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

from core.plugins import loader as loader_module
from core.plugins import validator as validator_module
from core.plugins.loader import (
    ManifestErrorCode,
    ManifestLoadResult,
    load_manifest,
    load_manifest_raw,
    load_manifest_text,
)
from core.plugins.manifest import manifest_from_dict
from core.plugins.models import (
    PluginAuthor,
    PluginDependency,
    PluginManifest,
    PluginValidationIssue,
    PluginValidationResult,
)
from core.plugins.validator import (
    REQUIRED_FIELDS,
    ManifestValidator,
    validate_manifest_data,
    validate_plugin_manifest,
    validate_version_constraint,
)

PLUGINS_DIR = Path(loader_module.__file__).resolve().parent

VALID = {
    "id": "akane-net-tools",
    "name": "AKANE Net Tools",
    "version": "1.2.0",
    "description": "Alat bantu jaringan untuk AKANE.",
    "author": {"name": "Lingga", "email": "lingga@example.com", "url": "https://example.com"},
    "entry_point": "plugins.net_tools.main:NetToolsPlugin",
    "category": "network",
    "tags": ["network", "ssh"],
    "api_version": "1",
    "compatibility": {
        "min_aira_version": "1.0.0",
        "max_aira_version": "2.0.0",
        "platforms": ["windows", "linux"],
    },
    "capabilities": ["network.ssh", "network.snmp"],
    "permissions": ["network:read", "device.config.read"],
    "dependencies": [
        "base-utils",
        {"id": "mikrotik-core", "version_constraint": ">=1.0.0,<2.0.0", "optional": True},
    ],
}


def valid(**overrides):
    """Salinan VALID dengan override. Nilai _DROP menghapus key."""
    data = copy.deepcopy(VALID)
    for key, value in overrides.items():
        if value is _DROP:
            data.pop(key, None)
        else:
            data[key] = value
    return data


_DROP = object()


def fields(result: PluginValidationResult) -> list[str]:
    return [issue.field for issue in result.issues]


class TempCase(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def write(self, name: str, content, *, binary: bool = False) -> Path:
        path = self.tmp / name
        # Selalu tulis BYTE persis, jangan write_text(): mode teks menerjemahkan
        # "\n" -> "\r\n" di Windows, sehingga ukuran file di disk berbeda dari
        # len(content.encode()) dan test yang mengukur byte (batas ukuran) gagal.
        path.write_bytes(content if binary else content.encode("utf-8"))
        return path

    def write_yaml(self, data, name: str = "plugin.yaml") -> Path:
        return self.write(name, yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


# ============================================================ LOADER

class TestLoaderSuccess(TempCase):

    def test_valid_manifest_yaml_produces_plugin_manifest(self):
        path = self.write_yaml(VALID)

        result = load_manifest(path)

        self.assertTrue(result.loaded)
        self.assertEqual(result.errors, [])
        self.assertIsInstance(result.manifest, PluginManifest)
        self.assertEqual(result.manifest.id, "akane-net-tools")
        self.assertEqual(result.manifest.version, "1.2.0")
        self.assertEqual(result.manifest.author.name, "Lingga")
        self.assertEqual(result.manifest.entry_point, "plugins.net_tools.main:NetToolsPlugin")
        self.assertEqual(result.manifest.compatibility.platforms, ["windows", "linux"])
        self.assertEqual(
            [(d.id, d.version_constraint, d.optional) for d in result.manifest.dependencies],
            [("base-utils", None, False), ("mikrotik-core", ">=1.0.0,<2.0.0", True)],
        )
        self.assertEqual(result.source, str(path))

    def test_accepts_str_and_pathlike(self):
        path = self.write_yaml(VALID)

        self.assertTrue(load_manifest(str(path)).loaded)
        self.assertTrue(load_manifest(path).loaded)

    def test_raw_keeps_fields_the_manifest_object_cannot_carry(self):
        result = load_manifest(self.write_yaml(VALID))

        self.assertEqual(result.raw["api_version"], "1")
        self.assertEqual(result.raw["capabilities"], ["network.ssh", "network.snmp"])
        self.assertEqual(result.raw["permissions"], ["network:read", "device.config.read"])

    def test_load_manifest_raw_returns_mapping_without_building_manifest(self):
        result = load_manifest_raw(self.write_yaml(VALID))

        self.assertTrue(result.loaded)
        self.assertIsNone(result.manifest)
        self.assertEqual(result.raw["id"], "akane-net-tools")

    def test_unicode_content_survives(self):
        path = self.write_yaml(valid(description="Alat jaringan — café ✓"))

        self.assertEqual(load_manifest(path).manifest.description, "Alat jaringan — café ✓")

    def test_utf8_bom_is_ignored(self):
        content = b"\xef\xbb\xbf" + yaml.safe_dump(VALID).encode("utf-8")

        result = load_manifest(self.write("bom.yaml", content, binary=True))

        self.assertTrue(result.loaded)
        self.assertEqual(result.manifest.id, "akane-net-tools")

    def test_result_to_dict_is_json_serializable(self):
        result = load_manifest(self.write_yaml(VALID))

        payload = result.to_dict()

        self.assertEqual(json.loads(json.dumps(payload)), payload)
        self.assertTrue(payload["loaded"])
        self.assertEqual(payload["manifest"]["id"], "akane-net-tools")
        self.assertNotIn("raw", payload)

    def test_load_manifest_text(self):
        result = load_manifest_text(yaml.safe_dump(VALID), source="memori")

        self.assertTrue(result.loaded)
        self.assertEqual(result.source, "memori")
        self.assertEqual(result.manifest.name, "AKANE Net Tools")


class TestLoaderStructuredErrors(TempCase):

    def assert_error(self, result: ManifestLoadResult, code: str):
        self.assertFalse(result.loaded)
        self.assertIsNone(result.raw)
        self.assertIsNone(result.manifest)
        self.assertEqual(len(result.errors), 1)
        self.assertEqual(result.errors[0].code, code)
        self.assertTrue(result.errors[0].message)
        json.dumps(result.to_dict())          # selalu JSON-safe

    def test_missing_manifest_file(self):
        path = self.tmp / "tidak-ada.yaml"

        result = load_manifest(path)

        self.assert_error(result, ManifestErrorCode.FILE_NOT_FOUND)
        self.assertEqual(result.errors[0].source, str(path))
        self.assertIn("tidak ditemukan", result.errors[0].message)

    def test_path_is_a_directory(self):
        self.assert_error(load_manifest(self.tmp), ManifestErrorCode.NOT_A_FILE)

    def test_malformed_yaml_reports_line_and_column(self):
        path = self.write("rusak.yaml", "id: ok\nname: [belum ditutup\nversion: 1.0.0\n")

        result = load_manifest(path)

        self.assert_error(result, ManifestErrorCode.YAML_SYNTAX_ERROR)
        self.assertIsNotNone(result.errors[0].line)
        self.assertIsNotNone(result.errors[0].column)
        self.assertIn("baris", result.errors[0].message)

    def test_malformed_yaml_bad_indentation(self):
        result = load_manifest(self.write("rusak2.yaml", "id: a\n  name: b\n version: c\n"))

        self.assert_error(result, ManifestErrorCode.YAML_SYNTAX_ERROR)

    def test_multiple_documents_are_rejected(self):
        result = load_manifest(self.write("multi.yaml", "id: a\n---\nid: b\n"))

        self.assert_error(result, ManifestErrorCode.YAML_SYNTAX_ERROR)

    def test_root_that_is_not_a_mapping(self):
        cases = {
            "list.yaml": "- a\n- b\n",
            "scalar.yaml": "hanya teks biasa\n",
            "number.yaml": "42\n",
            "bool.yaml": "true\n",
        }

        for name, content in cases.items():
            with self.subTest(name):
                result = load_manifest(self.write(name, content))

                self.assert_error(result, ManifestErrorCode.ROOT_NOT_MAPPING)
                self.assertIn("mapping", result.errors[0].message)

    def test_root_type_is_named_in_the_message(self):
        result = load_manifest(self.write("list.yaml", "- a\n"))

        self.assertIn("list", result.errors[0].message)

    def test_empty_and_comment_only_files(self):
        for name, content in (("empty.yaml", ""), ("blank.yaml", "  \n\n"), ("comment.yaml", "# cuma komentar\n")):
            with self.subTest(name):
                self.assert_error(load_manifest(self.write(name, content)), ManifestErrorCode.EMPTY_MANIFEST)

    def test_non_utf8_file(self):
        result = load_manifest(self.write("latin1.yaml", b"name: caf\xe9\xff\xfe\n", binary=True))

        self.assert_error(result, ManifestErrorCode.ENCODING_ERROR)

    def test_file_over_size_limit(self):
        path = self.write_yaml(VALID)

        with mock.patch.object(loader_module, "MAX_MANIFEST_BYTES", 20):
            result = load_manifest(path)

        self.assert_error(result, ManifestErrorCode.FILE_TOO_LARGE)

    def test_file_exactly_at_limit_is_accepted(self):
        text = "id: aa\n"
        path = self.write("pas.yaml", text)

        with mock.patch.object(loader_module, "MAX_MANIFEST_BYTES", len(text.encode())):
            self.assertTrue(load_manifest(path).loaded)

    def test_invalid_path_arguments(self):
        for bad in (None, 123, "", "   ", b"bytes.yaml", ["plugin.yaml"], object()):
            with self.subTest(repr(bad)):
                result = load_manifest(bad)

                self.assertFalse(result.loaded)
                self.assertEqual(result.errors[0].code, ManifestErrorCode.INVALID_PATH)

    def test_unreadable_file_is_a_read_error_not_an_exception(self):
        path = self.write_yaml(VALID)

        with mock.patch("builtins.open", side_effect=PermissionError("denied")):
            result = load_manifest(path)

        self.assert_error(result, ManifestErrorCode.READ_ERROR)

    def test_null_byte_in_path_is_contained(self):
        result = load_manifest("plugin\x00.yaml")

        self.assertFalse(result.loaded)
        self.assertIn(
            result.errors[0].code,
            {ManifestErrorCode.FILE_NOT_FOUND, ManifestErrorCode.READ_ERROR},
        )

    def test_unsafe_yaml_tags_are_not_executed(self):
        path = self.write("evil.yaml", 'id: !!python/object/apply:os.system ["echo pwned"]\n')

        with mock.patch("os.system") as system:
            result = load_manifest(path)

        system.assert_not_called()
        self.assert_error(result, ManifestErrorCode.YAML_SYNTAX_ERROR)

    def test_absurdly_deep_nesting_does_not_crash(self):
        result = load_manifest_text("[" * 20000 + "]" * 20000)

        self.assertFalse(result.loaded)

    def test_load_manifest_text_rejects_non_string(self):
        for bad in (None, 5, b"id: a", ["x"]):
            self.assertFalse(load_manifest_text(bad).loaded)

    def test_unexpected_internal_failure_becomes_structured_error(self):
        path = self.write_yaml(VALID)

        with mock.patch.object(loader_module, "manifest_from_dict", side_effect=RuntimeError("boom")), \
                self.assertLogs("aira.plugins.loader", level="ERROR"):
            result = load_manifest(path)

        self.assertFalse(result.loaded)
        self.assertEqual(result.errors[0].code, ManifestErrorCode.UNEXPECTED_ERROR)
        self.assertNotIn("boom", result.errors[0].message)      # detail internal tidak bocor


class TestLoaderDoesNotValidate(TempCase):

    def test_semantically_invalid_manifest_still_loads(self):
        path = self.write_yaml({"id": "BUKAN ID VALID!", "version": "abc", "name": ""})

        result = load_manifest(path)

        self.assertTrue(result.loaded)                 # dimuat...
        self.assertEqual(result.errors, [])
        self.assertFalse(validate_manifest_data(result.raw).is_valid)   # ...tapi validator menolak

    def test_wrong_typed_yaml_values_are_tolerated_by_the_parser(self):
        result = load_manifest(self.write("tipe.yaml", "id: aa-bb\nname: X\nversion: 1.0\ntags: satu\n"))

        self.assertTrue(result.loaded)
        self.assertEqual(result.raw["version"], 1.0)         # float asli terjaga di raw
        self.assertEqual(result.manifest.version, "")        # parser Phase 1.1 membuangnya

    def test_never_raises_on_garbage(self):
        garbage = [
            "\x00\x01\x02", "{{{{", "a: b: c", ":::", "\t\t", "!!binary |\n  ???",
            "&a [*a]", "? \n", "- - - -", "key: |\n" + " " * 5000,
        ]

        for index, text in enumerate(garbage):
            with self.subTest(text[:20]):
                result = load_manifest(self.write(f"g{index}.yaml", text))

                self.assertIsInstance(result, ManifestLoadResult)
                json.dumps(result.to_dict())


# ============================================================ VALIDATOR

class TestValidatorValid(unittest.TestCase):

    def test_fully_populated_manifest_is_valid(self):
        result = validate_manifest_data(VALID)

        self.assertTrue(result.is_valid, [i.to_dict() for i in result.issues])
        self.assertEqual(result.issues, [])

    def test_minimal_manifest_is_valid(self):
        minimal = {
            "id": "ab", "name": "N", "version": "0.0.1",
            "author": {"name": "A"}, "api_version": "1",
        }

        self.assertTrue(validate_manifest_data(minimal).is_valid)

    def test_null_optional_fields_count_as_absent(self):
        data = valid(description=None, entry_point=None, category=None, tags=None,
                     compatibility=None, capabilities=None, permissions=None, dependencies=None)

        self.assertTrue(validate_manifest_data(data).is_valid)

    def test_empty_description_and_empty_lists_are_valid(self):
        data = valid(description="", tags=[], capabilities=[], permissions=[], dependencies=[])

        self.assertTrue(validate_manifest_data(data).is_valid)

    def test_validation_does_not_mutate_input(self):
        data = valid()
        before = copy.deepcopy(data)

        validate_manifest_data(data)

        self.assertEqual(data, before)


class TestValidatorRequiredFields(unittest.TestCase):

    def test_each_required_field_missing_is_reported(self):
        for key in REQUIRED_FIELDS:
            with self.subTest(key):
                result = validate_manifest_data(valid(**{key: _DROP}))

                self.assertFalse(result.is_valid)
                self.assertEqual(fields(result), [key])
                self.assertIn("wajib", result.issues[0].message)

    def test_required_field_null_or_blank_is_reported(self):
        for key in ("id", "name", "version", "api_version"):
            for bad in (None, "", "   "):
                with self.subTest(key=key, value=bad):
                    result = validate_manifest_data(valid(**{key: bad}))

                    self.assertEqual(fields(result), [key])

    def test_author_name_is_required(self):
        result = validate_manifest_data(valid(author={"email": "a@b.co"}))

        self.assertEqual(fields(result), ["author.name"])

    def test_empty_mapping_reports_every_required_field(self):
        result = validate_manifest_data({})

        self.assertEqual(fields(result), list(REQUIRED_FIELDS))

    def test_all_issues_are_collected_not_just_the_first(self):
        result = validate_manifest_data({"id": "BAD ID", "version": "x", "name": 5})

        self.assertGreaterEqual(len(result.issues), 4)
        self.assertLessEqual({"id", "version", "name", "author", "api_version"}, set(fields(result)))


class TestValidatorIdentity(unittest.TestCase):

    def test_invalid_plugin_ids(self):
        for bad in ("A", "UPPER", "has space", "-leading", "_leading", "a", "x" * 65, "dot.ted", "ünï", "slash/x"):
            with self.subTest(bad):
                result = validate_manifest_data(valid(id=bad))

                self.assertFalse(result.is_valid)
                self.assertEqual(fields(result), ["id"])

    def test_valid_plugin_ids(self):
        for good in ("ab", "a1", "akane-net_tools", "0day", "x" * 64):
            with self.subTest(good):
                self.assertTrue(validate_manifest_data(valid(id=good)).is_valid)

    def test_invalid_versions(self):
        for bad in ("1", "1.0", "v1.0.0", "1.0.0.0", "abc", "1.0.0-", "01.0"):
            with self.subTest(bad):
                result = validate_manifest_data(valid(version=bad))

                self.assertEqual(fields(result), ["version"])

    def test_valid_versions(self):
        for good in ("0.0.1", "1.2.3", "1.2.0-beta.1", "1.0.0+build.5", "1.0.0-rc.1+sha.abc"):
            with self.subTest(good):
                self.assertTrue(validate_manifest_data(valid(version=good)).is_valid)

    def test_unquoted_yaml_version_gets_a_helpful_message(self):
        result = validate_manifest_data(valid(version=1.0))

        self.assertEqual(fields(result), ["version"])
        self.assertIn("string", result.issues[0].message)
        self.assertIn("tanda kutip", result.issues[0].message)

    def test_description_must_be_a_string(self):
        for bad in (123, ["x"], {"a": 1}, True):
            with self.subTest(repr(bad)):
                self.assertEqual(fields(validate_manifest_data(valid(description=bad))), ["description"])

    def test_name_type_and_blank(self):
        self.assertEqual(fields(validate_manifest_data(valid(name=123))), ["name"])
        self.assertEqual(fields(validate_manifest_data(valid(name="   "))), ["name"])

    def test_entry_point_format(self):
        for bad in ("nocolon", "a.b:", ":Cls", "a b:C", "a.b:C:D", "1a:C", "a..b:C"):
            with self.subTest(bad):
                self.assertEqual(fields(validate_manifest_data(valid(entry_point=bad))), ["entry_point"])

        self.assertTrue(validate_manifest_data(valid(entry_point="pkg:Plugin")).is_valid)

    def test_category_and_tags(self):
        self.assertEqual(fields(validate_manifest_data(valid(category=""))), ["category"])
        self.assertEqual(fields(validate_manifest_data(valid(category=5))), ["category"])
        self.assertEqual(fields(validate_manifest_data(valid(tags="satu"))), ["tags"])
        self.assertEqual(fields(validate_manifest_data(valid(tags=["ok", 3, ""]))), ["tags[1]", "tags[2]"])


class TestValidatorAuthor(unittest.TestCase):

    def test_author_must_be_a_mapping(self):
        for bad in ("Lingga", ["Lingga"], 5):
            with self.subTest(repr(bad)):
                result = validate_manifest_data(valid(author=bad))

                self.assertEqual(fields(result), ["author"])
                self.assertIn("mapping", result.issues[0].message)

    def test_author_email_and_url(self):
        result = validate_manifest_data(valid(author={"name": "A", "email": "bukan-email", "url": "ftp://x"}))

        self.assertEqual(fields(result), ["author.email", "author.url"])

        self.assertTrue(validate_manifest_data(valid(author={"name": "A"})).is_valid)

    def test_author_field_types(self):
        result = validate_manifest_data(valid(author={"name": 5, "email": 7, "url": 9}))

        self.assertEqual(fields(result), ["author.name", "author.email", "author.url"])


class TestValidatorApiVersion(unittest.TestCase):

    def test_valid_and_invalid_api_versions(self):
        for good in ("1", "1.0", "1.0.0", "12.34"):
            with self.subTest(good):
                self.assertTrue(validate_manifest_data(valid(api_version=good)).is_valid)

        for bad in ("v1", "1.", "1.0.0.0", "one", "1.x", "-1"):
            with self.subTest(bad):
                self.assertEqual(fields(validate_manifest_data(valid(api_version=bad))), ["api_version"])

    def test_unquoted_numeric_api_version_is_a_type_error_with_hint(self):
        for bad in (1, 1.0):
            with self.subTest(repr(bad)):
                result = validate_manifest_data(valid(api_version=bad))

                self.assertEqual(fields(result), ["api_version"])
                self.assertIn("tanda kutip", result.issues[0].message)


class TestValidatorCompatibility(unittest.TestCase):

    def test_must_be_a_mapping(self):
        self.assertEqual(fields(validate_manifest_data(valid(compatibility="windows"))), ["compatibility"])
        self.assertEqual(fields(validate_manifest_data(valid(compatibility=["linux"]))), ["compatibility"])

    def test_aira_version_bounds(self):
        result = validate_manifest_data(valid(compatibility={"min_aira_version": "1.0", "max_aira_version": 2}))

        self.assertEqual(fields(result), ["compatibility.min_aira_version", "compatibility.max_aira_version"])

    def test_min_greater_than_max_is_rejected(self):
        result = validate_manifest_data(valid(compatibility={"min_aira_version": "2.0.0", "max_aira_version": "1.9.9"}))

        self.assertEqual(fields(result), ["compatibility.min_aira_version"])
        self.assertIn("lebih besar", result.issues[0].message)

    def test_min_equal_max_and_prerelease_are_fine(self):
        data = valid(compatibility={"min_aira_version": "1.0.0-beta.1", "max_aira_version": "1.0.0"})

        self.assertTrue(validate_manifest_data(data).is_valid)

    def test_platforms(self):
        self.assertTrue(validate_manifest_data(valid(compatibility={"platforms": []})).is_valid)

        result = validate_manifest_data(valid(compatibility={"platforms": ["windows", "beos", 3, "windows"]}))
        self.assertEqual(
            fields(result),
            ["compatibility.platforms[1]", "compatibility.platforms[2]", "compatibility.platforms[3]"],
        )

        self.assertEqual(
            fields(validate_manifest_data(valid(compatibility={"platforms": "linux"}))),
            ["compatibility.platforms"],
        )


class TestValidatorCapabilitiesAndPermissions(unittest.TestCase):

    def test_must_be_lists(self):
        for key in ("capabilities", "permissions"):
            for bad in ("network.ssh", {"a": 1}, 5):
                with self.subTest(key=key, value=repr(bad)):
                    self.assertEqual(fields(validate_manifest_data(valid(**{key: bad}))), [key])

    def test_item_format(self):
        for key in ("capabilities", "permissions"):
            with self.subTest(key):
                result = validate_manifest_data(valid(**{key: ["ok.item", "Bad Item", 5, "", ".lead", "trail."]}))

                self.assertEqual(fields(result), [f"{key}[{i}]" for i in (1, 2, 3, 4, 5)])

    def test_valid_declaration_styles(self):
        data = valid(capabilities=["ssh", "network.ssh", "a_b-c.d0"], permissions=["net:read", "fs.write"])

        self.assertTrue(validate_manifest_data(data).is_valid)

    def test_duplicates_are_rejected(self):
        result = validate_manifest_data(valid(capabilities=["a.b", "c.d", "a.b"], permissions=["x", "x"]))

        self.assertEqual(fields(result), ["capabilities[2]", "permissions[1]"])


class TestValidatorDependencies(unittest.TestCase):

    def test_dependencies_must_be_a_list(self):
        for bad in ("base-utils", {"id": "base-utils"}, 3):
            with self.subTest(repr(bad)):
                self.assertEqual(fields(validate_manifest_data(valid(dependencies=bad))), ["dependencies"])

    def test_invalid_dependency_ids(self):
        for bad in ("BAD ID", "", "x", 5):
            with self.subTest(repr(bad)):
                result = validate_manifest_data(valid(dependencies=[{"id": bad}]))

                self.assertEqual(fields(result), ["dependencies[0].id"])

    def test_dependency_string_item_with_bad_id(self):
        self.assertEqual(fields(validate_manifest_data(valid(dependencies=["BAD ID"]))), ["dependencies[0]"])

    def test_dependency_missing_id(self):
        result = validate_manifest_data(valid(dependencies=[{"version_constraint": ">=1.0.0"}]))

        self.assertEqual(fields(result), ["dependencies[0].id"])
        self.assertIn("wajib", result.issues[0].message)

    def test_dependency_item_of_wrong_type(self):
        for bad in (5, None, ["a"], True):
            with self.subTest(repr(bad)):
                result = validate_manifest_data(valid(dependencies=[bad]))

                self.assertEqual(fields(result), ["dependencies[0]"])

    def test_valid_version_constraints(self):
        for good in ("*", "1.0.0", ">=1.0.0", ">1", "<=2.0", "==1.2.3", "!=1.0.0", "^1.2", "~1.2.3", "~=1.4.0",
                     ">=1.0.0,<2.0.0", ">= 1.0.0 , < 2.0.0", "1.0.0-beta.1", ">=1.0.0-rc.1+build.5"):
            with self.subTest(good):
                self.assertIsNone(validate_version_constraint(good))
                self.assertTrue(
                    validate_manifest_data(valid(dependencies=[{"id": "abc", "version_constraint": good}])).is_valid
                )

    def test_invalid_version_constraints(self):
        for bad in ("", "   ", "latest", ">=", ">=abc", "1.0.0,", ",1.0.0", ">=1.0.0 <2.0.0", "=>1.0.0", "1.x", ">>1.0"):
            with self.subTest(repr(bad)):
                self.assertIsNotNone(validate_version_constraint(bad))
                result = validate_manifest_data(valid(dependencies=[{"id": "abc", "version_constraint": bad}]))

                self.assertEqual(fields(result), ["dependencies[0].version_constraint"])

    def test_version_constraint_wrong_type(self):
        for bad in (1.0, 2, ["1.0.0"], True):
            with self.subTest(repr(bad)):
                result = validate_manifest_data(valid(dependencies=[{"id": "abc", "version_constraint": bad}]))

                self.assertEqual(fields(result), ["dependencies[0].version_constraint"])

        self.assertIsNotNone(validate_version_constraint(None))

    def test_optional_must_be_boolean(self):
        for bad in ("true", 1, "yes", []):
            with self.subTest(repr(bad)):
                result = validate_manifest_data(valid(dependencies=[{"id": "abc", "optional": bad}]))

                self.assertEqual(fields(result), ["dependencies[0].optional"])

    def test_duplicate_and_self_dependency(self):
        result = validate_manifest_data(valid(dependencies=["abc", {"id": "abc"}, "akane-net-tools"]))

        self.assertEqual(fields(result), ["dependencies[1].id", "dependencies[2]"])

    def test_multiple_bad_dependencies_all_reported(self):
        result = validate_manifest_data(valid(dependencies=[{"id": "BAD"}, 5, {"id": "ok-dep", "optional": "x"}]))

        self.assertEqual(fields(result), ["dependencies[0].id", "dependencies[1]", "dependencies[2].optional"])


class TestValidatorFieldTypes(unittest.TestCase):

    def test_invalid_field_types(self):
        cases = {
            "id": 123,
            "name": ["x"],
            "version": True,
            "description": {"a": 1},
            "author": "Lingga",
            "entry_point": 5,
            "category": [],
            "tags": "a,b",
            "api_version": 1,
            "compatibility": "windows",
            "capabilities": "network.ssh",
            "permissions": {"a": 1},
            "dependencies": "base",
        }

        for key, bad in cases.items():
            with self.subTest(key):
                result = validate_manifest_data(valid(**{key: bad}))

                self.assertFalse(result.is_valid)
                self.assertEqual(fields(result)[0].split(".")[0].split("[")[0], key)

    def test_type_errors_name_the_actual_type(self):
        result = validate_manifest_data(valid(name=123))

        self.assertIn("string", result.issues[0].message)
        self.assertIn("integer", result.issues[0].message)

    def test_root_must_be_a_mapping(self):
        for bad in (None, [], "text", 5, [VALID]):
            with self.subTest(repr(bad)):
                result = validate_manifest_data(bad)

                self.assertFalse(result.is_valid)
                self.assertEqual(fields(result), ["manifest"])

    def test_non_string_keys_are_reported(self):
        data = valid()
        data[True] = "yes-key"

        result = validate_manifest_data(data)

        self.assertFalse(result.is_valid)
        self.assertEqual(fields(result), ["manifest"])
        self.assertIn("boolean", result.issues[0].message)

    def test_never_raises_on_garbage(self):
        garbage = [
            None, 0, "", [], {}, {"id": object()}, {"author": {"name": object()}},
            {"dependencies": [object(), {"id": object()}]}, {"compatibility": {"platforms": [object()]}},
            {"capabilities": [None, [], {}]}, {1: 2, None: 3}, {"tags": [[]]},
        ]

        for item in garbage:
            with self.subTest(repr(item)[:40]):
                result = validate_manifest_data(item)

                self.assertIsInstance(result, PluginValidationResult)
                json.dumps(result.to_dict())

    def test_internal_failure_is_contained(self):
        with mock.patch.object(validator_module, "_check_tags", side_effect=RuntimeError("boom")), \
                self.assertLogs("aira.plugins.validator", level="ERROR"):
            result = validate_manifest_data(VALID)

        self.assertFalse(result.is_valid)
        self.assertEqual(fields(result), ["manifest"])
        self.assertNotIn("boom", result.issues[0].message)


class TestValidatorStrictMode(unittest.TestCase):

    def test_unknown_fields_are_ignored_by_default(self):
        self.assertTrue(validate_manifest_data(valid(extra_field="x")).is_valid)

    def test_strict_rejects_unknown_top_level_nested_fields(self):
        data = valid(
            extra_field="x",
            author={"name": "A", "nickname": "n"},
            compatibility={"platforms": [], "arch": "x64"},
            dependencies=[{"id": "abc", "pinned": True}],
        )

        result = validate_manifest_data(data, strict=True)

        self.assertEqual(
            set(fields(result)),
            {"extra_field", "author.nickname", "compatibility.arch", "dependencies[0].pinned"},
        )

    def test_strict_accepts_the_full_valid_manifest(self):
        self.assertTrue(validate_manifest_data(VALID, strict=True).is_valid)

    def test_typo_is_caught_only_in_strict_mode(self):
        typo = valid(capabilties=["x"])

        self.assertTrue(validate_manifest_data(typo).is_valid)
        self.assertEqual(fields(validate_manifest_data(typo, strict=True)), ["capabilties"])


class TestValidatorResultShape(unittest.TestCase):

    def test_valid_and_invalid_are_distinguishable(self):
        good = validate_manifest_data(VALID)
        bad = validate_manifest_data(valid(id="BAD ID"))

        self.assertIsInstance(good, PluginValidationResult)
        self.assertIsInstance(bad, PluginValidationResult)
        self.assertTrue(good.is_valid)
        self.assertFalse(bad.is_valid)
        self.assertEqual(good.issues, [])
        self.assertEqual(len(bad.issues), 1)
        self.assertIsInstance(bad.issues[0], PluginValidationIssue)

    def test_is_valid_is_always_consistent_with_issues(self):
        for data in (VALID, valid(id="X"), {}, None, valid(tags=[1])):
            result = validate_manifest_data(data)

            self.assertEqual(result.is_valid, result.issues == [])

    def test_result_to_dict(self):
        payload = validate_manifest_data(valid(version="x")).to_dict()

        self.assertEqual(json.loads(json.dumps(payload)), payload)
        self.assertFalse(payload["is_valid"])
        self.assertEqual(payload["issues"][0]["field"], "version")
        self.assertTrue(payload["issues"][0]["message"])

    def test_validation_is_deterministic(self):
        data = valid(id="BAD", version="x", tags=[1], dependencies=[5])

        self.assertEqual(validate_manifest_data(data).to_dict(), validate_manifest_data(data).to_dict())


class TestValidatePluginManifestObject(TempCase):

    def make(self, **overrides) -> PluginManifest:
        fields_ = dict(
            id="akane-net-tools", name="Net Tools", version="1.0.0",
            author=PluginAuthor(name="Lingga"), api_version="1",
        )
        fields_.update(overrides)
        return PluginManifest(**fields_)

    def test_valid_object(self):
        self.assertTrue(validate_plugin_manifest(self.make()).is_valid)

    def test_object_without_api_version_is_reported_as_missing(self):
        # Setelah alignment PluginManifest membawa api_version; kosong = tidak dideklarasikan.
        result = validate_plugin_manifest(self.make(api_version=""))

        self.assertFalse(result.is_valid)
        self.assertEqual(fields(result), ["api_version"])
        self.assertIn("wajib", result.issues[0].message)

    def test_object_with_default_api_version_matches_raw_path_for_missing_field(self):
        from_object = validate_plugin_manifest(PluginManifest(
            id="aa-bb", name="N", version="1.0.0", author=PluginAuthor(name="A")))
        from_raw = validate_manifest_data({"id": "aa-bb", "name": "N", "version": "1.0.0", "author": {"name": "A"}})

        self.assertEqual(from_object.to_dict(), from_raw.to_dict())

    def test_invalid_object_fields(self):
        result = validate_plugin_manifest(self.make(id="BAD ID", name="", version="1.0"))

        self.assertEqual(fields(result), ["id", "name", "version"])

    def test_invalid_dependency_on_object(self):
        manifest = self.make(dependencies=[
            PluginDependency(id="BAD ID"),
            PluginDependency(id="abc", version_constraint="latest"),
            PluginDependency(id="abc"),          # duplikat dari [1]
        ])

        result = validate_plugin_manifest(manifest)

        self.assertEqual(
            fields(result),
            ["dependencies[0].id", "dependencies[1].version_constraint", "dependencies[2].id"],
        )
        self.assertIn("lebih dari sekali", result.issues[2].message)

    def test_non_manifest_input(self):
        for bad in (None, {"id": "x"}, "manifest"):
            result = validate_plugin_manifest(bad)

            self.assertFalse(result.is_valid)
            self.assertEqual(fields(result), ["manifest"])

    def test_broken_object_does_not_raise(self):
        broken = self.make()
        broken.author = None

        result = validate_plugin_manifest(broken)

        self.assertFalse(result.is_valid)

    def test_validator_class_dispatches_on_input_type(self):
        validator = ManifestValidator()

        self.assertTrue(validator.validate(VALID).is_valid)
        self.assertFalse(validator.validate(valid(id="X")).is_valid)
        self.assertTrue(validator.validate(self.make()).is_valid)
        self.assertFalse(validator.validate(self.make(id="X")).is_valid)

    def test_validator_class_strictness(self):
        typo = valid(nama="x")

        self.assertTrue(ManifestValidator().validate(typo).is_valid)
        self.assertFalse(ManifestValidator(strict=True).validate(typo).is_valid)

    def test_object_from_loader_cannot_reveal_type_errors_but_raw_can(self):
        # Alasan desain: parser toleran membuang tipe salah; hanya raw yang tahu penyebabnya.
        result = load_manifest(self.write("t.yaml", "id: aa-bb\nname: N\nversion: 1.0\nauthor: {name: A}\napi_version: '1'\n"))

        self.assertTrue(result.loaded)

        from_object = validate_plugin_manifest(result.manifest)
        from_raw = validate_manifest_data(result.raw)

        self.assertEqual(fields(from_object), ["version"])
        self.assertIn("wajib", from_object.issues[0].message)
        self.assertEqual(fields(from_raw), ["version"])
        self.assertIn("float", from_raw.issues[0].message)


class TestManifestAlignment(TempCase):
    """PluginManifest = representasi kanonik: api_version/capabilities/permissions dibawa modelnya."""

    def make(self, **overrides) -> PluginManifest:
        fields_ = dict(
            id="akane-net-tools", name="Net Tools", version="1.0.0",
            author=PluginAuthor(name="Lingga"), api_version="1",
        )
        fields_.update(overrides)
        return PluginManifest(**fields_)

    # ---- model

    def test_model_carries_new_fields_with_safe_defaults(self):
        bare = PluginManifest(id="aa-bb", name="N", version="1.0.0")

        self.assertEqual(bare.api_version, "")
        self.assertEqual(bare.capabilities, [])
        self.assertEqual(bare.permissions, [])

    def test_phase_1_1_style_construction_still_works(self):
        # Kompatibilitas mundur: field baru di AKHIR dan opsional.
        manifest = PluginManifest("aa-bb", "N", "1.0.0", "desc", PluginAuthor(name="A"))

        self.assertEqual(manifest.description, "desc")
        self.assertEqual(manifest.api_version, "")

    def test_default_lists_are_not_shared_between_instances(self):
        a = PluginManifest(id="aa-bb", name="A", version="1.0.0")
        b = PluginManifest(id="cc-dd", name="B", version="1.0.0")
        a.capabilities.append("x.y")

        self.assertEqual(b.capabilities, [])

    def test_to_dict_includes_new_fields_and_is_json_safe(self):
        payload = self.make(capabilities=["net.ssh"], permissions=["net:read"]).to_dict()

        self.assertEqual(payload["api_version"], "1")
        self.assertEqual(payload["capabilities"], ["net.ssh"])
        self.assertEqual(payload["permissions"], ["net:read"])
        self.assertEqual(json.loads(json.dumps(payload)), payload)

    # ---- fidelity raw -> object

    def test_no_valid_field_is_lost_between_raw_and_object(self):
        manifest = manifest_from_dict(VALID)

        self.assertEqual(manifest.id, VALID["id"])
        self.assertEqual(manifest.name, VALID["name"])
        self.assertEqual(manifest.version, VALID["version"])
        self.assertEqual(manifest.description, VALID["description"])
        self.assertEqual(manifest.author.to_dict(), VALID["author"])
        self.assertEqual(manifest.api_version, VALID["api_version"])
        self.assertEqual(manifest.entry_point, VALID["entry_point"])
        self.assertEqual(manifest.category, VALID["category"])
        self.assertEqual(manifest.tags, VALID["tags"])
        self.assertEqual(manifest.capabilities, VALID["capabilities"])
        self.assertEqual(manifest.permissions, VALID["permissions"])
        self.assertEqual(manifest.compatibility.to_dict(), VALID["compatibility"])
        self.assertEqual(manifest.dependencies[0].id, "base-utils")
        self.assertEqual(manifest.dependencies[1].version_constraint, ">=1.0.0,<2.0.0")
        self.assertTrue(manifest.dependencies[1].optional)

    def test_object_round_trips_through_to_dict(self):
        manifest = manifest_from_dict(VALID)

        self.assertEqual(manifest_from_dict(manifest.to_dict()), manifest)

    def test_order_and_duplicates_are_preserved_for_validator_to_judge(self):
        manifest = manifest_from_dict(valid(capabilities=["b.x", "a.y", "b.x"]))

        self.assertEqual(manifest.capabilities, ["b.x", "a.y", "b.x"])
        self.assertIn("lebih dari sekali", validate_plugin_manifest(manifest).issues[0].message)

    def test_lists_are_copied_not_aliased(self):
        raw = valid()
        manifest = manifest_from_dict(raw)
        raw["capabilities"].append("added.later")
        raw["permissions"].clear()
        raw["tags"].append("added-later")

        self.assertEqual(manifest.capabilities, VALID["capabilities"])
        self.assertEqual(manifest.permissions, VALID["permissions"])
        self.assertEqual(manifest.tags, VALID["tags"])

    def test_wrong_typed_new_fields_fall_back_to_defaults_without_raising(self):
        manifest = manifest_from_dict(valid(api_version=1, capabilities="net.ssh", permissions={"a": 1}))

        self.assertEqual(manifest.api_version, "")
        self.assertEqual(manifest.capabilities, [])
        self.assertEqual(manifest.permissions, [])

    def test_missing_author_is_not_disguised_as_a_real_author(self):
        manifest = manifest_from_dict(valid(author=_DROP))

        self.assertEqual(manifest.author.name, "")
        self.assertEqual(fields(validate_plugin_manifest(manifest)), ["author.name"])

    def test_string_optional_is_not_coerced_to_true(self):
        raw = valid(dependencies=[{"id": "abc", "optional": "false"}])

        self.assertFalse(manifest_from_dict(raw).dependencies[0].optional)
        # ... dan jalur raw tetap melaporkan penyebabnya.
        self.assertEqual(fields(validate_manifest_data(raw)), ["dependencies[0].optional"])

    # ---- object path validates the new fields

    def test_object_path_checks_api_version_format(self):
        for bad in ("v1", "1.x", "1.0.0.0", " 1"):
            self.assertEqual(fields(validate_plugin_manifest(self.make(api_version=bad))), ["api_version"], bad)

        for good in ("1", "1.0", "1.0.0"):
            self.assertTrue(validate_plugin_manifest(self.make(api_version=good)).is_valid, good)

    def test_object_path_checks_capabilities_and_permissions(self):
        result = validate_plugin_manifest(self.make(
            capabilities=["Net.SSH", "net.ssh", "net.ssh"],
            permissions=["", "net:read"],
        ))

        self.assertEqual(
            sorted(fields(result)),
            sorted(["capabilities[0]", "capabilities[2]", "permissions[0]"]),
        )

    def test_object_path_does_not_split_a_string_into_characters(self):
        # to_dict() memakai list(...): "abc" akan jadi ["a","b","c"] dan lolos.
        result = validate_plugin_manifest(self.make(capabilities="network"))

        self.assertFalse(result.is_valid)
        self.assertEqual(fields(result), ["capabilities"])

    def test_object_path_strict_mode_accepts_all_canonical_fields(self):
        manifest = manifest_from_dict(VALID)

        self.assertTrue(validate_plugin_manifest(manifest, strict=True).is_valid)

    # ---- raw vs object agree; raw still catches malformed input

    def test_raw_and_object_agree_on_valid_manifest(self):
        self.assertTrue(validate_manifest_data(VALID).is_valid)
        self.assertTrue(validate_plugin_manifest(manifest_from_dict(VALID)).is_valid)

    def test_raw_and_object_report_same_issues_for_well_typed_bad_values(self):
        for override in (
            {"id": "BAD ID"},
            {"version": "1.0"},
            {"api_version": "one"},
            {"capabilities": ["A", "b"]},
            {"permissions": ["x", "x"]},
            {"dependencies": [{"id": "aa-bb", "version_constraint": "latest"}]},
            {"compatibility": {"min_aira_version": "2.0.0", "max_aira_version": "1.0.0"}},
        ):
            raw = valid(**override)

            self.assertEqual(
                validate_plugin_manifest(manifest_from_dict(raw)).to_dict(),
                validate_manifest_data(raw).to_dict(),
                override,
            )

    def test_raw_path_still_detects_malformed_input_the_parser_normalises(self):
        raw = valid(api_version=1, capabilities="network.ssh", version=1.0)

        self.assertEqual(fields(validate_manifest_data(raw)), ["version", "api_version", "capabilities"])
        # Objek hasil parser tidak lagi punya informasi tipe aslinya.
        self.assertNotEqual(
            fields(validate_plugin_manifest(manifest_from_dict(raw))),
            fields(validate_manifest_data(raw)),
        )

    def test_loader_result_object_is_canonical_after_successful_parse(self):
        result = load_manifest(self.write_yaml(VALID))

        self.assertTrue(result.loaded)
        self.assertEqual(result.manifest, manifest_from_dict(VALID))
        self.assertEqual(result.manifest.capabilities, VALID["capabilities"])
        self.assertTrue(validate_plugin_manifest(result.manifest).is_valid)

    # ---- yang tidak boleh menjadi wajib

    def test_entry_point_platforms_and_extras_remain_optional(self):
        minimal = {"id": "aa-bb", "name": "N", "version": "1.0.0", "author": {"name": "A"}, "api_version": "1"}

        self.assertTrue(validate_manifest_data(minimal).is_valid)
        self.assertTrue(validate_plugin_manifest(manifest_from_dict(minimal)).is_valid)
        for optional in ("entry_point", "category", "tags", "compatibility", "capabilities", "permissions",
                         "dependencies", "description"):
            self.assertNotIn(optional, REQUIRED_FIELDS)


# ============================================================ LOADER + VALIDATOR (end to end)

class TestLoaderThenValidator(TempCase):

    def test_valid_file_end_to_end(self):
        loaded = load_manifest(self.write_yaml(VALID))

        self.assertTrue(loaded.loaded)
        self.assertTrue(validate_manifest_data(loaded.raw).is_valid)
        self.assertTrue(validate_plugin_manifest(loaded.manifest).is_valid)

    def test_invalid_file_end_to_end(self):
        bad = valid(id="Bad ID", version="1.0", dependencies=[{"id": "x"}], api_version=_DROP)

        loaded = load_manifest(self.write_yaml(bad))
        result = validate_manifest_data(loaded.raw)

        self.assertTrue(loaded.loaded)
        self.assertFalse(result.is_valid)
        self.assertEqual(fields(result), ["id", "version", "api_version", "dependencies[0].id"])

    def test_hand_written_yaml_with_typical_mistakes(self):
        text = (
            "id: akane-net-tools\n"
            "name: Net Tools\n"
            "version: 1.0\n"              # tanpa kutip -> float
            "api_version: 1\n"            # tanpa kutip -> int
            "author: Lingga\n"            # string, bukan mapping
            "capabilities: network.ssh\n"  # bukan list
        )

        result = validate_manifest_data(load_manifest(self.write("salah.yaml", text)).raw)

        self.assertEqual(fields(result), ["version", "author", "api_version", "capabilities"])

    def test_committed_example_style_manifest_round_trips(self):
        loaded = load_manifest(self.write_yaml(VALID))

        self.assertEqual(loaded.manifest.to_dict()["id"], VALID["id"])
        self.assertEqual(loaded.manifest.to_dict()["dependencies"][1]["version_constraint"], ">=1.0.0,<2.0.0")


# ============================================================ BATAS TANGGUNG JAWAB

FORBIDDEN_IMPORT_PREFIXES = (
    "agents", "api", "tools", "core.events", "core.orchestrator", "core.brain",
    "core.logger", "core.memory", "core.model_", "paramiko", "pysnmp", "requests",
    "socket", "subprocess", "importlib", "sqlite3", "threading",
)

FORBIDDEN_WORDS = (
    "PluginManager", "PluginRegistry", "CapabilityRegistry", "PermissionEngine",
    "event_bus", "import_module", "__import__", "exec(", "eval(",
)


def _imports(path: Path) -> list[str]:
    names = []

    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.append(node.module)

    return names


class TestSeparationOfConcerns(unittest.TestCase):

    def test_neither_module_imports_infrastructure(self):
        for name in ("loader.py", "validator.py"):
            for imported in _imports(PLUGINS_DIR / name):
                self.assertFalse(
                    imported.startswith(FORBIDDEN_IMPORT_PREFIXES),
                    f"{name} mengimpor {imported} (di luar tanggung jawabnya)",
                )

    def test_neither_module_only_uses_plugin_foundation_from_core(self):
        for name in ("loader.py", "validator.py"):
            for imported in _imports(PLUGINS_DIR / name):
                if imported.startswith("core"):
                    self.assertTrue(imported.startswith("core.plugins"), f"{name} mengimpor {imported}")

    def test_loader_and_validator_do_not_depend_on_each_other(self):
        self.assertNotIn("core.plugins.validator", _imports(PLUGINS_DIR / "loader.py"))
        self.assertNotIn("core.plugins.loader", _imports(PLUGINS_DIR / "validator.py"))

    def test_no_lifecycle_manager_registry_or_dynamic_execution(self):
        for name in ("loader.py", "validator.py"):
            source = (PLUGINS_DIR / name).read_text(encoding="utf-8")
            code = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))

            for word in FORBIDDEN_WORDS:
                # Docstring boleh menyebut konsep-konsep itu untuk menjelaskan batasnya;
                # yang dilarang adalah pemakaiannya sebagai kode.
                tree = ast.parse(code)
                used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | \
                       {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
                self.assertNotIn(word.rstrip("("), used, f"{name} memakai {word}")

    def test_loader_uses_safe_load_only(self):
        source = (PLUGINS_DIR / "loader.py").read_text(encoding="utf-8")

        self.assertIn("yaml.safe_load", source)
        for unsafe in ("yaml.load(", "yaml.unsafe_load", "yaml.full_load", "FullLoader", "UnsafeLoader"):
            self.assertNotIn(unsafe, source)

    def test_only_expected_files_were_added_to_plugins_package(self):
        present = {p.name for p in PLUGINS_DIR.glob("*.py")}

        self.assertLessEqual({"loader.py", "validator.py"}, present)
        for forbidden in ("manager.py", "registry.py", "capabilities.py", "permissions.py"):
            self.assertNotIn(forbidden, present)


if __name__ == "__main__":
    unittest.main()
