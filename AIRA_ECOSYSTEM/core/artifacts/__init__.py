"""
core/artifacts/ - Artifact & Document Engine (Sprint 2.7 / W5).

    LLM -> structured spec -> deterministic generator -> binary artifact

Public API:
    from core.artifacts import (
        ArtifactEngine, get_artifact_engine,
        Artifact, ArtifactResult, ArtifactType, ArtifactStatus,
        DocumentSpec, DocumentBlock, heading, paragraph, bullet_list, table_block,
        SpreadsheetSpec, WorksheetSpec, CsvSpec,
        PresentationSpec, SlideSection,
        validate_for_type, ValidationResult, ValidationIssue,
        ArtifactStore, get_artifact_store,
    )

This package does not implement Attachment, Selection, Unified Context,
Workspace UI, Maps, Dynamic UI, Calendar, Scheduler, Voice, or vision - it
only turns a structured spec into a file and registers it. Storage/sandbox
comes from the EXISTING core.filesystem (via Dependency Injection in
core/artifacts/engine.py); no second storage system is created here.
"""

from core.artifacts.models import (
    Artifact, ArtifactResult, ArtifactStatus, ArtifactType,
    DOCUMENT_TYPES, EXTENSIONS, MIME_TYPES, PRESENTATION_TYPES, SPREADSHEET_TYPES,
)
from core.artifacts.specs import (
    CsvSpec, DocumentBlock, DocumentSpec, PresentationSpec, SlideSection,
    SpreadsheetSpec, WorksheetSpec, VALID_COLUMN_FORMATS,
    heading, paragraph, bullet_list, table_block,
)
from core.artifacts.validator import (
    ValidationIssue, ValidationResult,
    validate_csv_spec, validate_document_spec, validate_for_type,
    validate_presentation_spec, validate_spreadsheet_spec,
)
from core.artifacts.store import ArtifactStore, get_artifact_store
from core.artifacts.engine import ArtifactEngine, get_artifact_engine
from core.artifacts.generators import GenerationError

__all__ = [
    "Artifact", "ArtifactResult", "ArtifactStatus", "ArtifactType",
    "DOCUMENT_TYPES", "SPREADSHEET_TYPES", "PRESENTATION_TYPES", "MIME_TYPES", "EXTENSIONS",
    "CsvSpec", "DocumentBlock", "DocumentSpec", "PresentationSpec", "SlideSection",
    "SpreadsheetSpec", "WorksheetSpec", "VALID_COLUMN_FORMATS",
    "heading", "paragraph", "bullet_list", "table_block",
    "ValidationIssue", "ValidationResult",
    "validate_csv_spec", "validate_document_spec", "validate_for_type",
    "validate_presentation_spec", "validate_spreadsheet_spec",
    "ArtifactStore", "get_artifact_store",
    "ArtifactEngine", "get_artifact_engine",
    "GenerationError",
]