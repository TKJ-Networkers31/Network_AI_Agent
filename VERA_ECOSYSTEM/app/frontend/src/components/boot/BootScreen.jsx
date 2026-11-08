import React from "react";
import BrandEmblem from "../BrandEmblem.jsx";

export default function BootScreen({ label = "Menginisialisasi VERA..." }) {
  return (
    <div className="fixed inset-0 bg-vera-navy-dark flex flex-col items-center justify-center z-50 select-none">
      <div className="relative flex items-center justify-center mb-6">
        <span
          className="absolute inset-0 rounded-full bg-core-glow blur-2xl opacity-40 animate-pulse pointer-events-none"
          aria-hidden="true"
        />
        <BrandEmblem size={72} glow className="relative z-10" />
      </div>
      <div className="flex items-center gap-2 mb-2">
        <span className="text-xl font-bold tracking-[0.2em] text-white">VERA</span>
        <span className="text-xs font-semibold text-vera-cyan tracking-wider uppercase bg-vera-cyan/10 border border-vera-cyan/20 px-2 py-0.5 rounded-full">
          NOC Core
        </span>
      </div>
      <p className="text-xs font-mono text-text-secondary animate-pulse">{label}</p>
    </div>
  );
}
