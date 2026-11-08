export default function SelectField({ field, value, onChange, error }) {
  return (
    <div>
      {field.label && (
        <label className="text-xs font-medium text-white/70 mb-1.5 block">
          {field.label}
          {field.required && <span className="text-[#EF4444] ml-1">*</span>}
        </label>
      )}
      <select
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        disabled={field.disabled}
        className="w-full bg-[#111827] hover:bg-[#1F2937] border border-white/10 rounded-2xl px-3.5 py-2.5 text-sm text-white outline-none focus:border-[#2563EB] focus:ring-1 focus:ring-[#2563EB]/40 transition disabled:opacity-50"
      >
        <option value="" disabled>
          {field.placeholder || "Pilih salah satu..."}
        </option>
        {(field.options || []).map((opt, idx) => {
          const val = typeof opt === "object" && opt !== null ? opt.value : opt;
          const lbl = typeof opt === "object" && opt !== null ? (opt.label || opt.value) : opt;
          return (
            <option key={val ?? idx} value={val}>
              {lbl}
            </option>
          );
        })}
      </select>
      {error && <p className="text-[11px] text-[#EF4444] mt-1">{error}</p>}
    </div>
  );
}