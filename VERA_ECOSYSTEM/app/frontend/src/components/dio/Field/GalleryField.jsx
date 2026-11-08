// Field/GalleryField.jsx
import { useState } from "react";

export default function GalleryField({ field }) {
  const images = Array.isArray(field.images) ? field.images : [];
  const [failedIdx, setFailedIdx] = useState(() => new Set());
  if (images.length === 0) return null;

  return (
    <div>
      {field.label && <label className="text-xs font-medium text-white/70 mb-1.5 block">{field.label}</label>}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
        {images.map((img, i) =>
          failedIdx.has(i) ? null : (
            <figure key={img.url || i} className="m-0">
              <img src={img.url} alt={img.alt || img.caption || ""} loading="lazy" referrerPolicy="no-referrer"
                onError={() => setFailedIdx((prev) => new Set(prev).add(i))}
                className="w-full h-28 object-cover rounded-2xl border border-white/10 bg-black/20" />
              {img.caption && <figcaption className="text-[10px] text-white/40 mt-1 truncate">{img.caption}</figcaption>}
            </figure>
          )
        )}
      </div>
      {field.caption && <p className="text-[11px] text-white/40 mt-1.5">{field.caption}</p>}
    </div>
  );
}