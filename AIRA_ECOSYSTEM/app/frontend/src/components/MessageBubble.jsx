// AIRA_ECOSYSTEM/app/frontend/src/components/MessageBubble.jsx
import { useState } from "react";
import ToolStep from "./ToolStep.jsx";

function ProcessSteps({ steps }) {
  const [open, setOpen] = useState(false);

  if (!steps || steps.length === 0) return null;

  const toolCallCount = steps.filter((s) => s.type === "tool_call").length;
  const allOk = steps.every((s) => s.type !== "tool_call" || s.success);

  const summary =
    toolCallCount > 0
      ? `${toolCallCount} tool${toolCallCount > 1 ? "s" : ""} digunakan`
      : "Proses selesai";

  return (
    <div className="mb-2">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 text-xs text-white/50 hover:text-white/80 transition px-1 py-1"
      >
        <span
          className={`inline-block w-1.5 h-1.5 rounded-full ${
            allOk ? "bg-emerald-400" : "bg-amber-400"
          }`}
        />
        <span>{summary}</span>
        <svg
          viewBox="0 0 24 24"
          fill="none"
          className={`transition-transform ${open ? "rotate-180" : ""}`}
          style={{ width: 12, height: 12 }}
        >
          <path
            d="m6 9 6 6 6-6"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>

      {open && (
        <div className="mt-1.5 space-y-1.5">
          {steps.map((step, i) => (
            <ToolStep key={i} step={step} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function MessageBubble({ role, content, steps, isNew }) {
  const isUser = role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} ${isNew ? "reveal-fade" : ""}`}>
      <div className={`max-w-[88%] sm:max-w-[75%] ${isUser ? "" : "w-full"}`}>
        {!isUser && <ProcessSteps steps={steps} />}

        <div
          className={`rounded-xl2 px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap break-words
            ${
              isUser
                ? "bg-accent-gradient text-white"
                : "bg-card border border-border text-white/90"
            }`}
        >
          {content}
        </div>
      </div>
    </div>
  );
}