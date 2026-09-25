"""
core/workspace_links/ - Workspace Integration (Sprint 2.7 / Wave 2 / W6).

Connects the EXISTING Workspace (core/filesystem) with Conversation
(core/chat_sessions), Attachment (core/attachments), and Artifact
(core/artifacts) - see core/workspace_links/service.py for the four flows.

Public API:
    from core.workspace_links import (
        WorkspaceLink, LinkKind, LinkResult,
        WorkspaceLinkStore, get_workspace_link_store,
        WorkspaceIntegrationService, get_workspace_integration_service,
    )

This package reuses the EXISTING core.filesystem for every byte written
and read - it never creates a second filesystem, never duplicates a file,
and never reimplements sandboxing/permissions (those stay owned by
core/filesystem/workspace.py and core/filesystem/permissions.py).
"""

from core.workspace_links.models import LinkKind, LinkResult, WorkspaceLink
from core.workspace_links.store import WorkspaceLinkStore, get_workspace_link_store
from core.workspace_links.service import (
    WorkspaceIntegrationService,
    get_workspace_integration_service,
)

__all__ = [
    "WorkspaceLink", "LinkKind", "LinkResult",
    "WorkspaceLinkStore", "get_workspace_link_store",
    "WorkspaceIntegrationService", "get_workspace_integration_service",
]