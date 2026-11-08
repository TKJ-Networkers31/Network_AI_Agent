// src/components/VeraLogo.jsx
//
// Reusable VERA Vector Logo Component
// Supports:
// - "horizontal": Full wordmark + subtitle + Network Core emblem
// - "symbol": Network Core geometric V only
// - "dark" / "light" / "monochrome" themes

import React from "react";
import BrandEmblem from "./BrandEmblem.jsx";

export default function VeraLogo({
  variant = "horizontal",
  size = 32,
  subtitle = "Network Intelligence",
  className = "",
}) {
  if (variant === "symbol") {
    return <BrandEmblem size={size} className={className} />;
  }

  return (
    <div className={`flex items-center gap-3 select-none ${className}`}>
      <BrandEmblem size={size} glow />
      <div className="flex flex-col leading-none">
        <div className="flex items-center gap-1.5">
          <span className="font-extrabold text-white text-lg tracking-[0.18em] font-sans">
            VERA
          </span>
          <span className="text-[9px] font-semibold tracking-wider text-vera-cyan bg-vera-cyan/10 border border-vera-cyan/20 px-1.5 py-0.5 rounded-full uppercase">
            NOC
          </span>
        </div>
        {subtitle && (
          <span className="text-[9.5px] font-medium tracking-[0.16em] text-text-secondary uppercase mt-0.5">
            {subtitle}
          </span>
        )}
      </div>
    </div>
  );
}
