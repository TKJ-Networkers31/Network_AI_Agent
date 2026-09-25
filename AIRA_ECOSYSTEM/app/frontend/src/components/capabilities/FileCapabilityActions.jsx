// src/components/capabilities/FileCapabilityActions.jsx
//
// SPRINT 2.7 - W8 (Dynamic Capability UI)
//
// Kapabilitas area "file_actions" - menu "..." kecil yang bisa ditempel di
// baris file mana pun (mis. daftar file di Workspace). Berdiri sendiri
// (tidak bergantung pada CapabilityContext global) karena konteksnya adalah
// satu file (`filePath`), bukan percakapan.
//
// CATATAN INTEGRASI: paket W8 ini tidak menyertakan file daftar/file-tree
// Workspace itu sendiri (tidak ada di berkas yang diberikan untuk sprint
// ini), jadi komponen ini BELUM dipasang otomatis di baris file mana pun.
// Cara pakai di komponen file-list yang sudah ada, tanpa mengubah apa pun
// di dalamnya selain menambah satu elemen di baris file:
//
//   <FileCapabilityActions filePath={file.path} onChanged={refreshFileTree} />
//
// Lihat "Limitations" di laporan pengiriman.

import { useEffect, useRef, useState } from "react";
import { useCapabilities } from "../../hooks/useCapabilities.js";
import CapabilityIcon from "./CapabilityIcon.jsx";
import { invokeCapability } from "../../utils/capabilityInvoke.js";
import { useToast } from "../Toast.jsx";

export default function FileCapabilityActions({ filePath, onChanged }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);
  const { notify } = useToast();

  const { capabilities, loading } = useCapabilities("file_actions", {
    file_path: filePath ?? undefined,
  });

  useEffect(() => {
    if (!open) return undefined;

    function onDocClick(e) {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false);
    }

    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  async function handlePick(cap) {
    setOpen(false);
    await invokeCapability(cap, { notify, onWorkspaceChange: onChanged });
  }

  if (!loading && capabilities.length === 0) return null;

  return (
    <div ref={rootRef} className="relative inline-block">
      <button
        type="button"
        title="Aksi file"
        aria-label="Aksi file"
        onClick={() => setOpen((v) => !v)}
        className="w-7 h-7 inline-flex items-center justify-center rounded-pill text-white/40 hover:text-white hover:bg-white/10 transition"
      >
        <svg viewBox="0 0 24 24" fill="currentColor" className="w-3.5 h-3.5">
          <circle cx="5" cy="12" r="1.6" />
          <circle cx="12" cy="12" r="1.6" />
          <circle cx="19" cy="12" r="1.6" />
        </svg>
      </button>

      {open && (
        <div className="absolute right-0 mt-1 min-w-[9rem] rounded-xl2 border border-border bg-surface/95 backdrop-blur-xl shadow-card py-1 z-20">
          {capabilities.map((cap) => (
            <button
              key={cap.id}
              type="button"
              disabled={cap.enabled === false}
              title={cap.enabled === false ? cap.disabled_reason || "Tidak tersedia" : undefined}
              onClick={() => handlePick(cap)}
              className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-white/70 hover:text-white hover:bg-white/10 transition disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:bg-transparent"
            >
              <CapabilityIcon name={cap.icon} className="w-3.5 h-3.5" />
              <span className="truncate">{cap.label}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
