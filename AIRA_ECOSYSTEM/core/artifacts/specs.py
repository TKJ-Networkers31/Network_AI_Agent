"""
core/artifacts/specs.py - structured document specs (Sprint 2.7 / W5).

The LLM must never produce a binary artifact directly: it produces one of
these structured, JSON-safe specs; core/artifacts/engine.py runs the spec
through a deterministic generator (core/artifacts/generators/*) to produce
the actual file. Parsing here is TOLERANT (same philosophy as
core/dio/analyzer.py + core/dio/builder.py and core/plugins/manifest.py):
malformed input never raises, it degrades to a safe default and
core/artifacts/validator.py is what flags what's wrong before generation
runs.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional

# ============================================================ helpers

def _str(value: Any, default: str = "") -> str:
    return value.strip() if isinstance(value, str) else default


def _str_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw if isinstance(item, (str, int, float))]


def _row(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [("" if item is None else str(item)) for item in raw]


# ============================================================ DOCUMENT

@dataclass
class DocumentBlock:
    """One content block. `type` discriminates which fields apply:
        heading   -> text, level (1-6)
        paragraph -> text, style ("normal" | "bold" | "italic")
        list      -> items[str], ordered (bool)
        table     -> headers[str], rows[list[str]]
    Blocks are ORDERED - this is what lets a DocumentSpec interleave
    headings/paragraphs/lists/tables the way a real document does, while
    still only exposing the four content kinds the spec requires.
    """

    type: str = "paragraph"
    text: str = ""
    level: int = 1
    style: str = "normal"
    items: list[str] = field(default_factory=list)
    ordered: bool = False
    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Any) -> "DocumentBlock":
        data = data if isinstance(data, dict) else {}
        block_type = _str(data.get("type"), "paragraph").lower() or "paragraph"

        level = data.get("level", 1)
        level = level if isinstance(level, int) and not isinstance(level, bool) else 1

        raw_rows = data.get("rows")

        return cls(
            type=block_type,
            text=_str(data.get("text")),
            level=level,
            style=_str(data.get("style"), "normal") or "normal",
            items=_str_list(data.get("items")),
            ordered=bool(data.get("ordered", False)),
            headers=_str_list(data.get("headers")),
            rows=[_row(r) for r in raw_rows] if isinstance(raw_rows, list) else [],
        )


def heading(text: str, level: int = 1) -> DocumentBlock:
    return DocumentBlock(type="heading", text=text, level=level)


def paragraph(text: str, style: str = "normal") -> DocumentBlock:
    return DocumentBlock(type="paragraph", text=text, style=style)


def bullet_list(items: list, ordered: bool = False) -> DocumentBlock:
    return DocumentBlock(type="list", items=[str(i) for i in items], ordered=ordered)


def table_block(headers: list, rows: list) -> DocumentBlock:
    return DocumentBlock(
        type="table",
        headers=[str(h) for h in headers],
        rows=[[str(c) for c in r] for r in rows],
    )


@dataclass
class DocumentSpec:
    title: str = "Untitled Document"
    blocks: list[DocumentBlock] = field(default_factory=list)

    # ---- convenience views mirroring the four required content kinds ----

    @property
    def headings(self) -> list[DocumentBlock]:
        return [b for b in self.blocks if b.type == "heading"]

    @property
    def paragraphs(self) -> list[DocumentBlock]:
        return [b for b in self.blocks if b.type == "paragraph"]

    @property
    def lists(self) -> list[DocumentBlock]:
        return [b for b in self.blocks if b.type == "list"]

    @property
    def tables(self) -> list[DocumentBlock]:
        return [b for b in self.blocks if b.type == "table"]

    def to_dict(self) -> dict:
        return {"title": self.title, "blocks": [b.to_dict() for b in self.blocks]}

    @classmethod
    def from_dict(cls, data: Any) -> "DocumentSpec":
        data = data if isinstance(data, dict) else {}
        blocks: list[DocumentBlock] = []

        if isinstance(data.get("blocks"), list):
            blocks.extend(DocumentBlock.from_dict(b) for b in data["blocks"])
        else:
            # Accept the literal "one list per kind" shape named by the spec
            # (title/headings/paragraphs/lists/tables as separate top-level
            # lists) too, flattened into `blocks` in a stable, readable
            # order: headings -> paragraphs -> lists -> tables. Callers who
            # need real interleaving should pass `blocks` directly.
            for item in data.get("headings") or []:
                item = item if isinstance(item, dict) else {"text": item}
                blocks.append(DocumentBlock.from_dict({**item, "type": "heading"}))
            for item in data.get("paragraphs") or []:
                item = item if isinstance(item, dict) else {"text": item}
                blocks.append(DocumentBlock.from_dict({**item, "type": "paragraph"}))
            for item in data.get("lists") or []:
                item = item if isinstance(item, dict) else {"items": item}
                blocks.append(DocumentBlock.from_dict({**item, "type": "list"}))
            for item in data.get("tables") or []:
                item = item if isinstance(item, dict) else {}
                blocks.append(DocumentBlock.from_dict({**item, "type": "table"}))

        return cls(
            title=_str(data.get("title"), "Untitled Document") or "Untitled Document",
            blocks=blocks,
        )


# ============================================================ SPREADSHEET

VALID_COLUMN_FORMATS = frozenset({"text", "number", "integer", "currency", "date", "percent"})


@dataclass
class WorksheetSpec:
    name: str = "Sheet1"
    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    column_formats: dict[str, str] = field(default_factory=dict)  # header -> format

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Any) -> "WorksheetSpec":
        data = data if isinstance(data, dict) else {}
        raw_rows = data.get("rows")
        formats_raw = data.get("column_formats")

        formats = {
            str(k): str(v).lower()
            for k, v in formats_raw.items()
            if isinstance(v, str)
        } if isinstance(formats_raw, dict) else {}

        return cls(
            name=_str(data.get("name"), "Sheet1") or "Sheet1",
            headers=_str_list(data.get("headers")),
            rows=[_row(r) for r in raw_rows] if isinstance(raw_rows, list) else [],
            column_formats=formats,
        )


@dataclass
class SpreadsheetSpec:
    worksheets: list[WorksheetSpec] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"worksheets": [w.to_dict() for w in self.worksheets]}

    @classmethod
    def from_dict(cls, data: Any) -> "SpreadsheetSpec":
        data = data if isinstance(data, dict) else {}

        if isinstance(data.get("worksheets"), list):
            worksheets = [WorksheetSpec.from_dict(w) for w in data["worksheets"]]
        elif "headers" in data or "rows" in data:
            worksheets = [WorksheetSpec.from_dict(data)]  # single-sheet shorthand
        else:
            worksheets = []

        return cls(worksheets=worksheets)


# ============================================================ CSV (single table)

@dataclass
class CsvSpec:
    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Any) -> "CsvSpec":
        data = data if isinstance(data, dict) else {}
        raw_rows = data.get("rows")
        return cls(
            headers=_str_list(data.get("headers")),
            rows=[_row(r) for r in raw_rows] if isinstance(raw_rows, list) else [],
        )

    @classmethod
    def from_worksheet(cls, worksheet: "WorksheetSpec") -> "CsvSpec":
        return cls(headers=list(worksheet.headers), rows=[list(r) for r in worksheet.rows])


# ============================================================ PRESENTATION

@dataclass
class SlideSection:
    heading: str = ""
    content: list[str] = field(default_factory=list)   # bullet points
    table: Optional[dict] = None                        # {"headers": [...], "rows": [[...]]}
    image_ref: Optional[str] = None                      # reference/placeholder (path or description)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Any) -> "SlideSection":
        data = data if isinstance(data, dict) else {}

        table_raw = data.get("table")
        table = None
        if isinstance(table_raw, dict):
            raw_rows = table_raw.get("rows")
            table = {
                "headers": _str_list(table_raw.get("headers")),
                "rows": [_row(r) for r in raw_rows] if isinstance(raw_rows, list) else [],
            }

        return cls(
            heading=_str(data.get("heading")),
            content=_str_list(data.get("content")),
            table=table,
            image_ref=_str(data.get("image_ref")) or None,
        )


@dataclass
class PresentationSpec:
    title: str = "Untitled Presentation"
    sections: list[SlideSection] = field(default_factory=list)
    conclusion: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "sections": [s.to_dict() for s in self.sections],
            "conclusion": self.conclusion,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "PresentationSpec":
        data = data if isinstance(data, dict) else {}
        raw_sections = data.get("sections")
        sections = [SlideSection.from_dict(s) for s in raw_sections] if isinstance(raw_sections, list) else []

        return cls(
            title=_str(data.get("title"), "Untitled Presentation") or "Untitled Presentation",
            sections=sections,
            conclusion=_str(data.get("conclusion")) or None,
        )