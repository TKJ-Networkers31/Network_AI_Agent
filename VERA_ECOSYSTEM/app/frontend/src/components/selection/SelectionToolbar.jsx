// src/components/selection/SelectionToolbar.jsx
//
// Contextual "Ask AIRA" Floating Overlay & Inline Prompt Composer
// Streamlined according to Master Transformation Directive Section 11:
// - Replaces 8-button clutter with 1 primary action: "Tanya AIRA"
// - Clicking opens a compact contextual prompt composer directly near the selection
// - Automatically includes selected text as context
// - Retains original conversation context without scrolling to bottom
// - Keyboard accessible (Enter to submit, Escape to dismiss)

import { useEffect, useRef, useState } from "react";
import { MessageSquare, Sparkles, Send, X, CornerDownLeft } from "lucide-react";

export default function SelectionToolbar({ selection, onAction, onClose }) {
  const [isComposerOpen, setIsComposerOpen] = useState(false);
  const [promptText, setPromptText] = useState("");
  const inputRef = useRef(null);
  const containerRef = useRef(null);

  useEffect(() => {
    if (isComposerOpen && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isComposerOpen]);

  // Handle escape to close
  useEffect(() => {
    function onKeyDown(e) {
      if (e.key === "Escape") {
        if (isComposerOpen) {
          setIsComposerOpen(false);
        } else {
          onClose?.();
        }
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isComposerOpen, onClose]);

  if (!selection || !selection.selected_text) return null;

  const selectedSnippet = selection.selected_text.trim();
  const truncatedSnippet =
    selectedSnippet.length > 90 ? selectedSnippet.slice(0, 87) + "..." : selectedSnippet;

  const handleSubmit = (e) => {
    e?.preventDefault();
    const finalPrompt = promptText.trim();
    if (!finalPrompt) {
      // Default to asking explanation if prompt is empty
      onAction?.("ask", { ...selection, custom_question: "Jelaskan bagian ini secara teknis dan mendalam." });
    } else {
      onAction?.("ask", { ...selection, custom_question: finalPrompt });
    }
    setPromptText("");
    setIsComposerOpen(false);
    onClose?.();
  };

  const handleQuickChip = (chipText) => {
    onAction?.("ask", { ...selection, custom_question: chipText });
    setPromptText("");
    setIsComposerOpen(false);
    onClose?.();
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(selection.selected_text);
    } catch {}
    onClose?.();
  };

  return (
    <div
      ref={containerRef}
      data-selection-toolbar="true"
      role="region"
      aria-label="Tanya VERA kontekstual"
      onMouseDown={(e) => e.stopPropagation()}
      className="inline-block selection-toolbar-root animate-in fade-in zoom-in-95 duration-150 z-30"
    >
      {!isComposerOpen ? (
        // State 1: Sleek, compact floating pill with primary actions
        <div className="flex items-center gap-1 bg-surface-card/95 backdrop-blur-md border border-cyan-500/30 rounded-full px-2 py-1 shadow-2xl shadow-cyan-950/40 text-xs">
          <button
            type="button"
            onClick={() => setIsComposerOpen(true)}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-cyan-500/15 text-cyan-300 hover:bg-cyan-500/25 hover:text-white transition-all font-medium group"
          >
            <Sparkles size={13} className="text-cyan-400 group-hover:scale-110 transition-transform" />
            <span>Tanya VERA</span>
          </button>

          <button
            type="button"
            onClick={() => handleQuickChip("Jelaskan bagian ini secara teknis dan implikasinya.")}
            className="px-2 py-1 rounded-full text-white/70 hover:text-white hover:bg-white/10 transition text-[11px]"
          >
            Jelaskan
          </button>

          <button
            type="button"
            onClick={handleCopy}
            className="px-2 py-1 rounded-full text-white/50 hover:text-white hover:bg-white/10 transition text-[11px]"
          >
            Salin
          </button>

          <div className="h-3.5 w-px bg-white/10 mx-0.5" />

          {onClose && (
            <button
              type="button"
              onClick={onClose}
              aria-label="Tutup seleksi"
              className="p-1 rounded-full text-white/40 hover:text-white/80 hover:bg-white/10 transition"
            >
              <X size={13} />
            </button>
          )}
        </div>
      ) : (
        // State 2: Compact Contextual Prompt Composer right at the selection
        <form
          onSubmit={handleSubmit}
          className="w-80 sm:w-96 p-3 rounded-2xl bg-surface-card/95 backdrop-blur-xl border border-cyan-500/30 shadow-2xl shadow-black/60 space-y-2.5 text-xs text-white"
        >
          {/* Selected Text Context Badge */}
          <div className="flex items-start justify-between gap-2 p-2 rounded-xl bg-white/[0.04] border border-white/10">
            <div className="flex items-start gap-1.5 min-w-0">
              <MessageSquare size={13} className="text-cyan-400 mt-0.5 shrink-0" />
              <p className="text-[11px] text-white/70 italic line-clamp-2 leading-relaxed">
                "{truncatedSnippet}"
              </p>
            </div>
            <button
              type="button"
              onClick={() => setIsComposerOpen(false)}
              className="text-white/40 hover:text-white shrink-0 p-0.5"
            >
              <X size={13} />
            </button>
          </div>

          {/* Prompt Composer Input */}
          <div className="relative flex items-center">
            <input
              ref={inputRef}
              type="text"
              value={promptText}
              onChange={(e) => setPromptText(e.target.value)}
              placeholder="Tanyakan tentang bagian ini... (Enter kirim)"
              className="w-full pl-3 pr-8 py-2 rounded-xl bg-neutral-900/90 border border-white/10 focus:border-cyan-500/60 focus:outline-none focus:ring-1 focus:ring-cyan-500/40 text-xs placeholder:text-white/30 text-white"
            />
            <button
              type="submit"
              aria-label="Kirim pertanyaan"
              className="absolute right-1.5 p-1 rounded-lg bg-cyan-500 text-black hover:bg-cyan-400 transition"
            >
              <CornerDownLeft size={12} strokeWidth={2.5} />
            </button>
          </div>

          {/* Quick Action Chips */}
          <div className="flex items-center gap-1.5 flex-wrap pt-0.5">
            <span className="text-[10px] text-white/40 uppercase font-medium mr-1">Cepat:</span>
            {[
              "Jelaskan penyebabnya",
              "Bagaimana memperbaikinya?",
              "Bandingkan dengan topologi",
              "Sederhanakan",
            ].map((chip) => (
              <button
                key={chip}
                type="button"
                onClick={() => handleQuickChip(chip)}
                className="text-[10px] px-2 py-0.5 rounded-full bg-white/[0.05] hover:bg-cyan-500/20 hover:text-cyan-200 border border-white/5 transition text-white/60"
              >
                {chip}
              </button>
            ))}
          </div>
        </form>
      )}
    </div>
  );
}
