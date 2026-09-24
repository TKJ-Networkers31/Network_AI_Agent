"""
core/artifacts/generators/ - deterministic spec -> file generators
(Sprint 2.7 / W5).

One function per artifact_type, dispatched by core/artifacts/engine.py. Each
generator raises GenerationError on failure (missing optional dependency,
disk error) - it never returns a partial/corrupt file.
"""

from core.artifacts.generators.base import GenerationError
from core.artifacts.generators.docx_gen import generate_docx
from core.artifacts.generators.pdf_gen import generate_pdf
from core.artifacts.generators.xlsx_gen import generate_xlsx
from core.artifacts.generators.pptx_gen import generate_pptx
from core.artifacts.generators.document_text import generate_markdown, generate_txt
from core.artifacts.generators.csv_gen import generate_csv

__all__ = [
    "GenerationError",
    "generate_docx", "generate_pdf", "generate_xlsx", "generate_pptx",
    "generate_markdown", "generate_txt", "generate_csv",
]