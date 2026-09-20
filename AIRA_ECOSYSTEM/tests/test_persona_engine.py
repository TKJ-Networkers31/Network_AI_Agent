"""
tests/test_persona_engine.py — unit test Persona Engine (Sprint 2 / Worker 2).

Cakupan: pemuatan config, config hilang/rusak, PersonaContext, kompatibilitas
prompt lama, integrasi Context Builder & PersonaEngine, dan pemisahan dari
reasoning/pemilihan model. Test yang butuh komponen runtime (core.context,
core.persona.engine asli) di-skip - bukan gagal - kalau tidak bisa diimpor.

Jalankan dari root AIRA_ECOSYSTEM/:
    python -m unittest tests.test_persona_engine -v
"""

import ast
import json
import logging
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

import core.persona as persona_pkg
from core.persona import defaults as D
from core.persona.context import build_persona_context, render_template
from core.persona.emotion import derive_emotion, describe_emotion
from core.persona.loader import FORBIDDEN_KEYS, PERSONA_DIR, load_persona_config
from core.persona.prompt_builder import CORE_RULES, build_prompt
from core.persona.validator import BEHAVIOR_KEYS


def setUpModule():
    logging.disable(logging.CRITICAL)


def tearDownModule():
    logging.disable(logging.NOTSET)


def make_config_dir(tmp: str, **files) -> Path:
    """Salin config bawaan ke tmp lalu timpa/hapus file. value None = hapus."""
    base = Path(tmp)
    (base / "styles").mkdir()
    for path in PERSONA_DIR.glob("*.yaml"):
        (base / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    for path in (PERSONA_DIR / "styles").glob("*.yaml"):
        (base / "styles" / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    for name, content in files.items():
        target = base / name.replace("__", "/")
        if content is None:
            target.unlink()
        else:
            target.write_text(content, encoding="utf-8")
    return base


AKANE = D.DEFAULT_STYLES["akane"]
SENSEI = D.DEFAULT_STYLES["sensei"]


def ctx_for(style, **profile_extra):
    return build_persona_context({**style["profile"], **profile_extra}, style["behavior"], style["persona_text"])


# ============================================================ config bawaan

class TestShippedConfig(unittest.TestCase):

    def test_loads_without_warnings(self):
        config = load_persona_config()
        self.assertEqual(config.warnings, ())

    def test_yaml_matches_fallback_defaults(self):
        # drift guard: file YAML == defaults.py
        config = load_persona_config()
        self.assertEqual(config.identity, D.DEFAULT_IDENTITY)
        self.assertEqual(config.behavior, D.DEFAULT_BEHAVIOR)
        self.assertEqual(config.tone, D.DEFAULT_TONE)
        self.assertEqual(config.styles, D.DEFAULT_STYLES)

    def test_builtin_presets_come_from_config(self):
        from core.persona.presets import BUILTIN_PRESETS
        self.assertEqual(set(BUILTIN_PRESETS), {"akane", "sensei", "companion"})
        for preset in BUILTIN_PRESETS.values():
            self.assertEqual(set(preset), {"name", "description", "profile", "behavior", "persona_text"})
            self.assertEqual(set(preset["behavior"]), set(BEHAVIOR_KEYS))

    def test_romantic_guardrail_preserved(self):
        text = ctx_for(AKANE).style_text
        self.assertIn("JANGAN PERNAH: mengaku mencintai pengguna", text)


# ============================================================ config rusak

class TestLoaderResilience(unittest.TestCase):

    def test_empty_directory_uses_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = load_persona_config(Path(tmp))
        self.assertEqual(config.identity, D.DEFAULT_IDENTITY)
        self.assertEqual(config.styles, D.DEFAULT_STYLES)
        self.assertTrue(config.warnings)

    def test_nonexistent_directory_never_raises(self):
        config = load_persona_config(Path("/tidak/ada/sama/sekali"))
        self.assertEqual(config.tone, D.DEFAULT_TONE)

    def test_invalid_yaml_syntax_falls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = make_config_dir(tmp, **{"tone.yaml": "a: [unclosed\n  b: : :"})
            config = load_persona_config(base)
        self.assertEqual(config.tone, D.DEFAULT_TONE)
        self.assertTrue(any("tone.yaml" in w for w in config.warnings))

    def test_non_mapping_file_falls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = make_config_dir(tmp, **{"identity.yaml": "- satu\n- dua\n"})
            config = load_persona_config(base)
        self.assertEqual(config.identity, D.DEFAULT_IDENTITY)

    def test_forbidden_keys_reject_whole_file(self):
        for key in ("model", "tools", "routing", "permissions", "task_label", "security"):
            self.assertIn(key, FORBIDDEN_KEYS)
            with tempfile.TemporaryDirectory() as tmp:
                content = f"assistant_name: HACKED\n{key}: x\n"
                base = make_config_dir(tmp, **{"identity.yaml": content})
                config = load_persona_config(base)
            self.assertEqual(config.identity["assistant_name"], "AIRA", key)
            self.assertTrue(any("di luar ranah persona" in w for w in config.warnings))

    def test_forbidden_key_nested_in_style_rejects_style(self):
        style = yaml.safe_dump({"name": "EVIL", "persona_text": {"identity": "x"}, "profile": {"tools": ["ping"]}})
        with tempfile.TemporaryDirectory() as tmp:
            base = make_config_dir(tmp, **{"styles__evil.yaml": style})
            config = load_persona_config(base)
        self.assertNotIn("evil", config.styles)

    def test_bad_scale_falls_back_only_for_that_scale(self):
        raw = yaml.safe_load((PERSONA_DIR / "behavior.yaml").read_text(encoding="utf-8"))
        raw["scales"]["empathy"] = [{"min": "nol", "text": 5}]
        raw["scales"]["verbosity"] = [{"min": 0, "text": "custom"}]
        with tempfile.TemporaryDirectory() as tmp:
            base = make_config_dir(tmp, **{"behavior.yaml": yaml.safe_dump(raw, allow_unicode=True)})
            config = load_persona_config(base)
        self.assertEqual(config.behavior["scales"]["empathy"], D.DEFAULT_BEHAVIOR["scales"]["empathy"])
        self.assertEqual(config.behavior["scales"]["verbosity"], [(0, "custom")])

    def test_wrong_typed_string_value_falls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = make_config_dir(tmp, **{"identity.yaml": "assistant_name: 123\nlanguage: en\n"})
            config = load_persona_config(base)
        self.assertEqual(config.identity["assistant_name"], "AIRA")
        self.assertEqual(config.identity["language"], "en")

    def test_defaults_are_clamped_and_bool_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = make_config_dir(tmp, **{"behavior.yaml": "defaults:\n  empathy: 999\n  playfulness: true\n"})
            config = load_persona_config(base)
        self.assertEqual(config.behavior["defaults"]["empathy"], 100)
        self.assertEqual(config.behavior["defaults"]["playfulness"], D.DEFAULT_BEHAVIOR["defaults"]["playfulness"])

    def test_invalid_style_skipped_and_bad_id_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = make_config_dir(tmp, **{
                "styles__akane.yaml": "description: tanpa nama\n",
                "styles__Bad Name.yaml": "name: X\n",
            })
            config = load_persona_config(base)
        self.assertEqual(config.styles["akane"], D.DEFAULT_STYLES["akane"])   # fallback bawaan
        self.assertNotIn("bad name", config.styles)

    def test_custom_valid_style_is_added_with_behavior_defaults(self):
        style = yaml.safe_dump({"name": "CUSTOM", "behavior": {"empathy": 200}, "persona_text": {"identity": "hai"}})
        with tempfile.TemporaryDirectory() as tmp:
            base = make_config_dir(tmp, **{"styles__custom.yaml": style})
            config = load_persona_config(base)
        custom = config.styles["custom"]
        self.assertEqual(custom["behavior"]["empathy"], 100)
        self.assertEqual(custom["behavior"]["friendliness"], D.DEFAULT_BEHAVIOR["defaults"]["friendliness"])

    def test_style_cannot_set_active_preset(self):
        style = yaml.safe_dump({"name": "X", "profile": {"active_preset": "akane", "language": "en"}})
        with tempfile.TemporaryDirectory() as tmp:
            config = load_persona_config(make_config_dir(tmp, **{"styles__x.yaml": style}))
        self.assertNotIn("active_preset", config.styles["x"]["profile"])


# ============================================================ PersonaContext

class TestPersonaContext(unittest.TestCase):

    def test_deterministic(self):
        self.assertEqual(ctx_for(AKANE), ctx_for(AKANE))
        self.assertEqual(ctx_for(AKANE).to_dict(), ctx_for(AKANE).to_dict())

    def test_to_dict_is_json_serializable(self):
        json.dumps(ctx_for(AKANE, user_name="Lingga").to_dict())

    def test_identity_block_matches_legacy_layout(self):
        ctx = ctx_for(AKANE, user_name="Lingga")
        lines = ctx.identity_text.split("\n")
        self.assertEqual(lines[0], "Kamu adalah AIRA (Adaptive Intelligent Reasoning Assistant).")
        self.assertTrue(lines[1].startswith("Nama panggilan internalmu adalah Akane"))
        self.assertEqual(lines[2], "User memperkenalkan diri sebagai 'Lingga' - gunakan natural, jangan dipaksakan.")
        self.assertEqual(lines[3], "Jawab dalam bahasa: id. Zona waktu acuan: Asia/Jakarta.")

    def test_no_user_line_without_user_name(self):
        self.assertNotIn("memperkenalkan diri sebagai", ctx_for(AKANE).identity_text)

    def test_placeholder_in_user_name_not_expanded(self):
        ctx = ctx_for(AKANE, user_name="{language} {timezone} {x}")
        self.assertIn("'{language} {timezone} {x}'", ctx.identity_text)
        self.assertEqual(render_template("{a}{b}", a="{b}", b="Z"), "{b}Z")

    def test_legacy_behavior_line_exact(self):
        self.assertIn(
            "=== GAYA JAWAB === profesionalisme=calm professional mentor, presisi tinggi; "
            "keramahan=warm companion, peduli progres user; playful=sesekali teasing ringan; "
            "verbositas=detail dengan alasan; empati=peka kondisi emosional user; "
            "kedalaman=fundamental sampai advanced: konsep, alasan, implementasi, best practice, kesalahan umum",
            ctx_for(AKANE).style_text,
        )

    def test_missing_or_garbage_inputs_use_defaults(self):
        ctx = build_persona_context(None, {"empathy": None, "friendliness": "abc"}, None)
        self.assertEqual(ctx.assistant_name, "AIRA")
        self.assertEqual(ctx.behavior["empathy"], D.DEFAULT_BEHAVIOR["defaults"]["empathy"])
        self.assertEqual(ctx.behavior["friendliness"], 50)   # clamp_behavior_value untuk non-angka
        self.assertEqual(set(ctx.behavior), set(BEHAVIOR_KEYS))

    def test_presets_produce_different_style_same_structure(self):
        a, s = ctx_for(AKANE), ctx_for(SENSEI)
        self.assertNotEqual(a.style_text, s.style_text)
        self.assertEqual(a.formatting_text, s.formatting_text)
        self.assertNotIn("NUANSA HUBUNGAN", s.style_text)   # sensei tanpa romantic_flavor

    def test_emotion_derivation_and_guard(self):
        self.assertEqual(derive_emotion(AKANE["behavior"]), {"warmth": 79, "humor": 42, "expressiveness": 66})
        text = describe_emotion(AKANE["behavior"], D.DEFAULT_TONE["emotion"])
        self.assertIn("kehangatan=hangat & suportif", text)
        self.assertIn("jangan pernah mengubah fakta", text)

    def test_emotion_can_be_disabled_in_config(self):
        raw = yaml.safe_load((PERSONA_DIR / "tone.yaml").read_text(encoding="utf-8"))
        raw["emotion"]["enabled"] = False
        with tempfile.TemporaryDirectory() as tmp:
            config = load_persona_config(make_config_dir(tmp, **{"tone.yaml": yaml.safe_dump(raw, allow_unicode=True)}))
        ctx = build_persona_context(AKANE["profile"], AKANE["behavior"], AKANE["persona_text"], config=config)
        self.assertNotIn("EKSPRESI EMOSI", ctx.style_text)

    def test_config_change_changes_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = make_config_dir(tmp, **{"identity.yaml": "expansion: Sistem Uji\n"})
            config = load_persona_config(base)
        ctx = build_persona_context(AKANE["profile"], AKANE["behavior"], AKANE["persona_text"], config=config)
        self.assertTrue(ctx.identity_text.startswith("Kamu adalah AIRA (Sistem Uji)."))


# ============================================================ prompt

class TestPromptAssembly(unittest.TestCase):

    def test_section_order(self):
        prompt = build_prompt(AKANE["profile"], AKANE["behavior"], AKANE["persona_text"], "EXTRA_MARK")
        order = [
            "Kamu adalah AIRA", "=== ATURAN INTI ===", "=== GAYA BICARA ===", "=== GAYA JAWAB ===",
            "=== EKSPRESI EMOSI ===", "=== FORMAT JAWABAN ===", "=== ILUSTRASI VISUAL ===",
            "=== LOKASI USER ===", "EXTRA_MARK",
        ]
        positions = [prompt.index(marker) for marker in order]
        self.assertEqual(positions, sorted(positions))

    def test_system_rules_are_not_persona_controlled(self):
        # aturan inti/ilustrasi/lokasi identik apa pun preset-nya
        for style in D.DEFAULT_STYLES.values():
            prompt = build_prompt(style["profile"], style["behavior"], style["persona_text"])
            self.assertIn(CORE_RULES.strip(), prompt)
            self.assertEqual(prompt.count("=== ATURAN INTI ==="), 1)

    def test_persona_context_argument_is_equivalent(self):
        ctx = ctx_for(SENSEI)
        self.assertEqual(
            build_prompt(SENSEI["profile"], SENSEI["behavior"], SENSEI["persona_text"], "X"),
            build_prompt(persona_context=ctx, extra_context="X"),
        )


# ============================================================ pemisahan

FORBIDDEN_IMPORT_PREFIXES = (
    "core.model_", "core.task_classifier", "core.orchestrator", "core.brain",
    "core.context", "agents", "tools", "api",
)


class TestSeparationFromReasoning(unittest.TestCase):

    def test_persona_modules_do_not_import_reasoning_layers(self):
        for path in sorted(PERSONA_DIR.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                for name in names:
                    self.assertFalse(
                        name.startswith(FORBIDDEN_IMPORT_PREFIXES),
                        f"{path.name} mengimpor {name} (di luar ranah persona)",
                    )

    def test_shipped_yaml_has_no_forbidden_keys(self):
        from core.persona.loader import _find_forbidden
        for path in [*PERSONA_DIR.glob("*.yaml"), *(PERSONA_DIR / "styles").glob("*.yaml")]:
            self.assertEqual(_find_forbidden(yaml.safe_load(path.read_text(encoding="utf-8"))), [], path.name)

    def test_persona_context_exposes_only_presentation_fields(self):
        keys = set(ctx_for(AKANE).to_dict())
        self.assertEqual(keys, {
            "preset_id", "assistant_name", "user_name", "language", "timezone", "identity_text",
            "style_text", "formatting_text", "behavior", "emotion", "warnings",
        })

    def test_persona_text_does_not_name_models_or_task_labels(self):
        for style in D.DEFAULT_STYLES.values():
            blob = json.dumps(style).lower()
            for word in ("openrouter", "ollama", "nemotron", "model_id", "primary_label"):
                self.assertNotIn(word, blob)


# ============================================================ integrasi

class TestContextBuilderIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        try:
            from core.context import ContextBuilder
        except ImportError as exc:
            raise unittest.SkipTest(f"core.context tidak bisa diimpor: {exc}")
        cls.ContextBuilder = ContextBuilder

    def _builder(self, style):
        def composer(extra_context):
            return build_prompt(style["profile"], style["behavior"], style["persona_text"], extra_context)

        return self.ContextBuilder(
            persona_state=lambda: {"profile": style["profile"], "behavior": style["behavior"]},
            prompt_composer=composer,
            memory_text=lambda: "MEMORY_MARK",
            runtime_text=lambda: "RUNTIME_MARK",
            location_text=lambda sid: "LOCATION_MARK",
            tool_summary=lambda: {"count": 1, "names": ["ping"], "categories": {"network": ["ping"]}},
        )

    def test_persona_prompt_flows_through_builder_contract(self):
        context = self._builder(AKANE).build("cek R1", session_id="s1", task={"primary_label": "networking"})

        self.assertEqual(context.system_prompt.count("Kamu adalah AIRA"), 1)
        for marker in ("RUNTIME_MARK", "MEMORY_MARK", "LOCATION_MARK"):
            self.assertEqual(context.system_prompt.count(marker), 1)
        self.assertTrue(context.system_prompt.index("=== LOKASI USER ===") < context.system_prompt.index("RUNTIME_MARK"))

    def test_persona_does_not_change_reasoning_side_of_context(self):
        task = {"primary_label": "networking", "confidence": 0.9}
        a = self._builder(AKANE).build("cek R1", session_id="s1", task=task)
        s = self._builder(SENSEI).build("cek R1", session_id="s1", task=task)

        self.assertNotEqual(a.system_prompt, s.system_prompt)   # gaya beda
        self.assertEqual(a.task, s.task)                        # klasifikasi sama
        self.assertEqual(a.tool_context, s.tool_context)        # tool sama
        self.assertEqual(a.memory, s.memory)
        self.assertEqual(a.location, s.location)
        self.assertEqual(a.user_input, s.user_input)


class TestEngineIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        try:
            import core.persona.engine as engine_module
            engine_module._init_db
            engine_module.PersonaEngine.get_profile
        except (ImportError, AttributeError) as exc:
            raise unittest.SkipTest(f"PersonaEngine asli tidak tersedia: {exc}")
        cls.engine_module = engine_module

    def test_engine_prompt_uses_persona_context(self):
        module = self.engine_module

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(module, "DB_FILE", Path(tmp) / "persona_test.db"):
            module._init_db()
            engine = module.PersonaEngine()

            ctx = persona_pkg.get_persona_context(engine)
            self.assertEqual(ctx.preset_id, "akane")

            prompt = engine.build("EXTRA_MARK")
            self.assertEqual(prompt, build_prompt(persona_context=ctx, extra_context="EXTRA_MARK"))
            self.assertEqual(prompt.count("EXTRA_MARK"), 1)

            engine.apply_preset("sensei")
            sensei_ctx = persona_pkg.get_persona_context(engine)
            self.assertEqual(sensei_ctx.preset_id, "sensei")
            self.assertNotEqual(sensei_ctx.style_text, ctx.style_text)


if __name__ == "__main__":
    unittest.main()
