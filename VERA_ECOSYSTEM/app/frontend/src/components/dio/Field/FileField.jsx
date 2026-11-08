import { useRef, useState } from "react";

export default function FileField({ field, value, onChange, error }) {
  const inputRef = useRef(null);
  const [fileName, setFileName] = useState(value?.name || "");

  function handleChange(e) {
    const file = e.target.files?.[0];
    if (!file) return;

    setFileName(file.name);
    // Belum upload ke server - hanya metadata dasar. Backend yang
    // menangani upload sesungguhnya lewat mekanisme terpisah.
    onChange({ name: file.name, size: file.size, type: file.type });
  }

  return (
    <div>
      {field.label && (
        <label className="text-xs font-medium text-white/70 mb-1.5 block">
          {field.label}
          {field.required && <span className="text-[#EF4444] ml-1">*</span>}
        </label>
      )}

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="text-xs px-3.5 py-2.5 rounded-2xl bg-[#111827] hover:bg-[#1F2937] border border-white/10 text-white/80 transition"
        >
          Pilih File
        </button>
        <span className="text-xs text-white/40 truncate">
          {fileName || "Belum ada file dipilih."}
        </span>
      </div>

      <input ref={inputRef} type="file" accept={field.accept} onChange={handleChange} className="hidden" />

      {error && <p className="text-[11px] text-[#EF4444] mt-1">{error}</p>}
    </div>
  );
}