import React from "react";
import BrandEmblem from "../BrandEmblem.jsx";

export default function FirstBoot({ onDone }) {
  return (
    <div className="fixed inset-0 bg-vera-navy-dark flex flex-col items-center justify-center p-6 text-center select-none z-50">
      <div className="relative mb-6">
        <span
          className="absolute inset-0 rounded-full bg-core-glow blur-2xl opacity-40 animate-pulse pointer-events-none"
          aria-hidden="true"
        />
        <BrandEmblem size={84} glow className="relative z-10" />
      </div>
      <div className="max-w-md space-y-3">
        <h1 className="text-3xl font-extrabold text-white tracking-wider">Selamat datang di VERA</h1>
        <p className="text-xs font-mono text-vera-cyan tracking-widest uppercase">
          Understand · Monitor · Automate
        </p>
        <p className="text-xs text-text-secondary leading-relaxed pt-1">
          Platform kecerdasan infrastruktur jaringan yang mengintegrasikan monitoring real-time,
          visualisasi topologi multi-layer, dan diagnostik otonom berbasis AI.
        </p>
        <div className="pt-4">
          <button
            onClick={onDone}
            className="px-6 py-2.5 rounded-lg bg-vera-blue text-white text-xs font-semibold hover:bg-vera-blue/90 shadow-lg shadow-vera-blue/30 transition-all hover:-translate-y-0.5 active:translate-y-0"
          >
            Mulai Operasional
          </button>
        </div>
      </div>
    </div>
  );
}
