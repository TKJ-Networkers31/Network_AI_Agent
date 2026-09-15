const STYLE_CLASSES = {
  primary: "bg-[#2563EB] hover:bg-[#2563EB]/90 text-white",
  secondary: "bg-[#1F2937] hover:bg-[#1F2937]/80 text-white border border-white/10",
  danger: "bg-[#EF4444] hover:bg-[#EF4444]/90 text-white",
  ghost: "bg-transparent hover:bg-white/5 text-white/60 hover:text-white",
};

// ActionBar TIDAK tahu "intent" tombol (submit/cancel/dst) - hanya
// membaca label, style, dan action_id dari schema, sesuai spec.
export default function ActionBar({ actions, onAction, disabled }) {
  if (!actions || actions.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center justify-end gap-2 pt-2">
      {actions.map((action) => (
        <button
          key={action.id}
          type="button"
          disabled={disabled || action.disabled}
          onClick={() => onAction(action.id)}
          className={`text-sm font-medium px-4 py-2 rounded-2xl transition disabled:opacity-40 disabled:cursor-not-allowed ${
            STYLE_CLASSES[action.style] || STYLE_CLASSES.secondary
          }`}
        >
          {action.label}
        </button>
      ))}
    </div>
  );
}