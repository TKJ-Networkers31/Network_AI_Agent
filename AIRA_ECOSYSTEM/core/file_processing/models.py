"""
core/file_processing/models.py - hasil pemrosesan attachment (OCR, dokumen,
archive). Dataclass murni, JSON-safe, tanpa I/O.

Disimpan di Attachment.metadata["processing"] (key baru, backward-compatible:
schema Attachment/DB tidak berubah, metadata sudah JSON bebas).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

COMPLETED, PARTIAL, FAILED = "completed", "partial", "failed"
FILE_COMPLETED, FILE_PARTIAL, FILE_FAILED, FILE_UNSUPPORTED = "completed", "partial", "failed", "unsupported"

E_UNSUPPORTED = "unsupported_format"
E_EXTRACTION = "extraction_failed"
E_OCR = "ocr_failed"
E_VISION = "vision_failed"
E_RESOURCE = "resource_exhausted"
E_CORRUPTED = "corrupted_archive"
E_SECURITY = "security_blocked"


@dataclass
class ProcessingResult:
    source: str
    type: str = "file"
    status: str = COMPLETED
    files: list = field(default_factory=list)    # [{path,type,status,processors,detail}]
    text: list = field(default_factory=list)     # [{source_file,page,kind,text}]
    ocr: list = field(default_factory=list)      # [{source_file,page,extracted_text,lines,confidence,language,engine}]
    images: list = field(default_factory=list)   # [{source_file,width,height,vision:{status,provider,reason,analysis}}]
    metadata: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)   # [{code,message,path}]

    def error(self, code: str, message: str, path: Optional[str] = None) -> None:
        self.errors.append({"code": code, "message": message, "path": path})

    def finalize(self) -> "ProcessingResult":
        leaves = [f for f in self.files if f.get("type") != "archive"]
        done = [f for f in leaves if f["status"] == FILE_COMPLETED]
        bad = [f for f in leaves if f["status"] != FILE_COMPLETED]
        if (leaves or self.errors) and not done and (bad or self.errors):
            self.status = FAILED
        elif bad or self.errors:
            self.status = PARTIAL
        else:
            self.status = COMPLETED
        return self

    def to_dict(self) -> dict:
        return {
            "source": self.source, "type": self.type, "status": self.status,
            "files": self.files, "text": self.text, "ocr": self.ocr,
            "images": self.images, "metadata": self.metadata, "errors": self.errors,
        }