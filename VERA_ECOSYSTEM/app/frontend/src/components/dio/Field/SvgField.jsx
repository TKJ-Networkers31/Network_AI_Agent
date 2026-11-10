// Field/SvgField.jsx — render diagram SVG di dalam form (mis. layar review/approval)
import { useMemo } from "react";
import { buildSafeSvg } from "../../../platform/adaptive-experience/assets/svgBuilder.js";

export default function SvgField({ field }) {
  const built = useMemo(() => {
    const raw = field.svg || field.code;
    return buildSafeSvg(raw);
  }, [field.svg, field.code]);

  if (!built) return null;

  return (
    <div>
      {field.label && <label className="text-xs font-medium text-white/70 mb-1.5 block">{field.label}</label>}
      <div className="bg-[#050814] border border-white/10 rounded-2xl p-3 flex justify-center">
        <img
          src={built.uri}
          alt={field.label || "diagram"}
          className="max-w-full h-auto"
          style={{ maxWidth: built.maxWidth }}
        />
      </div>
      {field.caption && <p className="text-[11px] text-white/40 mt-1.5">{field.caption}</p>}
    </div>
  );
}