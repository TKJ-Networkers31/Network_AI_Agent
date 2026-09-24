"""
core/external_context/capability_bridge.py — External Context <-> W1
Capability Layer bridge (Sprint 2.7 / W7).

This is the ONLY place External Context talks to the Capability Layer,
and it reuses the EXISTING core.capability.get_capability_registry()
singleton - it does not create a second registry, mirroring exactly how
core/capability/integration.py bridges AGENT_TOOL_SCHEMAS into the same
registry for ordinary tools.

One Capability is registered per capability name the provider declares
(see core.external_context.constants.VALID_CAPABILITIES), each tagged
supported_context=[CONTEXT_LOCATION] so discovery can filter by "is a
location-context turn". tool_binding is left EMPTY on purpose: an
External Context provider is not itself an orchestrator tool
(core.orchestrator.AGENT_TOOL_MAP) - if/when an agent tool wraps
provider.execute(...) for REI to call, that tool's own schema goes
through core/capability/integration.py::register_tool_capabilities like
any other tool. This bridge only makes the PROVIDER's existence/capacity
discoverable, it does not wire execution into the conversation engine
(see GOAL: "Do not hardcode Google Maps into the conversation/agent
engine").
"""

from __future__ import annotations

import logging
from typing import Optional

from core.capability import (
    Capability,
    CapabilityRegistry,
    CapabilityUIMetadata,
    PERMISSION_SAFE,
    get_capability_registry,
)
from core.capability.constants import CONTEXT_LOCATION
from core.capability.registry import CapabilityAlreadyRegisteredError
from core.external_context.constants import CAPABILITY_LABELS
from core.external_context.provider import ExternalContextProvider

logger = logging.getLogger("aira.external_context.capability_bridge")

CAPABILITY_ID_PREFIX = "external_context."


def capability_id_for(provider_name: str, capability: str) -> str:
    """e.g. ('google_maps', 'location.search') -> 'external_context.google_maps.location.search'."""
    return f"{CAPABILITY_ID_PREFIX}{provider_name}.{capability}"


def capability_from_provider(provider: ExternalContextProvider, capability: str) -> Capability:
    """One provider capability name -> one W1 Capability. Pure - does not
    touch the registry (mirrors
    core/capability/integration.py::capability_from_tool_schema)."""
    identity = provider.identity

    return Capability(
        id=capability_id_for(identity.name, capability),
        name=f"{identity.display_name}: {CAPABILITY_LABELS.get(capability, capability)}",
        description=CAPABILITY_LABELS.get(capability, capability),
        category="external_context",
        supported_context=[CONTEXT_LOCATION],
        input_schema={},
        output_types=["structured_data"],
        permission=PERMISSION_SAFE,
        ui=CapabilityUIMetadata(group="External Context", label=identity.display_name),
        metadata={
            "origin": "external_context",
            "provider": identity.name,
            "provider_display_name": identity.display_name,
            "provider_version": identity.version,
            "capability": capability,
        },
    )


def register_provider_capabilities(
    provider: ExternalContextProvider,
    *,
    registry: Optional[CapabilityRegistry] = None,
    overwrite: bool = False,
) -> dict:
    """
    Register one Capability per capability the provider declares
    (provider.capabilities). Never raises for a single bad entry -
    failures are collected and returned, same defensive style as
    core/capability/integration.py::register_tool_capabilities, so one
    provider's misbehaving capability list can't block another provider
    (or a plain tool) from registering.
    """
    reg = registry or get_capability_registry()

    registered: list = []
    skipped: list = []
    errors: list = []

    for capability in provider.capabilities.capabilities:
        try:
            cap = capability_from_provider(provider, capability)
            reg.register(cap, overwrite=overwrite)
            registered.append(cap.id)
        except CapabilityAlreadyRegisteredError:
            skipped.append(capability_id_for(provider.identity.name, capability))
        except Exception as exc:
            logger.warning(
                "EXTERNAL CONTEXT CAPABILITY BRIDGE | gagal register '%s': %s",
                capability, exc,
            )
            errors.append({"capability": capability, "error": str(exc)})

    logger.info(
        "EXTERNAL CONTEXT CAPABILITY BRIDGE | provider=%s registered=%d skipped=%d errors=%d",
        provider.identity.name, len(registered), len(skipped), len(errors),
    )

    return {"registered": registered, "skipped": skipped, "errors": errors}


def unregister_provider_capabilities(
    provider: ExternalContextProvider,
    *,
    registry: Optional[CapabilityRegistry] = None,
) -> int:
    """Remove every Capability previously registered for this provider.
    Returns the number actually removed."""
    reg = registry or get_capability_registry()
    removed = 0

    for capability in provider.capabilities.capabilities:
        if reg.unregister(capability_id_for(provider.identity.name, capability)):
            removed += 1

    return removed
