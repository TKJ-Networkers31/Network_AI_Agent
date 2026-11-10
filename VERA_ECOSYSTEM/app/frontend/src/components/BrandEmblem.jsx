// src/components/BrandEmblem.jsx
//
// VERA Network Core Brand Emblem
// Geometric V-symbol representing network topology nodes, conduction paths,
// and central intelligence nexus.
//
// Conforms to brand directives:
// - Zero flower, cartoon, or mascot imagery.
// - Pure vector SVG rendering across all DPI displays.
// - Accessible contrast and scalability.

import React from "react";

export const EMBLEM_SRC = "/assets/brand/vera-symbol-core.svg";
export const EMBLEM_SCALE = 1.0;

export default function BrandEmblem({ size = 32, glow = false, className = "" }) {
  const px = Math.round(size * EMBLEM_SCALE);

  return (
    <div
      className={`shrink-0 flex items-center justify-center select-none ${className}`}
      style={{ width: px, height: px }}
    >
      <svg
        viewBox="0 0 120 120"
        width={px}
        height={px}
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className={glow ? "drop-shadow-[0_0_12px_rgba(84,214,255,0.45)]" : ""}
        aria-label="VERA Network Core"
      >
        <defs>
          <linearGradient id="vera-emblem-grad" x1="20" y1="20" x2="100" y2="100" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#38BDF8" />
            <stop offset="60%" stopColor="#8B5CF6" />
            <stop offset="100%" stopColor="#6D28D9" />
          </linearGradient>
          <linearGradient id="vera-emblem-core" x1="50" y1="38" x2="70" y2="58" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#38BDF8" />
            <stop offset="100%" stopColor="#8B5CF6" />
          </linearGradient>
        </defs>

        {/* Network Conduction Matrix Lines */}
        <line x1="24" y1="28" x2="44" y2="58" stroke="url(#vera-emblem-grad)" strokeWidth="4.5" strokeLinecap="round" />
        <line x1="96" y1="28" x2="76" y2="58" stroke="url(#vera-emblem-grad)" strokeWidth="4.5" strokeLinecap="round" />
        <line x1="44" y1="58" x2="60" y2="96" stroke="url(#vera-emblem-grad)" strokeWidth="4.5" strokeLinecap="round" />
        <line x1="76" y1="58" x2="60" y2="96" stroke="url(#vera-emblem-grad)" strokeWidth="4.5" strokeLinecap="round" />

        {/* Internal Nexus Bridge Lines (Intelligence Mesh) */}
        <line x1="44" y1="58" x2="60" y2="48" stroke="#38BDF8" strokeWidth="2.2" strokeDasharray="3 3" opacity="0.85" />
        <line x1="76" y1="58" x2="60" y2="48" stroke="#38BDF8" strokeWidth="2.2" strokeDasharray="3 3" opacity="0.85" />
        <line x1="60" y1="48" x2="60" y2="96" stroke="#38BDF8" strokeWidth="2.2" opacity="0.8" />
        <line x1="24" y1="28" x2="60" y2="48" stroke="#8B5CF6" strokeWidth="1.8" opacity="0.5" />
        <line x1="96" y1="28" x2="60" y2="48" stroke="#8B5CF6" strokeWidth="1.8" opacity="0.5" />

        {/* Outer Network Nodes */}
        <circle cx="24" cy="28" r="5.5" fill="#000000" stroke="#38BDF8" strokeWidth="3" />
        <circle cx="96" cy="28" r="5.5" fill="#000000" stroke="#38BDF8" strokeWidth="3" />
        <circle cx="44" cy="58" r="5" fill="#000000" stroke="#8B5CF6" strokeWidth="3" />
        <circle cx="76" cy="58" r="5" fill="#000000" stroke="#8B5CF6" strokeWidth="3" />

        {/* Apex Gateway Node */}
        <circle cx="60" cy="96" r="6.5" fill="#000000" stroke="#8B5CF6" strokeWidth="3.5" />
        <circle cx="60" cy="96" r="2.5" fill="#38BDF8" />

        {/* Central Intelligence Nexus Core */}
        <circle cx="60" cy="48" r="10" fill="#000000" stroke="#38BDF8" strokeWidth="2.5" />
        <circle cx="60" cy="48" r="6.5" fill="url(#vera-emblem-core)" />
        <circle cx="60" cy="48" r="2.2" fill="#F8FAFC" />
      </svg>
    </div>
  );
}
