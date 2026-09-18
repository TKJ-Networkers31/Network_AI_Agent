import { useState } from "react";
import ToolStep from "./ToolStep.jsx";
import Markdown from "./Markdown.jsx";

function ProcessSteps({ steps }) {
  const [open, setOpen] = useState(false);
  if (!steps || steps.length === 0) return null;

  const toolCallCount = steps.filter((step) => step.type === "tool_call").length;
  const allOk = steps.every((step) => step.type !== "tool_call" || step.success);
  const summary = toolCallCount > 0
    ? `${toolCallCount} tool${toolCallCount > 1 ? "s" : ""} digunakan`
    : "Proses selesai";

  return (
    <div className="mb-3">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.03] px-3 py-1.5 text-xs text-white/55 transition duration-200 hover:border-pink-300/30 hover:text-white/85"
      >
        <span className={`h-1.5 w-1.5 rounded-full ${allOk ? "bg-emerald-400" : "bg-amber-400"}`} />
        <span>{summary}</span>
        <span className={`transition-transform ${open ? "rotate-180" : ""}`} aria-hidden="true">⌄</span>
      </button>

      {open && (
        <div className="mt-2 space-y-2 rounded-2xl border border-white/8 bg-black/10 p-3">
          {steps.map((step, index) => <ToolStep key={index} step={step} />)}
        </div>
      )}
    </div>
  );
}

export default function MessageBubble({ role, content, steps, isNew }) {
  const isUser = role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} ${isNew ? "reveal-fade" : ""}`}>
      <div className={`${isUser ? "max-w-[88%] sm:max-w-[75%]" : "w-full max-w-3xl"}`}>
        {!isUser && <ProcessSteps steps={steps} />}
        <div className={isUser
          ? "rounded-[20px] rounded-br-md border border-pink-300/20 bg-gradient-to-br from-violet-500 to-pink-500 px-4 py-3 text-sm leading-6 text-white shadow-lg shadow-pink-500/10"
          : "rounded-[20px] rounded-bl-md border border-white/10 bg-white/[0.035] px-4 py-4 text-sm leading-6 text-white/90 shadow-xl shadow-black/10"}
        >
          {isUser ? <span className="whitespace-pre-wrap break-words">{content}</span> : <Markdown content={content} />}
        </div>
      </div>
    </div>
  );
}
