"""
core/capability/ — Capability Layer (Sprint 2.7 / Worker 1).

    Capability = WHAT AIRA can do
    Tool       = HOW it is executed (core/orchestrator.py, agents/*/registry.py)

Public API:
    from core.capability import (
        Capability, CapabilityUIMetadata, ToolBinding,
        CapabilityRegistry, get_capability_registry,
        CapabilityAlreadyRegisteredError, CapabilityValidationError,
        CapabilityDiscovery, get_capability_discovery,
        DiscoverySettings, DiscoveredCapability,
        validate_capability, ValidationResult, ValidationIssue,
        capability_to_frontend_dict, discovered_to_frontend_dict,
        capabilities_to_frontend_list,
    )

This package implements ONLY the foundation contract: representation,
registry, discovery, and frontend-safe serialization. It does not
implement Attachment/Selection/Artifact/Workspace/Location/Permission
capabilities themselves - those are separate Sprint 2.7 work packages
that call register() with their own Capability instances. The bridge to
the EXISTING tool/agent architecture (core/orchestrator.py) lives in
core/capability/integration.py and is intentionally NOT imported here,
so this package stays importable standalone (no agents/* dependency).
"""

from core.capability.constants import (
    CONTEXT_ARTIFACT,
    CONTEXT_ATTACHMENT,
    CONTEXT_CONVERSATION,
    CONTEXT_LOCATION,
    CONTEXT_PERMISSION,
    CONTEXT_SELECTION,
    CONTEXT_WORKSPACE,
    KNOWN_CONTEXT_TYPES,
    PERMISSION_CONFIRMATION_REQUIRED,
    PERMISSION_RESTRICTED,
    PERMISSION_SAFE,
    PERMISSION_UNAVAILABLE,
    STATE_AVAILABLE,
    STATE_DISABLED,
    STATE_ENABLED,
    STATE_REGISTERED,
    STATE_REQUIRES_CONFIRMATION,
    STATE_UNAVAILABLE,
    VALID_PERMISSIONS,
    VALID_STATES,
)
from core.capability.models import (
    Capability,
    CapabilityUIMetadata,
    ToolBinding,
    ValidationIssue,
    ValidationResult,
    validate_capability,
)
from core.capability.registry import (
    CapabilityAlreadyRegisteredError,
    CapabilityRegistry,
    CapabilityValidationError,
    get_capability_registry,
)
from core.capability.discovery import (
    CapabilityDiscovery,
    DiscoveredCapability,
    DiscoverySettings,
    get_capability_discovery,
)
from core.capability.frontend import (
    capabilities_to_frontend_list,
    capability_to_frontend_dict,
    discovered_to_frontend_dict,
)

__all__ = [
    # constants
    "CONTEXT_CONVERSATION", "CONTEXT_ATTACHMENT", "CONTEXT_SELECTION",
    "CONTEXT_ARTIFACT", "CONTEXT_WORKSPACE", "CONTEXT_LOCATION",
    "CONTEXT_PERMISSION", "KNOWN_CONTEXT_TYPES",
    "PERMISSION_SAFE", "PERMISSION_CONFIRMATION_REQUIRED",
    "PERMISSION_RESTRICTED", "PERMISSION_UNAVAILABLE", "VALID_PERMISSIONS",
    "STATE_REGISTERED", "STATE_AVAILABLE", "STATE_ENABLED", "STATE_DISABLED",
    "STATE_REQUIRES_CONFIRMATION", "STATE_UNAVAILABLE", "VALID_STATES",
    # models
    "Capability", "CapabilityUIMetadata", "ToolBinding",
    "validate_capability", "ValidationResult", "ValidationIssue",
    # registry
    "CapabilityRegistry", "get_capability_registry",
    "CapabilityAlreadyRegisteredError", "CapabilityValidationError",
    # discovery
    "CapabilityDiscovery", "get_capability_discovery",
    "DiscoverySettings", "DiscoveredCapability",
    # frontend
    "capability_to_frontend_dict", "discovered_to_frontend_dict",
    "capabilities_to_frontend_list",
]
