from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Optional


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _clean(data: dict) -> dict:
    return {k: v for k, v in data.items() if v is not None}


@dataclass
class ChoiceOption:
    value: str
    label: str

    def to_dict(self) -> dict:
        return _clean(asdict(self))


@dataclass
class MissingField:
    key: str
    data_type: str = "string"
    label: Optional[str] = None
    required: bool = True
    options: list[ChoiceOption] = field(default_factory=list)
    placeholder: Optional[str] = None
    helper_text: Optional[str] = None
    default: Any = None
    min: Optional[float] = None
    max: Optional[float] = None
    pattern: Optional[str] = None

    def to_dict(self) -> dict:
        data = asdict(self)
        data["options"] = [c.to_dict() for c in self.options]
        return _clean(data)


@dataclass
class InteractionPlan:
    intent: str
    confidence: float = 0.0
    known_data: dict[str, Any] = field(default_factory=dict)
    missing_data: list[MissingField] = field(default_factory=list)
    suggested_mode: Optional[str] = None
    priority: str = "normal"
    danger: bool = False
    needs_review: bool = False
    choices: list[ChoiceOption] = field(default_factory=list)
    plan_id: str = field(default_factory=lambda: _new_id("plan"))
    source_agent: Optional[str] = None
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["missing_data"] = [m.to_dict() for m in self.missing_data]
        data["choices"] = [c.to_dict() for c in self.choices]
        return _clean(data)


@dataclass
class Field:
    id: str
    type: str
    label: Optional[str] = None
    required: bool = False
    default: Any = None
    placeholder: Optional[str] = None
    helper_text: Optional[str] = None
    visible_if: Optional[dict] = None
    options: list[ChoiceOption] = field(default_factory=list)
    min: Optional[float] = None
    max: Optional[float] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    pattern: Optional[str] = None
    step: Optional[float] = None
    span: Optional[str] = None
    columns: Optional[list[dict]] = None
    rows: Optional[list[dict]] = None
    selectable: Optional[bool] = None
    variant: Optional[str] = None
    text: Optional[str] = None
    style: Optional[str] = None
    action_id: Optional[str] = None
    disabled: bool = False

    def to_dict(self) -> dict:
        data = asdict(self)
        data["options"] = [o.to_dict() for o in self.options]
        return _clean(data)


@dataclass
class Section:
    id: str
    title: Optional[str] = None
    description: Optional[str] = None
    columns: int = 1
    fields: list[Field] = field(default_factory=list)
    visible_if: Optional[dict] = None

    def to_dict(self) -> dict:
        return _clean({
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "columns": self.columns,
            "fields": [f.to_dict() for f in self.fields],
            "visible_if": self.visible_if,
        })


@dataclass
class Action:
    id: str
    label: str
    style: str = "secondary"
    disabled: bool = False

    def to_dict(self) -> dict:
        return _clean(asdict(self))


@dataclass
class InteractionSchema:
    id: str
    mode: str
    title: Optional[str] = None
    description: Optional[str] = None
    sections: list[Section] = field(default_factory=list)
    actions: list[Action] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    version: str = "1.0"
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return _clean({
            "id": self.id,
            "version": self.version,
            "title": self.title,
            "description": self.description,
            "mode": self.mode,
            "sections": [s.to_dict() for s in self.sections],
            "actions": [a.to_dict() for a in self.actions],
            "metadata": self.metadata,
            "created_at": self.created_at,
        })


@dataclass
class ValidationIssue:
    code: str
    message: str
    section_id: Optional[str] = None
    field_id: Optional[str] = None

    def to_dict(self) -> dict:
        return _clean(asdict(self))


@dataclass
class ValidationResult:
    is_valid: bool
    issues: list[ValidationIssue] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"is_valid": self.is_valid, "issues": [i.to_dict() for i in self.issues]}