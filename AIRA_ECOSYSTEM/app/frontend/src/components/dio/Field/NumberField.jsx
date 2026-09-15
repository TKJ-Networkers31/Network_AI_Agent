export default function NumberField({ field, value, onChange, error }) {
  return (
    <div>
      {field.label && (
        <label className="text-xs font-medium text-white/70 mb-1.5 block">
          {field.label}
          {field.required && <span className="text-[#EF4444] ml-1">*</span>}
        </label>
      )}
      <input
        type="number"
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))}
        placeholder={field.placeholder}
        min={field.min}
        max={field.max}
        step={field.step || 1}
        disabled={field.disabled}
        className="w-full bg-[#111827] hover:bg-[#1F2937] border border-white/10 rounded-2xl px-3.5 py-2.5 text-sm text-white placeholder-white/30 outline-none focus:border-[#2563EB] focus:ring-1 focus:ring-[#2563EB]/40 transition disabled:opacity-50"
      />
      {field.helper_text && !error && (
        <p className="text-[11px] text-white/40 mt-1">{field.helper_text}</p>
      )}
      {error && <p className="text-[11px] text-[#EF4444] mt-1">{error}</p>}
    </div>
  );
}