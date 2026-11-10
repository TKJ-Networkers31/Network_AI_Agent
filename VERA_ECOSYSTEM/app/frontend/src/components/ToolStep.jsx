import { useState } from "react";
import { ChevronRight, ChevronDown } from "lucide-react";

const CATEGORY_COLOR = {
  network: "text-sky-300",
  mikrotik: "text-emerald-300",
  snmp: "text-amber-300",
  web: "text-fuchsia-300",
  memory: "text-violet-300",
  inventory: "text-cyan-300",
  vision: "text-pink-300",
  tool: "text-white/60",
};

export default function ToolStep({ step }) {
  const [expanded, setExpanded] = useState(false);

  if (step.type === "confirmation_required") {
    return (
      <div className="text-xs px-3 py-2 rounded-lg bg-yellow-500/10 border border-yellow-500/20 text-yellow-300">
        ⚠ Tool <b>{step.name}</b> butuh konfirmasi manual — dilewati di web,
        jalankan lewat terminal kalau perlu.
      </div>
    );
  }

  if (step.type === "limit_reached") {
    return (
      <div className="text-xs px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/20 text-red-300">
        ⛔ {step.message}
      </div>
    );
  }

  const color = CATEGORY_COLOR[step.category] || "text-white/60";
  const ok = step.success;
  const args = step.args || step.parameters;
  const output = step.output || step.result || step.error;
  const hasDetails = Boolean(args || output);

  return (
    <div className="rounded-lg bg-white/[0.03] border border-border/70 overflow-hidden text-xs">
      <div
        role="button"
        tabIndex={0}
        onClick={() => hasDetails && setExpanded(!expanded)}
        className={`px-3 py-2 flex items-center gap-2 select-none ${
          hasDetails ? "cursor-pointer hover:bg-white/[0.04] transition" : ""
        }`}
      >
        <span className="shrink-0">{ok ? "✅" : "❌"}</span>
        <span className={`font-semibold ${color}`}>{step.category}</span>
        <span className="text-white/30">→</span>
        <span className="text-white/85 font-mono truncate">{step.name}</span>

        {typeof step.duration === "number" && (
          <span className="ml-auto text-white/40 font-mono text-[11px]">{step.duration}s</span>
        )}

        {hasDetails && (
          <span className="text-white/40 hover:text-white transition shrink-0 ml-1">
            {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </span>
        )}
      </div>

      {expanded && hasDetails && (
        <div className="px-3 pb-2.5 pt-1 border-t border-white/5 bg-black/30 space-y-2 text-[11px] font-mono animate-in fade-in duration-100">
          {args && (
            <div>
              <span className="text-white/40 block text-[10px] uppercase font-sans font-semibold mb-0.5">
                Parameters
              </span>
              <pre className="bg-black/40 rounded p-2 text-cyan-300/90 overflow-x-auto whitespace-pre-wrap max-h-32">
                {typeof args === "object" ? JSON.stringify(args, null, 2) : String(args)}
              </pre>
            </div>
          )}
          {output && (
            <div>
              <span className="text-white/40 block text-[10px] uppercase font-sans font-semibold mb-0.5">
                Output
              </span>
              <pre className="bg-black/40 rounded p-2 text-neutral-300 overflow-x-auto whitespace-pre-wrap max-h-48">
                {typeof output === "object" ? JSON.stringify(output, null, 2) : String(output)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
