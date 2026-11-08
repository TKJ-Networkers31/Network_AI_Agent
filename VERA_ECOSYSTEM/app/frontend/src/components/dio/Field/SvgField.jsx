// Field/SvgField.jsx — render diagram SVG di dalam form (mis. layar review/approval)
import { useMemo } from "react";
import DOMPurify from "dompurify";

export default function SvgField({ field }) {
  const uri = useMemo(() => {
    const raw = field.svg || field.code;
    if (!raw) return null;
    const clean = DOMPurify.sanitize(raw, { USE_PROFILES: { svg: true, svgFilters: true } });
    return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(clean)}`;
  }, [field.svg, field.code]);

  if (!uri) return null;

  return (
    <div>
      {field.label && <label className="text-xs font-medium text-white/70 mb-1.5 block">{field.label}</label>}
      <div className="bg-[#F8FAFC] rounded-2xl p-3 flex justify-center">
        <img src={uri} alt={field.label || "diagram"} className="max-w-full h-auto" />
      </div>
      {field.caption && <p className="text-[11px] text-white/40 mt-1.5">{field.caption}</p>}
    </div>
  );
}