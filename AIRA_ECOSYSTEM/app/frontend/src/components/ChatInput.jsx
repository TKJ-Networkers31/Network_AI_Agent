// app/frontend/src/components/ChatInput.jsx
// UI Redesign Sprint (Worker C) — identical props (onSend, disabled,
// tools, voiceControls) and identical slash-menu / submit logic to the
// original. Only the composer chrome changed: large rounded textarea,
// capsule send button, premium padding.

import { useRef, useState } from "react";
import SlashMenu from "./SlashMenu.jsx";

export default function ChatInput({ onSend, disabled, tools = [], voiceControls }) {
  const [value, setValue] = useState("");
  const [showSlash, setShowSlash] = useState(false);
  const textareaRef = useRef(null);

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
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
    setShowSlash(false);
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey && !showSlash) {
      submit(e);
    }
    if (e.key === "Escape") {
      setShowSlash(false);
    }
  }

  const slashQuery = showSlash ? value.slice(1) : "";

  return (
    <div className="relative">
      {showSlash && tools.length > 0 && <SlashMenu tools={tools} query={slashQuery} onPick={pickTool} />}

      <form
        onSubmit={submit}
        className="flex items-end gap-2 bg-surface/80 backdrop-blur-xl border border-border rounded-card p-2.5 shadow-card focus-within:border-sakura/40 transition"
      >
        {voiceControls}

        <textarea
          ref={textareaRef}
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          rows={1}
          placeholder="Ask anything, ketik '/' untuk tool, atau tekan mic untuk bicara..."
          className="flex-1 bg-transparent resize-none outline-none px-3 py-2.5 text-body text-text-primary placeholder-text-secondary/60 max-h-32"
        />

        <button
          type="submit"
          disabled={disabled || !value.trim()}
          aria-label="Kirim"
          className="shrink-0 w-10 h-10 flex items-center justify-center bg-sakura-gradient text-white rounded-pill shadow-sakura-glow disabled:opacity-30 disabled:shadow-none disabled:cursor-not-allowed transition"
        >
          {disabled ? (
            <span className="w-3.5 h-3.5 rounded-pill border-2 border-white/40 border-t-white animate-spin" />
          ) : (
            <svg viewBox="0 0 24 24" fill="none" style={{ width: 16, height: 16 }}>
              <path d="M5 12h13M13 6l6 6-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          )}
        </button>
      </form>
    </div>
  );
}