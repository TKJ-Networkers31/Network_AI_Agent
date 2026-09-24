"""core/artifacts/generators/csv_gen.py - CsvSpec -> .csv (stdlib csv module)."""
from __future__ import annotations

import csv
from pathlib import Path

from core.artifacts.generators.base import ensure_parent
from core.artifacts.specs import CsvSpec


def generate_csv(spec: CsvSpec, output_path: Path) -> dict:
    ensure_parent(output_path)

    with open(output_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(spec.headers)
        writer.writerows(spec.rows)

    return {"rows": len(spec.rows), "columns": len(spec.headers)}