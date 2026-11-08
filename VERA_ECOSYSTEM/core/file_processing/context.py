"""core/file_processing/context.py - hasil pemrosesan -> payload ContextSection.
Membedakan: attachment asli, file hasil ekstraksi, OCR, teks dokumen, vision. Menyebut status
partial/failed secara eksplisit. Tidak ada truncate."""
from __future__ import annotations


def processing_context_text(proc: dict) -> str:
    if not proc:
        return ""
    L = [f"[Pemrosesan attachment '{proc['source']}': status={proc['status']}]"]
    for f in proc.get("files", []):
        if f["type"] == "archive":
            L.append(f"- ARCHIVE {f['path']} ({f['status']}) {f.get('detail','')}")
        else:
            L.append(f"- FILE {f['path']} [{f['type']}] status={f['status']} via {','.join(f['processors']) or '-'}")
    for e in proc.get("errors", []):
        L.append(f"! {e['code']}: {e['message']} ({e.get('path')}) - JANGAN mengarang bagian ini.")
    for t in proc.get("text", []):
        L.append(f"\n--- TEKS DOKUMEN {t['source_file']} hal/sheet={t['page']} ---\n{t['text']}")
    for o in proc.get("ocr", []):
        L.append(f"\n--- HASIL OCR {o['source_file']} (conf={o.get('confidence')}, bahasa={o.get('language')}) ---\n"
                 f"{o['extracted_text'] or '(tidak ada teks terbaca)'}")
    for i in proc.get("images", []):
        v = i["vision"]
        if v["status"] == "available":
            L.append(f"\n--- ANALISIS VISUAL {i['source_file']} ---\n{(v.get('analysis') or {}).get('description','')}")
        else:
            L.append(f"\n--- ANALISIS VISUAL {i['source_file']}: {v['status']} ({v.get('reason')}) ---")
    return "\n".join(L)
