"""
core/capability/models.py — Capability Layer data contract (Sprint 2.7 / W1).

    Capability = WHAT AIRA can do   (this file)
    Tool       = HOW it is executed (core/orchestrator.py::AGENT_TOOL_MAP,
                 agents/*/registry.py - untouched by this module)

A Capability never holds a callable. ToolBinding only carries tool NAMES
(strings) that already exist in the orchestrator's tool map - the same
indirection AGENT_TOOL_MAP/AGENT_TOOL_SCHEMAS already use - so this module
never imports agents/* or core/orchestrator.py and stays free of circular
imports (mirrors core/dio/models.py + core/context/models.py: dataclasses
+ serialization only, no I/O, no reasoning).

Dataclasses here are intentionally "dumb": construction never raises for
bad input (same tolerant-parser philosophy as core/dio and core/plugins) -
CapabilityRegistry.register() is where invalid capabilities get rejected,
via validate_capability() below.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field, replace as _dataclasses_replace
from typing import Any, Optional

from core.capability.constants import (
    CONTEXT_CONVERSATION,
    DEFAULT_CATEGORY,
    PERMISSION_SAFE,
    STATE_REGISTERED,
    VALID_PERMISSIONS,
    VALID_STATES,
)


# ============================================================ UI METADATA

@dataclass
class CapabilityUIMetadata:
    """
    Presentation hints only - the frontend is never the source of truth
    for what a capability IS (id/permission/state), only for how it is
    drawn. Every field is optional; a capability with no UI metadata is
    still fully valid (e.g. backend-only/internal capabilities).
    """

    label: Optional[str] = None              # display name (falls back to Capability.name)
    icon: Optional[str] = None               # icon identifier (frontend resolves it)
    group: Optional[str] = None              # UI grouping (falls back to Capability.category)
    order: int = 0                           # sort hint within its group
    hidden: bool = False                     # registered/usable but not shown in pickers
    description_short: Optional[str] = None  # tooltip text (falls back to description)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "CapabilityUIMetadata":
        data = data if isinstance(data, dict) else {}
        known = {"label", "icon", "group", "order", "hidden", "description_short"}
        kwargs = {k: v for k, v in data.items() if k in known and v is not None}
        return cls(**kwargs)


# ============================================================ TOOL BINDING

@dataclass
class ToolBinding:
    """
    HOW a capability is executed, referenced by NAME only (never a
    callable) - resolution against the real tool map (e.g.
    core.orchestrator.AGENT_TOOL_MAP) happens at the integration boundary
    (core/capability/integration.py), not here. This keeps the Capability
    Layer importable and testable without agents/* or a running
    orchestrator.

    tool_names   : every tool this capability may invoke (order = preference).
    primary_tool : the tool name discovery treats as "the" tool for
                   availability checks; defaults to tool_names[0].
    requires_all : True = ALL tool_names must be available for this
                   capability to be usable; False (default) = ANY one is enough.
    """

    tool_names: list = field(default_factory=list)
    primary_tool: Optional[str] = None
    requires_all: bool = False

    def __post_init__(self) -> None:
        self.tool_names = [t for t in (self.tool_names or []) if isinstance(t, str) and t.strip()]

        if self.primary_tool is None and self.tool_names:
            self.primary_tool = self.tool_names[0]

    @property
    def is_empty(self) -> bool:
        return not self.tool_names

    def is_satisfied_by(self, available_tools) -> bool:
        """available_tools: any container supporting `in` (set/list/dict keys/sentinel)."""
        if self.is_empty:
            # No tool binding declared = not tool-gated (e.g. a pure UI/context capability).
            return True

        if self.requires_all:
            return all(name in available_tools for name in self.tool_names)

        return any(name in available_tools for name in self.tool_names)

    def to_dict(self) -> dict:
        return {
            "tool_names": list(self.tool_names),
            "primary_tool": self.primary_tool,
            "requires_all": self.requires_all,
        }

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "ToolBinding":
        data = data if isinstance(data, dict) else {}
        tool_names = data.get("tool_names")
        return cls(
            tool_names=list(tool_names) if isinstance(tool_names, list) else [],
            primary_tool=data.get("primary_tool"),
            requires_all=bool(data.get("requires_all", False)),
        )


def replace_capability(capability: "Capability", **changes: Any) -> "Capability":
    """dataclasses.replace() wrapper so callers don't need `dataclasses`
    themselves; re-runs __post_init__ (dataclasses.replace always does),
    so invariants (state/permission clamping) are re-checked."""
    return _dataclasses_replace(capability, **changes)


# ============================================================ CAPABILITY

@dataclass
class Capability:
    """
    Canonical capability representation. See core/capability/constants.py
    for the state/permission/context vocabularies.

    id                 : unique, stable identifier (e.g. "workspace.write_file").
    name               : human-readable name.
    description        : what this capability does, for humans and for LLM
                          tool-selection context (kept separate from any
                          single tool's own description).
    category           : grouping key (defaults to "general"); open-ended,
                          but core.capability.constants lists the context
                          categories Sprint 2.7 will add capabilities for.
    supported_context   : which context types (conversation/attachment/
                          selection/artifact/workspace/location/permission/
                          ...) this capability can operate under.
    input_schema       : JSON-schema-like dict describing expected input
                          (mirrors the "parameters" shape already used by
                          AGENT_TOOL_SCHEMAS, so existing tool schemas can
                          be wrapped directly - see integration.py).
    output_types       : free-form list of what this capability can return
                          (e.g. "text", "file", "image", "structured_data",
                          "interaction_schema").
    permission         : one of core.capability.constants' permission values.
    ui                 : CapabilityUIMetadata.
    tool_binding       : ToolBinding (may be empty for non-tool capabilities).
    state              : current lifecycle state. Owned by the registry/
                          discovery layer, not hand-authored in most cases -
                          register() always forces new capabilities to
                          STATE_REGISTERED regardless of what's passed in.
    metadata           : free-form extension bag (author, version, plugin
                          origin, danger flags, ...). Never interpreted by
                          this module.
    """

    id: str
    name: str
    description: str = ""
    category: str = DEFAULT_CATEGORY
    supported_context: list = field(default_factory=lambda: [CONTEXT_CONVERSATION])
    input_schema: dict = field(default_factory=dict)
    output_types: list = field(default_factory=list)
    permission: str = PERMISSION_SAFE
    ui: CapabilityUIMetadata = field(default_factory=CapabilityUIMetadata)
    tool_binding: ToolBinding = field(default_factory=ToolBinding)
    state: str = STATE_REGISTERED
    metadata: dict = field(default_factory=dict)
    registered_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        self.supported_context = [
            c for c in (self.supported_context or []) if isinstance(c, str) and c.strip()
        ] or [CONTEXT_CONVERSATION]

        self.output_types = [o for o in (self.output_types or []) if isinstance(o, str) and o.strip()]

        if self.permission not in VALID_PERMISSIONS:
            self.permission = PERMISSION_SAFE

        if self.state not in VALID_STATES:
            self.state = STATE_REGISTERED

        if not isinstance(self.input_schema, dict):
            self.input_schema = {}

        if not isinstance(self.metadata, dict):
            self.metadata = {}

        if isinstance(self.ui, dict):
            self.ui = CapabilityUIMetadata.from_dict(self.ui)
        elif not isinstance(self.ui, CapabilityUIMetadata):
            self.ui = CapabilityUIMetadata()

        if isinstance(self.tool_binding, dict):
            self.tool_binding = ToolBinding.from_dict(self.tool_binding)
        elif not isinstance(self.tool_binding, ToolBinding):
            self.tool_binding = ToolBinding()

    # ------------------------------------------------------------ derived

    def supports_context(self, context_types) -> bool:
        """True if this capability applies to ANY of the given context
        types. context_types: iterable of strings, or a single string."""
        if isinstance(context_types, str):
            context_types = [context_types]
        return any(c in self.supported_context for c in context_types)

    def with_state(self, new_state: str) -> "Capability":
        """Return a NEW Capability with state replaced (registry callers use
        this rather than mutate in place, so snapshots stay consistent)."""
        if new_state not in VALID_STATES:
            raise ValueError(f"State '{new_state}' tidak dikenal. Pilihan: {sorted(VALID_STATES)}.")

        return replace_capability(self, state=new_state, updated_at=time.time())

    # ------------------------------------------------------------ serialize

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "supported_context": list(self.supported_context),
            "input_schema": dict(self.input_schema),
            "output_types": list(self.output_types),
            "permission": self.permission,
            "ui": self.ui.to_dict(),
            "tool_binding": self.tool_binding.to_dict(),
            "state": self.state,
            "metadata": dict(self.metadata),
            "registered_at": self.registered_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Capability":
        data = data if isinstance(data, dict) else {}

        return cls(
            id=str(data.get("id") or ""),
            name=str(data.get("name") or ""),
            description=str(data.get("description") or ""),
            category=str(data.get("category") or DEFAULT_CATEGORY),
            supported_context=list(data.get("supported_context") or []),
            input_schema=dict(data.get("input_schema") or {}),
            output_types=list(data.get("output_types") or []),
            permission=str(data.get("permission") or PERMISSION_SAFE),
            ui=data.get("ui") or {},
            tool_binding=data.get("tool_binding") or {},
            state=str(data.get("state") or STATE_REGISTERED),
            metadata=dict(data.get("metadata") or {}),
            registered_at=float(data.get("registered_at") or time.time()),
            updated_at=float(data.get("updated_at") or time.time()),
        )


# ============================================================ VALIDATION

@dataclass
class ValidationIssue:
    field: str
    message: str

    def to_dict(self) -> dict:
        return {"field": self.field, "message": self.message}


@dataclass
class ValidationResult:
    is_valid: bool
    issues: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"is_valid": self.is_valid, "issues": [i.to_dict() for i in self.issues]}


_ID_MIN_LEN = 2
_ID_MAX_LEN = 128


def validate_capability(capability: Capability) -> ValidationResult:
    """Structural validation, same split as core/dio (models build tolerant
    objects; a separate validator flags what's wrong) and core/plugins
    (manifest.py builds, validator.py checks). Never raises."""
    issues: list = []

    try:
        if not isinstance(capability, Capability):
            return ValidationResult(False, [ValidationIssue("capability", "harus berupa Capability.")])

        cap_id = capability.id
        if not isinstance(cap_id, str) or not cap_id.strip():
            issues.append(ValidationIssue("id", "id wajib diisi (tidak boleh kosong)."))
        elif not (_ID_MIN_LEN <= len(cap_id) <= _ID_MAX_LEN):
            issues.append(ValidationIssue("id", f"id harus {_ID_MIN_LEN}-{_ID_MAX_LEN} karakter."))
        elif any(ch.isspace() for ch in cap_id):
            issues.append(ValidationIssue("id", "id tidak boleh mengandung spasi/whitespace."))

        if not isinstance(capability.name, str) or not capability.name.strip():
            issues.append(ValidationIssue("name", "name wajib diisi (tidak boleh kosong)."))

        if capability.permission not in VALID_PERMISSIONS:
            issues.append(ValidationIssue(
                "permission", f"permission '{capability.permission}' tidak dikenal.",
            ))

        if capability.state not in VALID_STATES:
            issues.append(ValidationIssue("state", f"state '{capability.state}' tidak dikenal."))

        if not capability.supported_context:
            issues.append(ValidationIssue("supported_context", "supported_context tidak boleh kosong."))

        if capability.tool_binding.requires_all and not capability.tool_binding.tool_names:
            issues.append(ValidationIssue(
                "tool_binding", "requires_all=True tapi tool_names kosong.",
            ))

    except Exception as exc:  # validator itself must never crash the caller
        issues.append(ValidationIssue("capability", f"Validasi gagal tak terduga: {type(exc).__name__}."))

    return ValidationResult(is_valid=len(issues) == 0, issues=issues)
