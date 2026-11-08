"""
core/persona/loader.py — memuat & memvalidasi konfigurasi persona (YAML).

File yang dibaca (semuanya di folder core/persona/):
    identity.yaml, behavior.yaml, tone.yaml, styles/<preset_id>.yaml

Prinsip:
  - Tidak pernah raise. File hilang / YAML rusak / bentuk salah / nilai
    tidak valid -> bagian itu memakai default dari core/persona/defaults.py
    dan sebuah peringatan dicatat di PersonaConfig.warnings.
  - BATAS PEMISAHAN: file persona hanya boleh berisi presentasi. Kalau
    sebuah file memuat key yang menyentuh model/tool/routing/klasifikasi/
    izin/keamanan (FORBIDDEN_KEYS), SELURUH file itu ditolak. Persona
    dengan begitu tidak bisa (bahkan lewat konfigurasi) ikut menentukan
    pemilihan model, tool, klasifikasi task, atau keputusan keamanan.
  - Deterministik: hasil hanya bergantung pada isi file.
"""

import copy
import logging
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import yaml

from core.persona import defaults as D
from core.persona.validator import (
    BEHAVIOR_KEYS, clamp_behavior_value, validate_behavior_fields, validate_profile_fields,
)

logger = logging.getLogger("aira.persona.loader")

PERSONA_DIR = Path(__file__).resolve().parent

FORBIDDEN_KEYS = frozenset({
    "model", "models", "model_id", "provider", "providers", "routing", "router",
    "fallback", "tool", "tools", "tool_choice", "capabilities", "capability",
    "permissions", "permission", "security", "policy", "classification",
    "classifier", "task", "task_label", "reasoning", "planner",
})

_STYLE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


@dataclass(frozen=True)
class PersonaConfig:
    identity: dict
    behavior: dict   # {"defaults": {key: int}, "scales": {key: [(min, text)]}}
    tone: dict
    styles: dict     # preset_id -> {name, description, profile, behavior, persona_text}
    warnings: tuple = ()
    source_dir: Optional[str] = None


# ------------------------------------------------------------------ helpers

def _str(value: Any) -> Optional[str]:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _find_forbidden(node: Any, path: str = "") -> list[str]:
    found: list[str] = []

    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{path}.{key}" if path else str(key)
            if str(key).strip().lower() in FORBIDDEN_KEYS:
                found.append(here)
            found.extend(_find_forbidden(value, here))
    elif isinstance(node, list):
        for index, item in enumerate(node):
            found.extend(_find_forbidden(item, f"{path}[{index}]"))

    return found


def _read_yaml(path: Path, label: str, warnings: list[str]) -> Optional[dict]:
    if not path.is_file():
        warnings.append(f"{label}: file tidak ditemukan - memakai default.")
        return None

    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle)
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        warnings.append(f"{label}: tidak bisa dibaca ({type(exc).__name__}) - memakai default.")
        return None

    if not isinstance(raw, dict):
        warnings.append(f"{label}: isi harus berupa mapping - memakai default.")
        return None

    forbidden = _find_forbidden(raw)
    if forbidden:
        warnings.append(
            f"{label}: ditolak karena memuat key di luar ranah persona "
            f"({', '.join(forbidden)}) - memakai default."
        )
        return None

    return raw


def _overlay_strings(target: dict, raw: Any, keys, where: str, warnings: list[str]) -> None:
    if raw is None:
        return

    if not isinstance(raw, dict):
        warnings.append(f"{where}: harus berupa mapping - memakai default.")
        return

    for key in keys:
        if key not in raw:
            continue
        value = _str(raw[key])
        if value is None:
            warnings.append(f"{where}.{key}: harus string non-kosong - memakai default.")
        else:
            target[key] = value


def _normalize_scale(raw: Any) -> Optional[list[tuple[int, str]]]:
    if not isinstance(raw, list) or not raw:
        return None

    scale: list[tuple[int, str]] = []

    for item in raw:
        if not isinstance(item, dict):
            return None
        minimum, text = item.get("min"), _str(item.get("text"))
        if isinstance(minimum, bool) or not isinstance(minimum, int) or text is None:
            return None
        scale.append((minimum, text))

    if len({minimum for minimum, _ in scale}) != len(scale):
        return None

    return sorted(scale, key=lambda entry: entry[0])


def _overlay_scales(target: dict, raw: Any, keys, where: str, warnings: list[str]) -> None:
    if raw is None:
        return

    if not isinstance(raw, dict):
        warnings.append(f"{where}: harus berupa mapping - memakai default.")
        return

    for key in keys:
        if key not in raw:
            continue
        scale = _normalize_scale(raw[key])
        if scale is None:
            warnings.append(f"{where}.{key}: skala tidak valid (butuh list {{min, text}}) - memakai default.")
        else:
            target[key] = scale


# ------------------------------------------------------------------ sections

def _load_identity(raw: Optional[dict], warnings: list[str]) -> dict:
    result = copy.deepcopy(D.DEFAULT_IDENTITY)

    if raw is None:
        return result

    _overlay_strings(result, raw, ("assistant_name", "expansion", "language", "timezone"),
                     "identity.yaml", warnings)
    _overlay_strings(result["templates"], raw.get("templates"), tuple(result["templates"]),
                     "identity.yaml.templates", warnings)
    return result


def _load_behavior(raw: Optional[dict], warnings: list[str]) -> dict:
    result = copy.deepcopy(D.DEFAULT_BEHAVIOR)

    if raw is None:
        return result

    raw_defaults = raw.get("defaults")
    if raw_defaults is not None:
        if not isinstance(raw_defaults, dict):
            warnings.append("behavior.yaml.defaults: harus berupa mapping - memakai default.")
        else:
            for key in BEHAVIOR_KEYS:
                if key not in raw_defaults:
                    continue
                value = raw_defaults[key]
                if isinstance(value, bool) or not isinstance(value, int):
                    warnings.append(f"behavior.yaml.defaults.{key}: harus angka 0-100 - memakai default.")
                else:
                    result["defaults"][key] = clamp_behavior_value(value)

    _overlay_scales(result["scales"], raw.get("scales"), BEHAVIOR_KEYS, "behavior.yaml.scales", warnings)
    return result


def _load_tone(raw: Optional[dict], warnings: list[str]) -> dict:
    result = copy.deepcopy(D.DEFAULT_TONE)

    if raw is None:
        return result

    _overlay_strings(result["section_titles"], raw.get("section_titles"),
                     tuple(result["section_titles"]), "tone.yaml.section_titles", warnings)
    _overlay_strings(result["behavior_labels"], raw.get("behavior_labels"),
                     BEHAVIOR_KEYS, "tone.yaml.behavior_labels", warnings)
    _overlay_strings(result, raw, ("formatting",), "tone.yaml", warnings)

    emotion_raw = raw.get("emotion")
    if emotion_raw is not None:
        if not isinstance(emotion_raw, dict):
            warnings.append("tone.yaml.emotion: harus berupa mapping - memakai default.")
        else:
            emotion = result["emotion"]
            if "enabled" in emotion_raw:
                if isinstance(emotion_raw["enabled"], bool):
                    emotion["enabled"] = emotion_raw["enabled"]
                else:
                    warnings.append("tone.yaml.emotion.enabled: harus true/false - memakai default.")
            _overlay_strings(emotion, emotion_raw, ("title", "guard"), "tone.yaml.emotion", warnings)
            _overlay_strings(emotion["labels"], emotion_raw.get("labels"), tuple(emotion["labels"]),
                             "tone.yaml.emotion.labels", warnings)
            _overlay_scales(emotion["bands"], emotion_raw.get("bands"), tuple(emotion["bands"]),
                            "tone.yaml.emotion.bands", warnings)

    return result


def _validate_style(raw: dict, behavior_defaults: dict, label: str, warnings: list[str]) -> Optional[dict]:
    name = _str(raw.get("name"))
    if name is None:
        warnings.append(f"{label}: 'name' wajib string non-kosong - style dilewati.")
        return None

    profile_raw = raw.get("profile") or {}
    behavior_raw = raw.get("behavior") or {}
    text_raw = raw.get("persona_text") or {}

    for section, value in (("profile", profile_raw), ("behavior", behavior_raw), ("persona_text", text_raw)):
        if not isinstance(value, dict):
            warnings.append(f"{label}.{section}: harus berupa mapping - style dilewati.")
            return None

    profile = validate_profile_fields(profile_raw)
    profile.pop("active_preset", None)  # dipilih user/engine, bukan oleh style

    behavior = {**behavior_defaults, **validate_behavior_fields(behavior_raw)}

    persona_text: dict[str, str] = {}
    for key, value in text_raw.items():
        if isinstance(value, str):
            persona_text[str(key)] = value
        else:
            warnings.append(f"{label}.persona_text.{key}: harus string - diabaikan.")

    description = raw.get("description")

    return {
        "name": name,
        "description": description.strip() if isinstance(description, str) else "",
        "profile": profile,
        "behavior": behavior,
        "persona_text": persona_text,
    }


def _load_styles(styles_dir: Path, behavior_defaults: dict, warnings: list[str]) -> dict:
    styles = copy.deepcopy(D.DEFAULT_STYLES)

    if not styles_dir.is_dir():
        warnings.append("styles/: folder tidak ditemukan - memakai style bawaan.")
        return styles

    for path in sorted(styles_dir.glob("*.yaml")):
        style_id = path.stem.strip().lower()
        label = f"styles/{path.name}"

        if not _STYLE_ID_RE.match(style_id):
            warnings.append(f"{label}: nama file bukan id valid (a-z, 0-9, -, _) - dilewati.")
            continue

        raw = _read_yaml(path, label, warnings)
        if raw is None:
            continue

        style = _validate_style(raw, behavior_defaults, label, warnings)
        if style is not None:
            styles[style_id] = style

    return styles


# ------------------------------------------------------------------ public

def load_persona_config(base_dir: Optional[Path] = None) -> PersonaConfig:
    """Muat konfigurasi persona dari base_dir (default: core/persona/). Tidak pernah raise."""
    base = Path(base_dir) if base_dir else PERSONA_DIR
    warnings: list[str] = []

    identity = _load_identity(_read_yaml(base / "identity.yaml", "identity.yaml", warnings), warnings)
    behavior = _load_behavior(_read_yaml(base / "behavior.yaml", "behavior.yaml", warnings), warnings)
    tone = _load_tone(_read_yaml(base / "tone.yaml", "tone.yaml", warnings), warnings)
    styles = _load_styles(base / "styles", behavior["defaults"], warnings)

    for message in warnings:
        logger.warning("PERSONA CONFIG | %s", message)

    return PersonaConfig(
        identity=identity, behavior=behavior, tone=tone, styles=styles,
        warnings=tuple(warnings), source_dir=str(base),
    )


_config_singleton: Optional[PersonaConfig] = None
_config_lock = threading.Lock()


def get_persona_config(reload: bool = False) -> PersonaConfig:
    global _config_singleton

    with _config_lock:
        if _config_singleton is None or reload:
            _config_singleton = load_persona_config()
        return _config_singleton
