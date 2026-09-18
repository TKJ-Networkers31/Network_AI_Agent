// app/frontend/src/components/CopyButton.jsx
//
// Tombol salin serbaguna. Tanpa `label` tampil sebagai tombol ikon bulat
// (dipakai di aksi pesan); dengan `label` tampil sebagai tombol kecil
// beserta teks (dipakai di header blok kode).

import { useEffect, useRef, useState } from "react";
import { copyText } from "../utils/clipboard.js";
import { useToast } from "./Toast.jsx";

function CopyIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" style={{ width: 14, height: 14 }}>
      <rect x="9" y="9" width="11" height="11" rx="2.5" stroke="currentColor" strokeWidth="1.8" />
      <path
        d="M5 15V6.5A2.5 2.5 0 0 1 7.5 4H15"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" style={{ width: 14, height: 14 }}>
      <path
        d="m5 12.5 4.5 4.5L19 7.5"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export default function CopyButton({ text, title = "Salin", label, className = "" }) {
  const [copied, setCopied] = useState(false);
  const timerRef = useRef(null);
  const { notify } = useToast();

  useEffect(() => () => clearTimeout(timerRef.current), []);

  async function handleClick(e) {
    e.stopPropagation();

    const ok = await copyText(typeof text === "function" ? text() : text);

    if (!ok) {
      notify({ type: "error", message: "Gagal menyalin ke clipboard.", duration: 2500 });
      return;
    }

    setCopied(true);
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setCopied(false), 1500);
  }

  const shape = label ? "px-2 py-1 text-[11px] gap-1.5" : "w-7 h-7 justify-center";

  return (
    <button
      type="button"
      onClick={handleClick}
      title={copied ? "Tersalin" : title}
      aria-label={copied ? "Tersalin" : title}
      className={`inline-flex items-center rounded-pill transition hover:bg-white/10 ${shape} ${
        copied ? "text-emerald-300" : "text-white/40 hover:text-white"
      } ${className}`}
    >
      {copied ? <CheckIcon /> : <CopyIcon />}
      {label && <span>{copied ? "Tersalin" : label}</span>}
    </button>
  );
}