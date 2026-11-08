export default function PresetCard({ preset, onApply, onDuplicate }) {
  return (
    <div
      className={`rounded-xl2 border p-4 flex flex-col gap-2 ${
        preset.is_active ? "border-accent bg-accent/5" : "border-border bg-white/5"
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-semibold text-white truncate">{preset.name}</span>
        <div className="flex gap-1 shrink-0">
          {preset.is_builtin && (
            <span className="text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full bg-white/10 text-white/50">
              Built-in
            </span>
          )}
          {preset.is_active && (
            <span className="text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full bg-accent/20 text-accent-light border border-accent/30">
              Active
            </span>
          )}
        </div>
      </div>

      <p className="text-xs text-white/50 flex-1">{preset.description}</p>

      <div className="flex gap-1.5">
        <button
          onClick={onApply}
          disabled={preset.is_active}
          className="text-[11px] px-2.5 py-1.5 rounded-lg bg-accent-gradient text-white font-medium disabled:opacity-40"
        >
          Apply
        </button>
        <button
          onClick={onDuplicate}
          className="text-[11px] px-2.5 py-1.5 rounded-lg bg-white/5 text-white/70 hover:text-white"
        >
          Duplicate
        </button>
      </div>
    </div>
  );
}