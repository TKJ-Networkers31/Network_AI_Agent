// AIRA_ECOSYSTEM/app/frontend/src/components/LiveSteps.jsx
const CATEGORY_STYLE = {
  network:   { icon: "🌐", color: "text-sky-300",     ring: "border-sky-400/60" },
  mikrotik:  { icon: "📡", color: "text-emerald-300",  ring: "border-emerald-400/60" },
  snmp:      { icon: "📊", color: "text-amber-300",    ring: "border-amber-400/60" },
  web:       { icon: "🔎", color: "text-fuchsia-300",  ring: "border-fuchsia-400/60" },
  memory:    { icon: "🧠", color: "text-violet-300",   ring: "border-violet-400/60" },
  inventory: { icon: "🗂️", color: "text-cyan-300",     ring: "border-cyan-400/60" },
  vision:    { icon: "👁️", color: "text-pink-300",     ring: "border-pink-400/60" },
  tool:      { icon: "⚙️", color: "text-white/70",     ring: "border-white/40" },
};

function ToolLiveCard({ step }) {
  const style = CATEGORY_STYLE[step.category] || CATEGORY_STYLE.tool;
  const running = step.success === null;

  return (
    <div className="pop-in flex items-center gap-3 bg-white/5 border border-border rounded-lg px-3 py-2">
      <div className="relative shrink-0 w-6 h-6 flex items-center justify-center">
        {running ? (
          <span
            className={`spin-ring absolute inset-0 rounded-full border-2 border-transparent border-t-current ${style.color}`}
          />
        ) : (
          <span className={`check-pop text-sm ${step.success ? "text-emerald-400" : "text-red-400"}`}>
            {step.success ? "✓" : "✕"}
          </span>
        )}
        {running && <span className="text-xs">{style.icon}</span>}
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className={`text-xs font-semibold ${style.color}`}>{step.category}</span>
          <span className="text-white/30">→</span>
          <span className="text-sm text-white/85 truncate">{step.name}</span>
        </div>
      </div>

      {typeof step.duration === "number" && (
        <span className="shrink-0 text-[10px] text-white/30 font-mono">{step.duration}s</span>
      )}
    </div>
  );
}

function ThinkingBubble({ phase }) {
  return (
    <div className="pop-in flex items-center gap-2.5 px-1 py-1">
      <span className="relative flex h-2.5 w-2.5">
        <span className="pulse-ring-soft absolute inline-flex h-full w-full rounded-full bg-accent-light opacity-60" />
        <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-accent-light" />
      </span>
      <span className="shimmer-text text-sm font-medium">{phase}</span>
    </div>
  );
}

export default function LiveSteps({ phase, liveTools }) {
  if (!phase && liveTools.length === 0) return null;

  return (
    <div className="bg-card border border-border rounded-xl2 px-4 py-3 space-y-2 min-w-[240px] shadow-lg shadow-black/20">
      {phase && <ThinkingBubble phase={phase} />}

      {liveTools.length > 0 && (
        <div className="space-y-1.5 pt-1">
          {liveTools.map((step, i) => (
            <ToolLiveCard key={`${step.name}-${i}`} step={step} />
          ))}
        </div>
      )}
    </div>
  );
}