"""
core/persona/validator.py — validasi input Persona Engine sebelum
disimpan ke database/persona.db.
"""

from typing import Any

BEHAVIOR_KEYS = (
    "professionalism", "friendliness", "playfulness",
    "verbosity", "empathy", "teaching_depth",
)

PROFILE_KEYS = (
    "assistant_name", "user_name", "language",
    "timezone", "greeting", "active_preset",
)


def clamp_behavior_value(value: Any) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        v = 50
    return max(0, min(100, v))


def validate_behavior_fields(fields: dict) -> dict:
    return {
        key: clamp_behavior_value(value)
        for key, value in fields.items()
        if key in BEHAVIOR_KEYS and value is not None
    }


def validate_profile_fields(fields: dict) -> dict:
    cleaned: dict = {}

    for key, value in fields.items():
        if key not in PROFILE_KEYS:
            continue

        if value is None:
            # user_name boleh dikosongkan eksplisit, field lain diabaikan
            # kalau None supaya tidak menimpa nilai valid jadi NULL.
            if key == "user_name":
                cleaned[key] = None
            continue

        text = str(value).strip()

        if key == "assistant_name" and not text:
            continue

        cleaned[key] = text[:200]

    return cleaned