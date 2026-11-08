export default function DateField({ field, value, onChange, error }) {
  return (
    <div>
      {field.label && (
        <label className="text-xs font-medium text-white/70 mb-1.5 block">
          {field.label}
          {field.required && <span className="text-[#EF4444] ml-1">*</span>}
        </label>
      )}
      <input
        type="date"
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        min={field.min_date}
        max={field.max_date}
        disabled={field.disabled}
        className="w-full bg-[#111827] hover:bg-[#1F2937] border border-white/10 rounded-2xl px-3.5 py-2.5 text-sm text-white outline-none focus:border-[#2563EB] focus:ring-1 focus:ring-[#2563EB]/40 transition disabled:opacity-50 [color-scheme:dark]"
      />
      {error && <p className="text-[11px] text-[#EF4444] mt-1">{error}</p>}
    </div>
  );
}