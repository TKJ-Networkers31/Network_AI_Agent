// src/components/ChatInput.jsx
//
// Multi-file upload, drag-and-drop preview, slash menu, stop button,
// capability slot, and WhatsApp-style quote reply support.
// Styled with Cyber Minimalist Glass & Neon Glowing Hover.

import { useEffect, useRef, useState } from "react";
import SlashMenu from "./SlashMenu.jsx";
import CapabilityInputSlot from "./capabilities/CapabilityInputSlot.jsx";

function AttachIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" style={{ width: 16, height: 16 }}>
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

function FileTypeIcon({ name = "" }) {
  const ext = name.split(".").pop()?.toLowerCase();
  const isImg = ["png", "jpg", "jpeg", "webp", "gif", "bmp"].includes(ext);
  if (isImg) {
    return (
      <svg viewBox="0 0 24 24" fill="none" className="w-3.5 h-3.5 text-purple-400 shrink-0">
        <rect x="3" y="3" width="18" height="18" rx="2" stroke="currentColor" strokeWidth="1.8" />
        <circle cx="8.5" cy="8.5" r="1.5" fill="currentColor" />
        <path d="M21 15l-5-5L5 21" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" fill="none" className="w-3.5 h-3.5 text-cyan-400 shrink-0">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <polyline points="14 2 14 8 20 8" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function ChatInput({
  onSend,
  disabled,
  tools = [],
  voiceControls,
  voiceTranscript = "",
  interimVoiceText = "",
  isRunning = false,
  onStop,
  onCapabilityInvoke,
  onAttachFile,
  onAttachFiles,
  attachedFileName = null,
  attachedFiles = [],
  onRemoveAttachment,
  isUploading = false,
  quote = null,
  onClearQuote,
}) {
  const [value, setValue] = useState("");
  const [showSlash, setShowSlash] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const textareaRef = useRef(null);
  const fileInputRef = useRef(null);

  // Kutipan baru masuk -> fokus ke textarea supaya user langsung mengetik.
  useEffect(() => {
    if (quote) requestAnimationFrame(() => textareaRef.current?.focus());
  }, [quote]);

  // Input ucapan suara masuk -> masukkan ke textarea dan fokus untuk review/edit
  useEffect(() => {
    if (voiceTranscript && typeof voiceTranscript === "string") {
      setValue((prev) => (prev ? `${prev.trim()} ${voiceTranscript.trim()}` : voiceTranscript.trim()));
      requestAnimationFrame(() => textareaRef.current?.focus());
    }
  }, [voiceTranscript]);

  // Auto-resize tinggi textarea sesuai isi (max 140px)
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 140)}px`;
  }, [value]);

  function handleChange(e) {
    const val = e.target.value;
    setValue(val);
    setShowSlash(val.startsWith("/") && !val.includes(" ") && tools.length > 0);
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    } else if (e.key === "Escape") {
      if (showSlash) setShowSlash(false);
      else if (quote) onClearQuote?.();
    }
  }

  function submit(e) {
    if (e) e.preventDefault();
    const text = value.trim();
    if (!text && !quote && attachedFiles.length === 0 && !attachedFileName) return;
    if (disabled) return;

    onSend(text, quote);
    setValue("");
    setShowSlash(false);

    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }

  function pickTool(t) {
    const toolName = typeof t === "string" ? t : t?.name || "";
    setValue(`/${toolName} `);
    setShowSlash(false);
    textareaRef.current?.focus();
  }

  function handleFilesPicked(e) {
    const files = Array.from(e.target.files || []);
    if (files.length === 0) return;
    if (onAttachFiles) {
      onAttachFiles(files);
    } else if (onAttachFile) {
      onAttachFile(files[0]);
    }
    e.target.value = "";
  }

  function handleDragOver(e) {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  }

  function handleDragLeave(e) {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  }

  function handleDrop(e) {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    const files = Array.from(e.dataTransfer.files || []);
    if (files.length === 0) return;

    if (onAttachFiles) {
      onAttachFiles(files);
    } else if (onAttachFile) {
      onAttachFile(files[0]);
    }
  }

  const slashQuery = showSlash ? value.slice(1) : "";

  // Gabungkan file attachments
  const activeFiles = [...attachedFiles];
  if (activeFiles.length === 0 && attachedFileName) {
    activeFiles.push({ name: attachedFileName, id: "single" });
  }

  return (
    <div
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className={`shrink-0 -mx-3 sm:-mx-5 lg:-mx-6 -mb-3 sm:-mb-4 px-3 sm:px-5 lg:px-6 py-2 bg-app/80 backdrop-blur-2xl border-t transition-all ${
        isDragging
          ? "border-cyan-400 bg-cyan-950/20 shadow-[0_0_25px_rgba(56,189,248,0.25)]"
          : "border-white/[0.08]"
      }`}
    >
      <div className="relative max-w-5xl xl:max-w-6xl mx-auto">
        {showSlash && tools.length > 0 && (
          <SlashMenu tools={tools} query={slashQuery} onPick={pickTool} />
        )}

        {/* Multi-file preview chips */}
        {activeFiles.length > 0 && (
          <div className="mb-2 flex flex-wrap items-center gap-1.5 px-1">
            <span className="text-[11px] text-text-secondary font-medium mr-1 flex items-center gap-1">
              <AttachIcon /> Lampiran ({activeFiles.length}):
            </span>
            {activeFiles.map((f, idx) => (
              <div
                key={f.id || idx}
                className="group inline-flex items-center gap-1.5 bg-surface/70 border border-white/10 hover:border-cyan-400/50 hover:shadow-[0_0_12px_rgba(56,189,248,0.25)] rounded-control px-2.5 py-1 text-xs text-text-primary transition shadow-sm"
              >
                <FileTypeIcon name={f.name} />
                <span className="truncate max-w-[160px] font-medium" title={f.name}>
                  {f.name}
                </span>
                {f.hasOcr && (
                  <span className="text-[9px] px-1 py-0.2 rounded bg-purple-500/20 text-purple-300 font-mono">
                    OCR
                  </span>
                )}
                {onRemoveAttachment && (
                  <button
                    type="button"
                    onClick={() => onRemoveAttachment(f.id)}
                    aria-label={`Hapus ${f.name}`}
                    title="Hapus file"
                    className="ml-1 text-text-secondary hover:text-danger rounded p-0.5 transition"
                  >
                    ✕
                  </button>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Uploading progress indicator */}
        {isUploading && (
          <div className="mb-2 flex items-center gap-2 px-2 text-xs text-cyan-400 animate-pulse">
            <span className="w-3 h-3 rounded-full border-2 border-cyan-400/30 border-t-cyan-400 animate-spin" />
            <span>Mengunggah & menganalisis file...</span>
          </div>
        )}

        {/* Quote reply card */}
        {quote?.selected_text && (
          <div className="mb-1.5 flex items-start gap-2 rounded-xl border-l-4 border-cyan-400 bg-surface/80 border border-white/10 px-3 py-2">
            <div className="min-w-0 flex-1">
              <div className="text-[10px] uppercase tracking-wide text-cyan-400 mb-0.5 font-semibold">
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
              className="shrink-0 w-6 h-6 inline-flex items-center justify-center rounded-full text-white/40 hover:text-white hover:bg-white/10 transition text-xs"
            >
              ✕
            </button>
          </div>
        )}

        {interimVoiceText && (
          <div className="mb-2 px-3 py-1.5 rounded-xl bg-cyan-500/10 border border-cyan-500/30 text-xs text-cyan-300 italic flex items-center gap-2 animate-pulse">
            <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping" />
            <span className="font-mono text-[11px] not-italic text-cyan-400 font-semibold uppercase tracking-wider">Mendengarkan:</span>
            <span className="truncate">{interimVoiceText}</span>
          </div>
        )}

        <form
          onSubmit={submit}
          className="flex items-end gap-2 bg-surface/50 border border-white/10 rounded-2xl p-1.5 sm:p-2 focus-within:border-cyan-400/60 focus-within:shadow-[0_0_20px_rgba(56,189,248,0.2)] transition-all duration-200"
        >
          {voiceControls}

          {(onAttachFiles || onAttachFile) && (
            <>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                className="hidden"
                onChange={handleFilesPicked}
              />
              <button
                type="button"
                title="Lampirkan satu atau beberapa gambar/dokumen (atau drag & drop ke sini)"
                aria-label="Lampirkan file"
                onClick={() => fileInputRef.current?.click()}
                className="shrink-0 w-8 h-8 inline-flex items-center justify-center rounded-xl text-white/50 hover:text-cyan-300 hover:bg-cyan-500/10 hover:border hover:border-cyan-500/20 transition"
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
              isDragging
                ? "Lepaskan gambar/dokumen di sini untuk upload..."
                : quote
                ? "Tulis pertanyaanmu tentang kutipan ini..."
                : activeFiles.length > 0
                ? "Tanyakan atau minta reasoning atas dokumen/gambar yang terlampir..."
                : "Tanya apa saja, ketik '/' untuk tool, lampirkan dokumen/gambar, atau tekan mic..."
            }
            className="flex-1 bg-transparent resize-none outline-none px-2.5 py-1.5 text-sm text-text-primary placeholder-text-secondary/50 max-h-32"
          />

          {isRunning ? (
            <button
              type="button"
              onClick={onStop}
              aria-label="Hentikan proses"
              title="Hentikan proses"
              className="shrink-0 w-9 h-9 flex items-center justify-center bg-danger text-white rounded-xl shadow-card hover:brightness-110 active:scale-95 transition"
            >
              <svg viewBox="0 0 24 24" fill="currentColor" style={{ width: 14, height: 14 }}>
                <rect x="5" y="5" width="14" height="14" rx="2.5" />
              </svg>
            </button>
          ) : (
            <button
              type="submit"
              disabled={disabled || (!value.trim() && !quote && activeFiles.length === 0)}
              aria-label="Kirim"
              className="shrink-0 w-9 h-9 flex items-center justify-center bg-gradient-to-r from-cyan-500 to-purple-600 text-white rounded-xl shadow-[0_0_15px_rgba(56,189,248,0.3)] hover:shadow-[0_0_25px_rgba(56,189,248,0.5)] hover:scale-105 active:scale-95 disabled:opacity-30 disabled:shadow-none disabled:cursor-not-allowed transition"
            >
              {disabled ? (
                <span className="w-3.5 h-3.5 rounded-full border-2 border-white/40 border-t-white animate-spin" />
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
