export default function CheckboxField({ field, value, onChange, error }) {
  if (field.options && field.options.length > 0) {
    const selected = Array.isArray(value) ? value : [];

    function toggle(optValue) {
      onChange(
        selected.includes(optValue)
          ? selected.filter((v) => v !== optValue)
          : [...selected, optValue]
      );
    }

    return (
      <div>
        {field.label && (
          <label className="text-xs font-medium text-white/70 mb-2 block">
            {field.label}
            {field.required && <span className="text-[#EF4444] ml-1">*</span>}
          </label>
        )}
        <div className="space-y-1.5">
          {field.options.map((opt) => (
            <label
              key={opt.value}
              className="flex items-center gap-2.5 bg-[#111827] hover:bg-[#1F2937] border border-white/10 rounded-2xl px-3.5 py-2.5 text-sm text-white/85 cursor-pointer transition"
            >
              <input
                type="checkbox"
                checked={selected.includes(opt.value)}
                onChange={() => toggle(opt.value)}
                className="accent-[#2563EB]"
              />
              {opt.label}
            </label>
          ))}
        </div>
        {error && <p className="text-[11px] text-[#EF4444] mt-1">{error}</p>}
      </div>
    );
  }

  return (
    <div>
      <label className="flex items-center gap-2.5 text-sm text-white/85 cursor-pointer">
        <input
          type="checkbox"
          checked={Boolean(value)}
          onChange={(e) => onChange(e.target.checked)}
          className="accent-[#2563EB] w-4 h-4"
        />
        {field.label}
        {field.required && <span className="text-[#EF4444] ml-1">*</span>}
      </label>
      {error && <p className="text-[11px] text-[#EF4444] mt-1">{error}</p>}
    </div>
  );
}