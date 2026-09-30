// src/components/ChatInput.jsx
//
// (Riwayat sebelumnya dipertahankan: full-bleed, slash menu, Stop, W8 capability
// slot, attach file.)
//
// INTEGRATION RECOVERY: kutipan ala WhatsApp reply.
// - Prop baru `quote` ({selected_text, ...}) dan `onClearQuote`. Saat `quote`
//   ada, kartu kutipan tampil di atas textarea dan textarea otomatis fokus.
// - onSend(text, quote) - pemanggil yang memutuskan cara membangun pesan.
// - Kutipan boleh dikirim tanpa teks tambahan (mengikuti default backend).
// - Esc (tanpa slash menu) menghapus kutipan.

import { useEffect, useRef, useState } from "react";
import SlashMenu from "./SlashMenu.jsx";
import CapabilityInputSlot from "./capabilities/CapabilityInputSlot.jsx";

function AttachIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" style={{ width: 15, height: 15 }}>
      <path
        d="M17 8v8a4 4 0 0 1-8 0V6a2.5 2.5 0 0 1 5 0v9a1 1 0 0 1-2 0V8"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export default function ChatInput({
  onSend,
  disabled,
  tools = [],
  voiceControls,
  isRunning = false,
  onStop,
  onCapabilityInvoke,
  onAttachFile,
  attachedFileName = null,
  quote = null,
  onClearQuote,
}) {
  const [value, setValue] = useState("");
  const [showSlash, setShowSlash] = useState(false);
  const textareaRef = useRef(null);
  const fileInputRef = useRef(null);

  // Kutipan baru masuk -> fokus ke textarea supaya user langsung mengetik.
  useEffect(() => {
    if (quote) requestAnimationFrame(() => textareaRef.current?.focus());
  }, [quote]);

  function handleChange(e) {
    const v = e.target.value;
    setValue(v);
    setShowSlash(v.startsWith("/") && !v.includes(" "));
  }

  function pickTool(name) {
    const next = `/${name} `;
    setValue(next);
    setShowSlash(false);
    requestAnimationFrame(() => textareaRef.current?.focus());
  }

  function submit(e) {
    e.preventDefault();
    const trimmed = value.trim();
    if ((!trimmed && !quote) || disabled) return;
    onSend(trimmed, quote);
    setValue("");
    setShowSlash(false);
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent?.isComposing && !showSlash) {
      submit(e);
    }
    if (e.key === "Escape") {
      if (showSlash) setShowSlash(false);
      else if (quote) onClearQuote?.();
    }
  }

  function handleFilePicked(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (file && onAttachFile) onAttachFile(file);
  }

  const slashQuery = showSlash ? value.slice(1) : "";

  return (
    <div className="shrink-0 -mx-3 sm:-mx-5 lg:-mx-6 -mb-3 sm:-mb-4 px-3 sm:px-5 lg:px-6 py-2.5 bg-surface/80 backdrop-blur-xl border-t border-border">
      <div className="relative max-w-4xl mx-auto">
        {showSlash && tools.length > 0 && (
          <SlashMenu tools={tools} query={slashQuery} onPick={pickTool} />
        )}

        {attachedFileName && (
          <div className="mb-1.5 flex items-center gap-1.5 text-[11px] text-white/50 px-1">
            <AttachIcon />
            <span className="truncate">{attachedFileName}</span>
          </div>
        )}

        {quote?.selected_text && (
          <div className="mb-1.5 flex items-start gap-2 rounded-xl2 border-l-4 border-sakura bg-white/[0.06] px-3 py-2">
            <div className="min-w-0 flex-1">
              <div className="text-[10px] uppercase tracking-wide text-sakura/80 mb-0.5">
                Membalas kutipan
              </div>
              <p className="text-xs text-white/70 line-clamp-3 whitespace-pre-wrap break-words">
                {quote.selected_text}
              </p>
            </div>
            <button
              type="button"
              onClick={() => onClearQuote?.()}
              aria-label="Hapus kutipan"
              title="Hapus kutipan (Esc)"
              className="shrink-0 w-6 h-6 inline-flex items-center justify-center rounded-pill text-white/40 hover:text-white hover:bg-white/10 transition text-xs"
            >
              ✕
            </button>
          </div>
        )}

        <form
          onSubmit={submit}
          className="flex items-end gap-2 bg-white/[0.04] border border-border rounded-card p-2 focus-within:border-sakura/40 transition"
        >
          {voiceControls}

          {onAttachFile && (
            <>
              <input ref={fileInputRef} type="file" className="hidden" onChange={handleFilePicked} />
              <button
                type="button"
                title="Lampirkan file"
                aria-label="Lampirkan file"
                onClick={() => fileInputRef.current?.click()}
                className="shrink-0 w-8 h-8 inline-flex items-center justify-center rounded-pill text-white/40 hover:text-white hover:bg-white/10 transition"
              >
                <AttachIcon />
              </button>
            </>
          )}

          <CapabilityInputSlot onInvoke={onCapabilityInvoke} />

          <textarea
            ref={textareaRef}
            value={value}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            rows={1}
            placeholder={
              quote
                ? "Tulis pertanyaanmu tentang kutipan ini..."
                : "Ask anything, ketik '/' untuk tool, atau tekan mic untuk bicara..."
            }
            className="flex-1 bg-transparent resize-none outline-none px-3 py-2.5 text-body text-text-primary placeholder-text-secondary/60 max-h-32"
          />

          {isRunning ? (
            <button
              type="button"
              onClick={onStop}
              aria-label="Hentikan proses"
              title="Hentikan proses"
              className="shrink-0 w-10 h-10 flex items-center justify-center bg-danger text-white rounded-pill shadow-card hover:brightness-110 transition"
            >
              <svg viewBox="0 0 24 24" fill="currentColor" style={{ width: 14, height: 14 }}>
                <rect x="5" y="5" width="14" height="14" rx="2.5" />
              </svg>
            </button>
          ) : (
            <button
              type="submit"
              disabled={disabled || (!value.trim() && !quote)}
              aria-label="Kirim"
              className="shrink-0 w-10 h-10 flex items-center justify-center bg-sakura-gradient text-white rounded-pill shadow-sakura-glow disabled:opacity-30 disabled:shadow-none disabled:cursor-not-allowed transition"
            >
              {disabled ? (
                <span className="w-3.5 h-3.5 rounded-pill border-2 border-white/40 border-t-white animate-spin" />
              ) : (
                <svg viewBox="0 0 24 24" fill="none" style={{ width: 16, height: 16 }}>
                  <path
                    d="M5 12h13M13 6l6 6-6 6"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              )}
            </button>
          )}
        </form>
      </div>
    </div>
  );
}