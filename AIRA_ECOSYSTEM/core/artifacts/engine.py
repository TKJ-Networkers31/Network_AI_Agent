"""
core/artifacts/engine.py - ArtifactEngine (Sprint 2.7 / W5).

    LLM -> structured spec (core/artifacts/specs.py)
        -> ArtifactEngine.create_*()
        -> validate (core/artifacts/validator.py)
        -> generate (core/artifacts/generators/*, deterministic)
        -> store bytes via the EXISTING Workspace (core/filesystem)
        -> register metadata (core/artifacts/store.py)
        -> ArtifactResult (JSON-safe)

The LLM never produces a binary artifact directly - only a JSON-safe spec.
This module is the only place that turns a spec into a real file.

Storage: this module does NOT invent a new storage system. Path resolution
and sandboxing are delegated to core.filesystem.WorkspaceManager.resolve()
(the SAME sandbox FSE/HAL already enforce) via a resolver callback, default-
injected lazily so importing this module never touches disk (same
Dependency-Injection pattern as core/context/builder.py::ContextBuilder and
core/selection/builder.py::SelectionBuilder). Bytes are written directly at
the resolved path because core.filesystem.FileOperations.write_text() is
text-only; binary artifacts (.docx/.pdf/.xlsx/.pptx) can't go through it.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Callable, Optional

from core.artifacts.generators import (
    GenerationError, generate_csv, generate_docx, generate_markdown,
    generate_pdf, generate_pptx, generate_txt, generate_xlsx,
)
from core.artifacts.models import (
    Artifact, ArtifactResult, ArtifactStatus, ArtifactType,
    EXTENSIONS, MIME_TYPES,
)
from core.artifacts.specs import CsvSpec, DocumentSpec, PresentationSpec, SpreadsheetSpec
from core.artifacts.store import ArtifactStore, get_artifact_store
from core.artifacts.validator import validate_for_type

logger = logging.getLogger("aira.artifacts.engine")

DEFAULT_WORKSPACE_SUBDIR = "Artifacts"

_GENERATORS: dict[str, Callable[[Any, Path], dict]] = {
    ArtifactType.DOCX.value: generate_docx,
    ArtifactType.PDF.value: generate_pdf,
    ArtifactType.XLSX.value: generate_xlsx,
    ArtifactType.PPTX.value: generate_pptx,
    ArtifactType.MARKDOWN.value: generate_markdown,
    ArtifactType.TXT.value: generate_txt,
    ArtifactType.CSV.value: generate_csv,
}


def _default_resolve_path(relative_path: str) -> Path:
    """Lazy import - default only. Resolves through the REAL AIRA Workspace
    sandbox (core.filesystem.WorkspaceManager); never imported at module
    load time, so importing this module never touches disk."""
    from core.filesystem import get_workspace_manager
    return get_workspace_manager().resolve(relative_path)


def _publish(event_name: str, **data: Any) -> None:
    """Best-effort publish to the EXISTING Event Bus. Never raises - same
    defensive pattern as core/global_settings.py / core/capability/registry.py."""
    try:
        from core.events import event_bus
        event_bus.publish(event_name, source="ARTIFACTS", agent="ARTIFACTS", data=data)
    except Exception:
        logger.debug("ARTIFACTS | gagal publish %s (diabaikan).", event_name, exc_info=True)


class ArtifactEngine:
    """
    Dependency Injection: `store` and `resolve_path` can both be swapped -
    tests inject a temp ArtifactStore + a temp-dir resolver so no real
    Workspace or database/artifacts.db is ever touched. Production code gets
    the real ArtifactStore + WorkspaceManager lazily via the defaults above.
    """

    def __init__(
        self,
        store: Optional[ArtifactStore] = None,
        resolve_path: Optional[Callable[[str], Path]] = None,
        workspace_subdir: str = DEFAULT_WORKSPACE_SUBDIR,
    ):
        self._store = store
        self._resolve_path = resolve_path or _default_resolve_path
        self._workspace_subdir = workspace_subdir.strip("/\\") or DEFAULT_WORKSPACE_SUBDIR
        self._lock = threading.Lock()

    @property
    def store(self) -> ArtifactStore:
        return self._store or get_artifact_store()

    # ------------------------------------------------------------ public API

    def create_document(
        self, spec: DocumentSpec, artifact_type: Any = ArtifactType.DOCX,
        *, session_id: Optional[str] = None, name: Optional[str] = None,
        source: str = "generated", metadata: Optional[dict] = None,
    ) -> ArtifactResult:
        return self._create(spec, artifact_type, session_id, name, source, metadata)

    def create_spreadsheet(
        self, spec: Any, artifact_type: Any = ArtifactType.XLSX,
        *, session_id: Optional[str] = None, name: Optional[str] = None,
        source: str = "generated", metadata: Optional[dict] = None,
    ) -> ArtifactResult:
        try:
            coerced_type = ArtifactType.coerce(artifact_type)
        except ValueError as exc:
            return ArtifactResult(False, errors=[str(exc)])

        if coerced_type.value == ArtifactType.CSV.value and isinstance(spec, SpreadsheetSpec):
            if not spec.worksheets:
                return ArtifactResult(False, errors=["worksheets: spreadsheet butuh minimal satu worksheet."])
            # CSV can only hold ONE table - the first worksheet is used, the
            # rest are recorded in metadata so nothing silently disappears.
            dropped = [w.name for w in spec.worksheets[1:]]
            spec = CsvSpec.from_worksheet(spec.worksheets[0])
            metadata = {**(metadata or {}), "dropped_worksheets": dropped}

        return self._create(spec, coerced_type, session_id, name, source, metadata)

    def create_presentation(
        self, spec: PresentationSpec, artifact_type: Any = ArtifactType.PPTX,
        *, session_id: Optional[str] = None, name: Optional[str] = None,
        source: str = "generated", metadata: Optional[dict] = None,
    ) -> ArtifactResult:
        return self._create(spec, artifact_type, session_id, name, source, metadata)

    def get(self, artifact_id: str) -> Optional[Artifact]:
        return self.store.get(artifact_id)

    def list(self, session_id: Optional[str] = None) -> list[Artifact]:
        return self.store.list(session_id=session_id)

    def delete(self, artifact_id: str) -> bool:
        return self.store.delete(artifact_id)

    # ------------------------------------------------------------ internal

    def _create(
        self, spec: Any, artifact_type: Any, session_id: Optional[str],
        name: Optional[str], source: str, metadata: Optional[dict],
    ) -> ArtifactResult:
        try:
            artifact_type = ArtifactType.coerce(artifact_type)
        except ValueError as exc:
            return ArtifactResult(False, errors=[str(exc)])

        validation = validate_for_type(spec, artifact_type.value)
        if not validation.is_valid:
            return ArtifactResult(False, errors=validation.messages())

        artifact = Artifact(
            session_id=session_id,
            name=name or self._default_name(spec, artifact_type),
            artifact_type=artifact_type.value,
            mime_type=MIME_TYPES[artifact_type.value],
            source=source,
            status=ArtifactStatus.GENERATING.value,
            metadata=dict(metadata or {}),
        )

        relative_path = f"{self._workspace_subdir}/{artifact.id}{EXTENSIONS[artifact_type.value]}"

        try:
            output_path = self._resolve_path(relative_path)
        except Exception as exc:
            logger.exception("ARTIFACTS | gagal resolve path untuk %s", artifact.id)
            return self._fail(artifact, f"Gagal resolve path penyimpanan: {exc}")

        generator = _GENERATORS.get(artifact_type.value)
        if generator is None:
            return self._fail(artifact, f"Tidak ada generator untuk artifact_type '{artifact_type.value}'.")

        try:
            gen_info = generator(spec, output_path)
        except GenerationError as exc:
            return self._fail(artifact, str(exc))
        except Exception as exc:
            logger.exception("ARTIFACTS | generator gagal tak terduga untuk %s", artifact.id)
            return self._fail(artifact, f"Generator gagal tak terduga: {type(exc).__name__}: {exc}")

        try:
            size = output_path.stat().st_size
        except OSError as exc:
            return self._fail(artifact, f"File hasil generate tidak terbaca: {exc}")

        artifact.storage_reference = relative_path
        artifact.size = size
        artifact.status = ArtifactStatus.READY.value
        artifact.metadata = {**artifact.metadata, "generation": gen_info}

        with self._lock:
            self.store.save(artifact)

        logger.info(
            "ARTIFACT CREATED | id=%s type=%s size=%d path=%s",
            artifact.id, artifact.artifact_type, artifact.size, artifact.storage_reference,
        )
        _publish("artifact.created", id=artifact.id, artifact_type=artifact.artifact_type, size=artifact.size)

        return ArtifactResult(True, artifact=artifact)

    def _fail(self, artifact: Artifact, message: str) -> ArtifactResult:
        artifact.status = ArtifactStatus.FAILED.value
        artifact.metadata = {**artifact.metadata, "error": message}

        with self._lock:
            self.store.save(artifact)

        logger.warning("ARTIFACT FAILED | id=%s type=%s error=%s", artifact.id, artifact.artifact_type, message)
        _publish("artifact.failed", id=artifact.id, artifact_type=artifact.artifact_type, error=message)

        return ArtifactResult(False, artifact=artifact, errors=[message])

    @staticmethod
    def _default_name(spec: Any, artifact_type: ArtifactType) -> str:
        title = getattr(spec, "title", None)
        if title:
            return str(title)
        if isinstance(spec, SpreadsheetSpec) and spec.worksheets:
            return spec.worksheets[0].name
        return f"untitled.{artifact_type.value}"


_engine_singleton: Optional[ArtifactEngine] = None
_engine_lock = threading.Lock()


def get_artifact_engine() -> ArtifactEngine:
    global _engine_singleton
    if _engine_singleton is None:
        with _engine_lock:
            if _engine_singleton is None:
                _engine_singleton = ArtifactEngine()
    return _engine_singleton