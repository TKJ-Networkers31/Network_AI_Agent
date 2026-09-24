"""core/artifacts/generators/pdf_gen.py - DocumentSpec -> .pdf (reportlab)."""
from __future__ import annotations

from pathlib import Path

from core.artifacts.generators.base import GenerationError, ensure_parent
from core.artifacts.specs import DocumentSpec


def generate_pdf(spec: DocumentSpec, output_path: Path) -> dict:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem, Table, TableStyle,
        )
    except ImportError as exc:
        raise GenerationError("reportlab tidak terpasang (pip install reportlab).") from exc

    ensure_parent(output_path)

    styles = getSampleStyleSheet()
    story = [Paragraph(_escape(spec.title), styles["Title"]), Spacer(1, 12)]
    counts = {"headings": 0, "paragraphs": 0, "lists": 0, "tables": 0}

    heading_styles = {
        1: styles["Heading1"], 2: styles["Heading2"], 3: styles["Heading3"],
        4: styles["Heading4"], 5: styles["Heading4"], 6: styles["Heading4"],
    }

    for block in spec.blocks:
        if block.type == "heading":
            level = max(1, min(block.level, 6))
            story.append(Paragraph(_escape(block.text), heading_styles[level]))
            counts["headings"] += 1

        elif block.type == "paragraph":
            text = _escape(block.text)
            if block.style == "bold":
                text = f"<b>{text}</b>"
            elif block.style == "italic":
                text = f"<i>{text}</i>"
            story.append(Paragraph(text, styles["Normal"]))
            counts["paragraphs"] += 1

        elif block.type == "list":
            items = [ListItem(Paragraph(_escape(item), styles["Normal"])) for item in block.items]
            story.append(ListFlowable(items, bulletType="1" if block.ordered else "bullet"))
            counts["lists"] += 1

        elif block.type == "table":
            data = [block.headers] + block.rows
            table = Table(data)
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
            ]))
            story.append(table)
            counts["tables"] += 1

        story.append(Spacer(1, 8))

    try:
        doc = SimpleDocTemplate(str(output_path), pagesize=A4)
        doc.build(story)
    except Exception as exc:
        raise GenerationError(f"Gagal membuat .pdf: {exc}") from exc

    return counts


def _escape(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")