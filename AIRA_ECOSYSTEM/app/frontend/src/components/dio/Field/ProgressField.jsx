// Field/ProgressField.jsx
export default function ProgressField({ field }) {
  const value = Math.max(0, Math.min(100, Number(field.value ?? field.percent ?? 0)));
  return (
    <div>
      {field.label && (
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-xs font-medium text-white/70">{field.label}</span>
          <span className="text-xs font-mono text-white/50">{Math.round(value)}%</span>
        </div>
      )}
      <div className="w-full h-2 rounded-pill bg-white/10 overflow-hidden">
        <div className="h-full rounded-pill bg-accent-gradient transition-[width]" style={{ width: `${value}%` }} />
      </div>
      {field.helper_text && <p className="text-[11px] text-white/40 mt-1.5">{field.helper_text}</p>}
    </div>
  );
}