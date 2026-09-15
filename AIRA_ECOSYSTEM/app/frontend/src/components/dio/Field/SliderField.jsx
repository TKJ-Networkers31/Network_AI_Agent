export default function SliderField({ field, value, onChange, error }) {
  const current = value === "" || value === undefined ? field.default ?? field.min ?? 0 : value;

  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <label className="text-xs font-medium text-white/70">
          {field.label}
          {field.required && <span className="text-[#EF4444] ml-1">*</span>}
        </label>
        <span className="text-xs font-mono text-[#F9A8D4]">{current}</span>
      </div>
      <input
        type="range"
        min={field.min ?? 0}
        max={field.max ?? 100}
        step={field.step || 1}
        value={current}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-[#2563EB]"
      />
      {error && <p className="text-[11px] text-[#EF4444] mt-1">{error}</p>}
    </div>
  );
}