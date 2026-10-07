"""core/file_processing/service.py - jembatan ke AttachmentEngine (tanpa mengubah schema)."""
from __future__ import annotations

from core.file_processing.processor import FileProcessor


def process_attachment(attachment_engine, attachment_id: str, session_id: str = None,
                       processor: FileProcessor = None, force: bool = False) -> dict | None:
    att = attachment_engine.get(attachment_id, session_id=session_id)
    if att is None:
        return None
    if not force and isinstance(att.metadata.get("processing"), dict):
        return att.metadata["processing"]
    ref = attachment_engine.get_content_reference(attachment_id, session_id=session_id)
    if not ref or ref.get("kind") != "workspace_path":
        return None
    proc = (processor or FileProcessor()).process(ref["absolute_path"], att.name).to_dict()
    att.metadata = {**att.metadata, "processing": proc}
    attachment_engine.store.save(att)
    return proc
