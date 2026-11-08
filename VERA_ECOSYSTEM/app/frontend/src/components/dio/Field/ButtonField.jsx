const STYLE_CLASSES = {
  primary: "bg-[#2563EB] hover:bg-[#2563EB]/90 text-white",
  secondary: "bg-[#1F2937] hover:bg-[#1F2937]/80 text-white border border-white/10",
  danger: "bg-[#EF4444] hover:bg-[#EF4444]/90 text-white",
  ghost: "bg-transparent hover:bg-white/5 text-white/60 hover:text-white",
};

export default function ButtonField({ field, onAction }) {
  return (
    <button
      type="button"
      disabled={field.disabled}
      onClick={() => onAction?.(field.action_id || field.id)}
      className={`text-sm font-medium px-4 py-2 rounded-2xl transition disabled:opacity-40 ${
        STYLE_CLASSES[field.style] || STYLE_CLASSES.secondary
      }`}
    >
      {field.label}
    </button>
  );
}