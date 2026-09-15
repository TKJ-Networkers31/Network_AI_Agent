const VARIANT_STYLES = {
  info: { bg: "bg-[#2563EB]/10", border: "border-[#2563EB]/30", text: "text-[#93C5FD]", icon: "ℹ" },
  success: { bg: "bg-[#10B981]/10", border: "border-[#10B981]/30", text: "text-[#6EE7B7]", icon: "✓" },
  warning: { bg: "bg-[#F59E0B]/10", border: "border-[#F59E0B]/30", text: "text-[#FCD34D]", icon: "⚠" },
  danger: { bg: "bg-[#EF4444]/10", border: "border-[#EF4444]/30", text: "text-[#FCA5A5]", icon: "✕" },
};

export default function InfoField({ field }) {
  const variant = VARIANT_STYLES[field.variant] || VARIANT_STYLES.info;

  return (
    <div
      className={`flex items-start gap-2.5 rounded-2xl border px-3.5 py-3 text-sm ${variant.bg} ${variant.border} ${variant.text}`}
    >
      <span className="shrink-0 mt-0.5">{variant.icon}</span>
      <div>
        {field.label && <div className="font-semibold mb-0.5">{field.label}</div>}
        <p className="leading-relaxed">{field.text}</p>
      </div>
    </div>
  );
}