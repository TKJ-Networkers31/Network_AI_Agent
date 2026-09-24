"""core/artifacts/generators/document_text.py - DocumentSpec -> .md / .txt (stdlib only)."""
from __future__ import annotations

from pathlib import Path

from core.artifacts.generators.base import ensure_parent
from core.artifacts.specs import DocumentSpec


def render_markdown(spec: DocumentSpec) -> str:
    lines = [f"# {spec.title}", ""]

    for block in spec.blocks:
        if block.type == "heading":
            level = max(1, min(block.level, 6))
            lines.append(f"{'#' * level} {block.text}")
        elif block.type == "paragraph":
            text = block.text
            if block.style == "bold":
                text = f"**{text}**"
            elif block.style == "italic":
                text = f"*{text}*"
            lines.append(text)
        elif block.type == "list":
            for index, item in enumerate(block.items, start=1):
                prefix = f"{index}." if block.ordered else "-"
                lines.append(f"{prefix} {item}")
        elif block.type == "table":
            lines.append("| " + " | ".join(block.headers) + " |")
            lines.append("| " + " | ".join("---" for _ in block.headers) + " |")
            for row in block.rows:
                lines.append("| " + " | ".join(str(c) for c in row) + " |")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_txt(spec: DocumentSpec) -> str:
    lines = [spec.title, "=" * len(spec.title), ""]

    for block in spec.blocks:
        if block.type == "heading":
            lines.append(block.text.upper())
            lines.append("-" * len(block.text))
        elif block.type == "paragraph":
            lines.append(block.text)
        elif block.type == "list":
            for index, item in enumerate(block.items, start=1):
                prefix = f"{index}." if block.ordered else "*"
                lines.append(f"  {prefix} {item}")
        elif block.type == "table":
            lines.append(" | ".join(block.headers))
            for row in block.rows:
                lines.append(" | ".join(str(c) for c in row))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def generate_markdown(spec: DocumentSpec, output_path: Path) -> dict:
    ensure_parent(output_path)
    text = render_markdown(spec)
    output_path.write_text(text, encoding="utf-8")
    return {"chars": len(text), "blocks": len(spec.blocks)}


def generate_txt(spec: DocumentSpec, output_path: Path) -> dict:
    ensure_parent(output_path)
    text = render_txt(spec)
    output_path.write_text(text, encoding="utf-8")
    return {"chars": len(text), "blocks": len(spec.blocks)}