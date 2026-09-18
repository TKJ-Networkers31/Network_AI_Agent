import { useRef, useState } from "react";
import SlashMenu from "./SlashMenu.jsx";

export default function ChatInput({ onSend, disabled, tools = [], voiceControls }) {
  const [value, setValue] = useState("");
  const [showSlash, setShowSlash] = useState(false);
  const textareaRef = useRef(null);

  function handleChange(e) {
    const nextValue = e.target.value;
    setValue(nextValue);
    setShowSlash(nextValue.startsWith("/") && !nextValue.includes(" "));
  }

  function pickTool(name) {
    setValue(`/${name} `);
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
    if (e.key === "Enter" && !e.shiftKey && !showSlash) submit(e);
    if (e.key === "Escape") setShowSlash(false);
  }

  const slashQuery = showSlash ? value.slice(1) : "";

  return (
    <div className="relative w-full">
      {showSlash && tools.length > 0 && (
        <SlashMenu tools={tools} query={slashQuery} onPick={pickTool} />
      )}

      <form
        onSubmit={submit}
        className="aira-panel aira-control flex flex-col gap-3 p-3 sm:p-4"
      >
        <textarea
          ref={textareaRef}
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          rows={2}
          disabled={disabled}
          placeholder="Ask AIRA anything… ketik '/' untuk tool"
          className="w-full min-h-16 max-h-40 resize-none bg-transparent px-1 py-1 text-sm leading-6 text-white outline-none placeholder:text-white/30 disabled:opacity-50"
        />

        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2 text-xs text-white/45">
            {voiceControls}
            <span className="hidden sm:inline">Shift + Enter untuk baris baru</span>
          </div>

          <button
            type="submit"
            disabled={disabled || !value.trim()}
            className="aira-control inline-flex items-center gap-2 rounded-full border-0 bg-gradient-to-r from-violet-500 to-pink-500 px-4 py-2 text-xs font-semibold text-white shadow-lg shadow-pink-500/10 transition duration-200 hover:-translate-y-0.5 hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:translate-y-0"
          >
            <span>{disabled ? "Memproses" : "Kirim"}</span>
            <span aria-hidden="true">↗</span>
          </button>
        </div>
      </form>
    </div>
  );
}
