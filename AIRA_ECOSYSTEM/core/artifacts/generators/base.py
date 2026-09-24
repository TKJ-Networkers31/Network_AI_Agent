"""core/artifacts/generators/base.py - shared contract for artifact generators."""
from __future__ import annotations

from pathlib import Path


class GenerationError(Exception):
    """Raised by a generator when it cannot produce output for an otherwise
    validated spec (e.g. missing optional dependency, disk error). Caught by
    ArtifactEngine and turned into ArtifactResult(success=False)."""


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)