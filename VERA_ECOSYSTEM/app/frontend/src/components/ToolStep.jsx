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

  return (
    <div className="text-xs px-3 py-2 rounded-lg bg-white/5 border border-border flex items-center gap-2">
      <span>{ok ? "✅" : "❌"}</span>
      <span className={`font-medium ${color}`}>{step.category}</span>
      <span className="text-white/40">→</span>
      <span className="text-white/80">{step.name}</span>
      {typeof step.duration === "number" && (
        <span className="ml-auto text-white/30">{step.duration}s</span>
      )}
    </div>
  );
}
