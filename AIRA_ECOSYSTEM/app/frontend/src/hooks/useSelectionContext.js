// src/hooks/useSelectionContext.js
import { useCallback, useEffect, useRef, useState } from "react";

const SURROUNDING_WINDOW = 240;

function extractSurrounding(fullText, start, end, window = SURROUNDING_WINDOW) {
  if (!fullText) return "";
  const winStart = Math.max(0, start - window);
  const winEnd = Math.min(fullText.length, end + window);
  const prefix = (winStart > 0 ? "…" : "") + fullText.slice(winStart, start);
  const suffix = fullText.slice(end, winEnd) + (winEnd < fullText.length ? "…" : "");
  return [prefix, suffix].filter(Boolean).join("\n[...]\n");
}

export function useSelectionContext(containerRef, { messageId, conversationId, sessionId } = {}) {
  const [selection, setSelection] = useState(null);
  const idsRef = useRef({ messageId, conversationId, sessionId });
  idsRef.current = { messageId, conversationId, sessionId };

  const clear = useCallback(() => setSelection(null), []);

  useEffect(() => {
    const container = containerRef?.current;
    if (!container) return undefined;

    function isInsideToolbar(target) {
      return Boolean(target?.closest?.("[data-selection-toolbar]"));
    }

    // 1. Sumber utama: browser 'selectionchange' — juga menangani
    //    "selection berubah menjadi collapsed" dan "selection kosong".
    function handleSelectionChange() {
      const sel = window.getSelection?.();

      if (!sel || sel.isCollapsed || sel.rangeCount === 0) {
        setSelection(null);
        return;
      }

      const range = sel.getRangeAt(0);

      if (!container.contains(range.commonAncestorContainer)) {
        // Selection pindah ke luar container ini — bukan urusan hook ini.
        return;
      }

      const selectedText = sel.toString().trim();
      if (!selectedText) {
        setSelection(null);
        return;
      }

      const fullText = container.textContent || "";
      const preRange = range.cloneRange();
      preRange.selectNodeContents(container);
      preRange.setEnd(range.startContainer, range.startOffset);
      const startOffset = preRange.toString().length;
      const endOffset = startOffset + selectedText.length;

      const { messageId: mid, conversationId: cid, sessionId: sid } = idsRef.current;

      setSelection({
        source_type: "message",
        message_id: mid || null,
        conversation_id: cid || null,
        session_id: sid || null,
        selected_text: selectedText,
        surrounding_text: extractSurrounding(fullText, startOffset, endOffset),
        start_offset: startOffset,
        end_offset: endOffset,
      });
    }

    // 2. "Klik area lain" — kebalikan dari klik di dalam container/toolbar.
    function handlePointerDown(e) {
      if (container.contains(e.target) || isInsideToolbar(e.target)) return;
      setSelection(null);
    }

    // 3. Escape membatalkan selection secara eksplisit.
    function handleKeyDown(e) {
      if (e.key === "Escape") setSelection(null);
    }

    document.addEventListener("selectionchange", handleSelectionChange);
    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("selectionchange", handleSelectionChange);
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [containerRef]);

  return { selection, clear };
}