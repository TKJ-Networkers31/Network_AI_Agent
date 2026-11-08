const INPUT_CLASS =
  "w-full bg-[#111827] hover:bg-[#1F2937] border border-white/10 rounded-2xl px-3.5 py-2.5 text-sm text-white placeholder-white/30 outline-none focus:border-[#2563EB] focus:ring-1 focus:ring-[#2563EB]/40 transition disabled:opacity-50";

export default function TextField({ field, value, onChange, error }) {
  const isTextarea = field.type === "textarea";

  return (
    <div>
      {field.label && (
        <label className="text-xs font-medium text-white/70 mb-1.5 block">
          {field.label}
          {field.required && <span className="text-[#EF4444] ml-1">*</span>}
        </label>
      )}

      {isTextarea ? (
        <textarea
          value={value ?? ""}
          onChange={(e) => onChange(e.target.value)}
          placeholder={field.placeholder}
          rows={field.rows || 4}
          disabled={field.disabled}
          className={`${INPUT_CLASS} resize-none`}
        />
      ) : (
        <input
          type="text"
          value={value ?? ""}
          onChange={(e) => onChange(e.target.value)}
          placeholder={field.placeholder}
          disabled={field.disabled}
          className={INPUT_CLASS}
        />
      )}

      {field.helper_text && !error && (
        <p className="text-[11px] text-white/40 mt-1">{field.helper_text}</p>
      )}
      {error && <p className="text-[11px] text-[#EF4444] mt-1">{error}</p>}
    </div>
  );
}