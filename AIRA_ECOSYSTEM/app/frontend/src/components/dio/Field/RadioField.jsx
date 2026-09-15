export default function RadioField({ field, value, onChange, error }) {
  return (
    <div>
      {field.label && (
        <label className="text-xs font-medium text-white/70 mb-2 block">
          {field.label}
          {field.required && <span className="text-[#EF4444] ml-1">*</span>}
        </label>
      )}
      <div className="space-y-1.5">
        {(field.options || []).map((opt) => (
          <label
            key={opt.value}
            className="flex items-center gap-2.5 bg-[#111827] hover:bg-[#1F2937] border border-white/10 rounded-2xl px-3.5 py-2.5 text-sm text-white/85 cursor-pointer transition"
          >
            <input
              type="radio"
              name={field.id}
              value={opt.value}
              checked={value === opt.value}
              onChange={() => onChange(opt.value)}
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