"""
core/capability/discovery.py — CapabilityDiscovery (Sprint 2.7 / W1).

Turns the static registry (what's REGISTERED) into "what's usable RIGHT
NOW", given:

    - context          : which context types are present this turn
                          (conversation/attachment/selection/artifact/
                          workspace/location/permission/...), e.g.
                          {"conversation"} for a plain chat turn.
    - available_tools   : tool names currently resolvable (normally
                          core.orchestrator.AGENT_TOOL_MAP.keys(), injected
                          by the caller - this module never imports
                          orchestrator or agents/*).
    - settings          : DiscoverySettings (disabled ids, allowed
                          permission levels, confirmations already granted
                          this turn/session).

Discovery NEVER mutates the registry's stored state (that stays whatever
CapabilityRegistry.set_state() last set it to) - it computes an EFFECTIVE
state per capability for THIS discovery call, returned alongside the
capability as a DiscoveredCapability. "Available in general" and
"available in THIS turn's context" are different questions, and the
registry is shared/global while discovery is per-turn.

Effective-state resolution (see core/capability/constants.py for values):

    registry state DISABLED or id in settings.disabled_ids  -> DISABLED
    permission UNAVAILABLE, or not in settings.allowed_permissions,
        or context doesn't match, or tool_binding unsatisfied            -> UNAVAILABLE
    resolve_enablement=False (structural check only)                    -> AVAILABLE
    permission CONFIRMATION_REQUIRED and id not in confirmed_ids         -> REQUIRES_CONFIRMATION
    otherwise                                                            -> ENABLED
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

from core.capability.constants import (
    PERMISSION_CONFIRMATION_REQUIRED,
    PERMISSION_RESTRICTED,
    PERMISSION_SAFE,
    PERMISSION_UNAVAILABLE,
    STATE_AVAILABLE,
    STATE_DISABLED,
    STATE_ENABLED,
    STATE_REQUIRES_CONFIRMATION,
    STATE_UNAVAILABLE,
)
from core.capability.models import Capability
from core.capability.registry import CapabilityRegistry, get_capability_registry


class _AlwaysContains:
    """Sentinel used when available_tools=None: tool_binding checks should
    pass unconditionally rather than fail because nothing was provided."""

    def __contains__(self, item: object) -> bool:
        return True


_ALWAYS = _AlwaysContains()


@dataclass
class DiscoverySettings:
    """
    What varies per caller/turn/user, injected rather than read from a
    database directly (Dependency Injection, same approach as
    core/context/builder.py::ContextBuilder) so discovery stays testable
    and doesn't hardcode where settings come from.

    disabled_ids        : capability ids explicitly turned off (e.g. by
                           user preference / org policy), in addition to
                           whatever the registry's own state says.
    allowed_permissions  : permission levels usable in this call; default
                           allows everything except UNAVAILABLE (which is
                           never usable by definition).
    confirmed_ids        : capability ids where confirmation_required has
                           already been satisfied for this call (so they
                           resolve to ENABLED, not REQUIRES_CONFIRMATION).
    """

    disabled_ids: frozenset = field(default_factory=frozenset)
    allowed_permissions: frozenset = field(default_factory=lambda: frozenset({
        PERMISSION_SAFE, PERMISSION_CONFIRMATION_REQUIRED, PERMISSION_RESTRICTED,
    }))
    confirmed_ids: frozenset = field(default_factory=frozenset)


@dataclass
class DiscoveredCapability:
    capability: Capability
    effective_state: str
    reasons: list = field(default_factory=list)

    @property
    def is_usable(self) -> bool:
        return self.effective_state == STATE_ENABLED

    def to_dict(self) -> dict:
        data = self.capability.to_dict()
        data["effective_state"] = self.effective_state
        data["reasons"] = list(self.reasons)
        return data


class CapabilityDiscovery:

    def __init__(self, registry: Optional[CapabilityRegistry] = None):
        self._registry = registry

    @property
    def registry(self) -> CapabilityRegistry:
        return self._registry or get_capability_registry()

    def _resolve_effective_state(
        self,
        capability: Capability,
        *,
        context: frozenset,
        available_tools,
        settings: DiscoverySettings,
        resolve_enablement: bool,
    ) -> "tuple":
        reasons: list = []

        if capability.state == STATE_DISABLED or capability.id in settings.disabled_ids:
            reasons.append("disabled")
            return STATE_DISABLED, reasons

        if capability.permission == PERMISSION_UNAVAILABLE:
            reasons.append("permission_unavailable")
            return STATE_UNAVAILABLE, reasons

        if capability.permission not in settings.allowed_permissions:
            reasons.append(f"permission_not_allowed:{capability.permission}")
            return STATE_UNAVAILABLE, reasons

        if context and not capability.supports_context(context):
            reasons.append("context_mismatch")
            return STATE_UNAVAILABLE, reasons

        if not capability.tool_binding.is_satisfied_by(available_tools):
            reasons.append("tool_unavailable")
            return STATE_UNAVAILABLE, reasons

        # Structural prerequisites are met. Callers that only want "what
        # exists here" (not "what can I invoke this instant") stop here.
        if not resolve_enablement:
            reasons.append("structurally_available")
            return STATE_AVAILABLE, reasons

        if capability.permission == PERMISSION_CONFIRMATION_REQUIRED and capability.id not in settings.confirmed_ids:
            reasons.append("confirmation_required")
            return STATE_REQUIRES_CONFIRMATION, reasons

        reasons.append("ok")
        return STATE_ENABLED, reasons

    def discover(
        self,
        *,
        context: Optional[Iterable] = None,
        available_tools: Optional[Iterable] = None,
        settings: Optional[DiscoverySettings] = None,
        category: Optional[str] = None,
        resolve_enablement: bool = True,
        include_unavailable: bool = False,
    ) -> list:
        """
        Compute effective state for every REGISTERED capability (optionally
        pre-filtered by category, same filter registry.list() supports).

        - context=None            -> context is not checked (all capabilities pass).
        - available_tools=None    -> tool_binding is not checked (all capabilities pass).
        - resolve_enablement=False -> stop at structural AVAILABLE, ignore
          settings.confirmed_ids (useful for "what exists here" listings).
        - include_unavailable=False -> UNAVAILABLE/DISABLED capabilities are
          dropped from the result; pass True for introspection/debugging.
        """
        context_set = frozenset(context) if context is not None else frozenset()
        tools = set(available_tools) if available_tools is not None else _ALWAYS
        settings = settings or DiscoverySettings()

        candidates = self.registry.list(category=category)
        results: list = []

        for capability in candidates:
            effective_state, reasons = self._resolve_effective_state(
                capability,
                context=context_set,
                available_tools=tools,
                settings=settings,
                resolve_enablement=resolve_enablement,
            )

            if not include_unavailable and effective_state in (STATE_UNAVAILABLE, STATE_DISABLED):
                continue

            results.append(DiscoveredCapability(
                capability=capability, effective_state=effective_state, reasons=reasons,
            ))

        return results

    def is_usable(
        self,
        capability_id: str,
        *,
        context: Optional[Iterable] = None,
        available_tools: Optional[Iterable] = None,
        settings: Optional[DiscoverySettings] = None,
    ) -> bool:
        """True only if the capability resolves all the way to ENABLED."""
        capability = self.registry.get(capability_id)
        if capability is None:
            return False

        context_set = frozenset(context) if context is not None else frozenset()
        tools = set(available_tools) if available_tools is not None else _ALWAYS
        settings = settings or DiscoverySettings()

        effective_state, _ = self._resolve_effective_state(
            capability, context=context_set, available_tools=tools,
            settings=settings, resolve_enablement=True,
        )

        return effective_state == STATE_ENABLED


_discovery_singleton: Optional[CapabilityDiscovery] = None


def get_capability_discovery() -> CapabilityDiscovery:
    global _discovery_singleton

    if _discovery_singleton is None:
        _discovery_singleton = CapabilityDiscovery()

    return _discovery_singleton
