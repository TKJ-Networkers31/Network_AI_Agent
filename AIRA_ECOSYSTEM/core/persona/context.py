"""
core/persona/context.py — PersonaContext: hasil deterministik Persona Engine.

    profile + behavior + persona_text + PersonaConfig  ->  PersonaContext

PersonaContext hanya berisi PRESENTASI:
    identity_text   - siapa AIRA + sapaan user + bahasa/zona waktu
    style_text      - gaya bicara, nuansa, gaya mengajar, gaya jawab, ekspresi emosi
    formatting_text - aturan format jawaban (Markdown)

Ia tidak memilih model, tool, klasifikasi, izin, atau keputusan keamanan,
dan tidak mengimpor modul reasoning mana pun. Pemanggil (prompt_builder ->
PersonaEngine.build -> ContextBuilder) menempatkan teks ini di system prompt.

Deterministik: input sama -> PersonaContext sama (tanpa waktu/acak/I-O).
"""

import re
from dataclasses import dataclass
from typing import Any, Optional

from core.persona.emotion import derive_emotion, describe_emotion
from core.persona.loader import PersonaConfig, get_persona_config
from core.persona.scales import pick
from core.persona.validator import BEHAVIOR_KEYS, clamp_behavior_value

_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


def render_template(template: str, **values: Any) -> str:
    """Isi {placeholder} dalam SATU putaran - nilai user yang memuat "{...}" tidak ikut diperluas."""
    return _PLACEHOLDER_RE.sub(lambda m: str(values.get(m.group(1), m.group(0))), template)


def _clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _text(value: Any) -> str:
    return value if isinstance(value, str) and value.strip() else ""


@dataclass(frozen=True)
class PersonaContext:
    preset_id: Optional[str]
    assistant_name: str
    user_name: Optional[str]
    language: str
    timezone: str
    identity_text: str
    style_text: str
    formatting_text: str
    behavior: dict
    emotion: dict
    warnings: tuple = ()

    def to_dict(self) -> dict:
        return {
            "preset_id": self.preset_id,
            "assistant_name": self.assistant_name,
            "user_name": self.user_name,
            "language": self.language,
            "timezone": self.timezone,
            "identity_text": self.identity_text,
            "style_text": self.style_text,
            "formatting_text": self.formatting_text,
            "behavior": dict(self.behavior),
            "emotion": dict(self.emotion),
            "warnings": list(self.warnings),
        }


def _behavior_narrative(behavior: dict, config: PersonaConfig) -> str:
    scales = config.behavior["scales"]
    labels = config.tone["behavior_labels"]

    parts = [f"{labels[key]}={pick(scales[key], behavior[key])}" for key in BEHAVIOR_KEYS]

    return f"=== {config.tone['section_titles']['behavior']} === " + "; ".join(parts)


def build_persona_context(
    profile: Optional[dict] = None,
    behavior: Optional[dict] = None,
    persona_text: Optional[dict] = None,
    config: Optional[PersonaConfig] = None,
    preset_id: Optional[str] = None,
) -> PersonaContext:
    config = config or get_persona_config()
    profile = profile if isinstance(profile, dict) else {}
    behavior_in = behavior if isinstance(behavior, dict) else {}
    persona_text = persona_text if isinstance(persona_text, dict) else {}

    identity = config.identity
    templates = identity["templates"]

    assistant_name = _clean(profile.get("assistant_name")) or identity["assistant_name"]
    user_name = _clean(profile.get("user_name")) or None
    language = _clean(profile.get("language")) or identity["language"]
    timezone = _clean(profile.get("timezone")) or identity["timezone"]

    defaults = config.behavior["defaults"]
    behavior_norm = {
        key: clamp_behavior_value(behavior_in[key] if behavior_in.get(key) is not None else defaults[key])
        for key in BEHAVIOR_KEYS
    }

    # ---- identitas
    lines = [
        render_template(templates["intro"], assistant_name=assistant_name, expansion=identity["expansion"]),
        _text(persona_text.get("identity")),
    ]
    if user_name:
        lines.append(render_template(templates["user_name"], user_name=user_name))
    lines.append(render_template(templates["locale"], language=language, timezone=timezone))
    identity_text = "\n".join(line for line in lines if line)

    # ---- gaya
    titles = config.tone["section_titles"]
    blocks = []

    for key, title_key in (
        ("speaking_style", "speaking_style"),
        ("romantic_flavor", "relationship"),
        ("teaching_style", "teaching_style"),
    ):
        body = _text(persona_text.get(key))
        if body:
            blocks.append(f"=== {titles[title_key]} ===\n{body}")

    blocks.append(_behavior_narrative(behavior_norm, config))

    emotion_text = describe_emotion(behavior_norm, config.tone["emotion"])
    if emotion_text:
        blocks.append(emotion_text)

    return PersonaContext(
        preset_id=preset_id or (_clean(profile.get("active_preset")) or None),
        assistant_name=assistant_name,
        user_name=user_name,
        language=language,
        timezone=timezone,
        identity_text=identity_text,
        style_text="\n\n".join(blocks),
        formatting_text=config.tone["formatting"],
        behavior=behavior_norm,
        emotion=derive_emotion(behavior_norm),
        warnings=config.warnings,
    )
