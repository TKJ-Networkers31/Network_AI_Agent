"""
core/attachments/ - Universal Attachment (Sprint 2.7 / Wave 1 / Worker 2).

    Attachment = METADATA + a REFERENCE to a file that already exists in
                 storage (user upload, workspace file, generated artifact,
                 or external file). Binary content is never carried by an
                 Attachment nor injected into Context - only metadata/
                 reference (see core/attachments/context.py).

Public API:
    from core.attachments import (
        Attachment, AttachmentSource, AttachmentStatus, AttachmentResult,
        ValidationIssue, ValidationResult,
        validate_for_create,
        AttachmentStore, get_attachment_store,
        AttachmentEngine, get_attachment_engine,
        attachment_to_context_dict, attachments_context_section,
    )

This package reuses the EXISTING core.filesystem (Workspace/HAL) for all
storage - it does not create a second filesystem or storage abstraction.
It reuses the EXISTING Event Bus (core.events) for notifications. It does
not create a second Context Builder or Capability Registry: the small
context-summarization helper in core/attachments/context.py produces plain
data meant to be handed to the EXISTING core.context.ContextBuilder by
whichever caller wires it in (Brain/Planner), not a parallel prompt system.
"""

from core.attachments.constants import (
    ALLOWED_EXTENSIONS,
    ALLOWED_MIME_TYPES,
    BLOCKED_EXTENSIONS,
    DEFAULT_WORKSPACE_SUBDIR,
    MAX_ATTACHMENT_BYTES,
)
from core.attachments.models import (
    Attachment,
    AttachmentResult,
    AttachmentSource,
    AttachmentStatus,
    ValidationIssue,
    ValidationResult,
    VALID_SOURCES,
    VALID_STATUSES,
)
from core.attachments.validator import validate_for_create
from core.attachments.store import AttachmentStore, get_attachment_store
from core.attachments.engine import (
    AttachmentEngine,
    get_attachment_engine,
)
from core.attachments.context import (
    attachment_to_context_dict,
    attachments_context_section,
)

__all__ = [
    # constants
    "ALLOWED_EXTENSIONS", "ALLOWED_MIME_TYPES", "BLOCKED_EXTENSIONS",
    "DEFAULT_WORKSPACE_SUBDIR", "MAX_ATTACHMENT_BYTES",
    # models
    "Attachment", "AttachmentResult", "AttachmentSource", "AttachmentStatus",
    "ValidationIssue", "ValidationResult", "VALID_SOURCES", "VALID_STATUSES",
    # validator
    "validate_for_create",
    # store
    "AttachmentStore", "get_attachment_store",
    # engine
    "AttachmentEngine", "get_attachment_engine",
    # context
    "attachment_to_context_dict", "attachments_context_section",
]
