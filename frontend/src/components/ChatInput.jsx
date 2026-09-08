import { useState } from "react";

export default function ChatInput({ onSend, disabled }) {
  const [value, setValue] = useState("");

  function submit(e) {
    e.preventDefault();
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      submit(e);
    }
  }

  return (
    <form
      onSubmit={submit}
      className="flex items-end gap-2 bg-card border border-border rounded-xl2 p-2"
    >
      <textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        rows={1}
        placeholder="Tanya sesuatu ke agent... (Enter untuk kirim, Shift+Enter baris baru)"
        className="flex-1 bg-transparent resize-none outline-none text-sm px-3 py-2 text-white placeholder-white/30 max-h-32"
      />
      <button
        type="submit"
        disabled={disabled || !value.trim()}
        className="shrink-0 bg-accent-gradient text-white text-sm font-semibold px-4 py-2.5 rounded-lg disabled:opacity-40 disabled:cursor-not-allowed"
      >
        {disabled ? "..." : "Kirim"}
      </button>
    </form>
  );
}
