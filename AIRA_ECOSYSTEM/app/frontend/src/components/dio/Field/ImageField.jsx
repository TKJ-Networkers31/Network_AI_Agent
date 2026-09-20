// Field/ImageField.jsx
import { useState } from "react";

export default function ImageField({ field }) {
  const [failed, setFailed] = useState(false);
  const src = field.src || field.url;
  if (!src) return null;

  return (
    <div>
      {field.label && <label className="text-xs font-medium text-white/70 mb-1.5 block">{field.label}</label>}
      {failed ? (
        <div className="text-xs text-white/40 bg-white/5 border border-white/10 rounded-2xl px-3 py-2">
          Gambar gagal dimuat.
        </div>
      ) : (
        <img src={src} alt={field.alt || field.label || ""} loading="lazy" referrerPolicy="no-referrer"
          onError={() => setFailed(true)}
          className="w-full max-h-72 object-contain rounded-2xl border border-white/10 bg-black/20" />
      )}
      {field.caption && <p className="text-[11px] text-white/40 mt-1.5">{field.caption}</p>}
    </div>
  );
}