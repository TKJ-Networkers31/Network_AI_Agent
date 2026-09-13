"""
core/persona/types.py — bentuk data Persona Engine (Phase 1.3).
Dataclass murni, tidak menyentuh SQLite - itu tanggung jawab engine.py.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class PersonaProfile:
    assistant_name: str = "AIRA"
    user_name: Optional[str] = None
    language: str = "id"
    timezone: str = "Asia/Jakarta"
    greeting: str = ""
    active_preset: str = "akane"


@dataclass
class PersonaBehavior:
    professionalism: int = 86
    friendliness: int = 84
    playfulness: int = 42
    verbosity: int = 78
    empathy: int = 74
    teaching_depth: int = 96

    def as_dict(self) -> dict:
        return {
            "professionalism": self.professionalism,
            "friendliness": self.friendliness,
            "playfulness": self.playfulness,
            "verbosity": self.verbosity,
            "empathy": self.empathy,
            "teaching_depth": self.teaching_depth,
        }


@dataclass
class PersonaPreset:
    id: str
    name: str
    description: str
    is_builtin: bool
    profile: dict
    behavior: dict
    persona_text: dict