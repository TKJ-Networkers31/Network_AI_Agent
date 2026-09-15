export default function SwitchField({ field, value, onChange, error }) {
  const checked = Boolean(value);

  return (
    <div>
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm text-white/85">
          {field.label}
          {field.required && <span className="text-[#EF4444] ml-1">*</span>}
        </span>
        <button
          type="button"
          role="switch"
          aria-checked={checked}
          onClick={() => onChange(!checked)}
          className={`relative w-11 h-6 rounded-full transition shrink-0 ${
            checked ? "bg-[#2563EB]" : "bg-white/10"
          }`}
        >
          <span
            className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white transition-transform ${
              checked ? "translate-x-5" : "translate-x-0"
            }`}
          />
        </button>
      </div>
      {error && <p className="text-[11px] text-[#EF4444] mt-1">{error}</p>}
    </div>
  );
}