// src/components/capabilities/CapabilityButton.jsx
//
// SPRINT 2.7 - W8 (Dynamic Capability UI)
//
// Renderer generik untuk SATU kapabilitas yang dikirim backend. Dipakai di
// semua area (Hero, Chat Input, Capability Dock, Message Actions). Tidak
// tahu apa arti kapabilitasnya - hanya menampilkan label/ikon dan
// mendelegasikan eksekusi ke `onInvoke` (lihat utils/capabilityInvoke.js).
//
// Dua varian visual, keduanya reuse pola yang sudah ada di codebase:
// - "icon"  : tombol bundar w-7 h-7, sama seperti ActionButton di
//             MessageBubble.jsx - dipakai di Chat Input & Message Actions.
// - "pill"  : chip berlabel dengan border-border, sama seperti gaya tombol
//             di ChatInput/EditBox - dipakai di Hero & Capability Dock.
//
// Disabled/unavailable: kapabilitas dengan `enabled === false` dirender
// redup (disabled:opacity-30, cursor-not-allowed) dan alasan dari backend
// (`disabled_reason`) ditaruh di title/tooltip - tidak ada logika baru di
// frontend untuk MEMUTUSKAN kapan sesuatu nonaktif, itu murni ikut backend.

import { useState } from "react";
import CapabilityIcon from "./CapabilityIcon.jsx";

export default function CapabilityButton({ capability, onInvoke, variant = "pill" }) {
  const [busy, setBusy] = useState(false);
  const disabled = capability.enabled === false || busy;

  async function handleClick() {
    if (disabled || !onInvoke) return;
    setBusy(true);
    try {
      await onInvoke(capability);
    } finally {
      setBusy(false);
    }
  }

  const title =
    capability.enabled === false
      ? capability.disabled_reason || `${capability.label} belum tersedia.`
      : capability.description || capability.label;

  if (variant === "icon") {
    return (
      <button
        type="button"
        title={title}
        aria-label={capability.label}
        onClick={handleClick}
        disabled={disabled}
        className="w-7 h-7 inline-flex items-center justify-center rounded-pill text-white/40 hover:text-white hover:bg-white/10 transition disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:bg-transparent disabled:hover:text-white/40"
      >
        {busy ? (
          <span className="w-3 h-3 rounded-pill border-2 border-white/40 border-t-white animate-spin" />
        ) : (
          <CapabilityIcon name={capability.icon} className="w-3.5 h-3.5" />
        )}
      </button>
    );
  }

  return (
    <button
      type="button"
      title={title}
      onClick={handleClick}
      disabled={disabled}
      className="shrink-0 inline-flex items-center gap-1.5 rounded-pill border border-border bg-white/[0.04] px-3 py-1.5 text-xs text-white/70 hover:text-white hover:bg-white/10 transition disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:bg-white/[0.04] disabled:hover:text-white/70"
    >
      {busy ? (
        <span className="w-3 h-3 rounded-pill border-2 border-white/40 border-t-white animate-spin" />
      ) : (
        <CapabilityIcon name={capability.icon} className="w-3.5 h-3.5" />
      )}
      <span className="whitespace-nowrap">{capability.label}</span>
    </button>
  );
}
