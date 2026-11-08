import React from "react";
import BrandEmblem from "../BrandEmblem.jsx";

export default function SplashScreen() {
  return (
    <div className="fixed inset-0 bg-vera-navy-dark flex flex-col items-center justify-center select-none z-50">
      <div className="relative mb-4">
        <span
          className="absolute inset-0 rounded-full bg-core-glow blur-2xl opacity-40 animate-pulse pointer-events-none"
          aria-hidden="true"
        />
        <BrandEmblem size={96} glow className="relative z-10" />
      </div>
      <div className="flex items-center gap-2">
        <span className="text-2xl font-black tracking-[0.22em] text-white">VERA</span>
        <span className="text-[10px] font-mono tracking-widest text-vera-cyan uppercase border border-vera-cyan/30 px-2 py-0.5 rounded-full bg-vera-cyan/10">
          ENTERPRISE
        </span>
      </div>
    </div>
  );
}
