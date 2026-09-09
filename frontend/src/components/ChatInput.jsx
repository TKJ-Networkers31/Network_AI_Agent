import { useRef, useState } from "react";
import SlashMenu from "./SlashMenu.jsx";

export default function ChatInput({
  onSend,
  disabled,
  tools = [],
  voiceControls,
}) {
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
      {showSlash && tools.length > 0 && (
        <SlashMenu tools={tools} query={slashQuery} onPick={pickTool} />
      )}

      <form
        onSubmit={submit}
        className="flex items-end gap-2 bg-card border border-border rounded-xl2 p-2"
      >
        {voiceControls}

        <textarea
          ref={textareaRef}
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          rows={1}
          placeholder="Tanya sesuatu, ketik '/' untuk tool, atau tekan mic untuk bicara..."
          className="flex-1 bg-transparent resize-none outline-none px-3 py-2 text-white placeholder-white/30 max-h-32"
        />
        <button
          type="submit"
          disabled={disabled || !value.trim()}
          className="shrink-0 bg-accent-gradient text-white text-sm font-semibold px-4 py-2.5 rounded-lg disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {disabled ? "..." : "Kirim"}
        </button>
      </form>
    </div>
  );
}
