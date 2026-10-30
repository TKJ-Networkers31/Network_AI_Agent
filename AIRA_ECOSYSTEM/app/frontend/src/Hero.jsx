// app/frontend/src/Hero.jsx
//
// Cyber Minimalist Centered Hero (Claude Style) with Dynamic Tool Trends
// Dominan Hitam, Biru Teknologi, dan Ungu Cyber dengan Neon Hover Glow.

import { useEffect, useMemo, useState } from "react";
import BrandEmblem from "./components/BrandEmblem.jsx";

const STORAGE_KEY_RECENT_TOOLS = "aira_recent_tools";

// Daftar pustaka tool cerdas AIRA yang siap direkomendasikan secara dinamis
const ALL_SMART_TOOLS = [
  {
    id: "mikrotik_report",
    icon: "🛡️",
    badge: "Audit",
    title: "Router Health Report",
    desc: "Audit komprehensif CPU, memory, link interface, firewall & logs router.",
    prompt: "Tolong audit kondisi router dan buatkan laporan kesehatannya.",
    glow: "cyan",
    weight: 10,
  },
  {
    id: "mikrotik_exec",
    icon: "⚡",
    badge: "CLI SSH",
    title: "Remote & Eksekusi CLI",
    desc: "Kirim perintah RouterOS persistent dan analisa outputnya secara mendalam.",
    prompt: "Konek ke router dan cek konfigurasi /ip address print",
    glow: "cyan",
    weight: 9,
  },
  {
    id: "net_diag",
    icon: "🌐",
    badge: "Diag",
    title: "Network Diagnostics",
    desc: "Diagnostik rute jaringan, DNS resolution, dan uji latensi ICMP.",
    prompt: "Lakukan ping dan traceroute ke 8.8.8.8 untuk cek kualitas koneksi",
    glow: "purple",
    weight: 8,
  },
  {
    id: "multimodal_ocr",
    icon: "👁️",
    badge: "Vision",
    title: "Analisis Dokumen & Topologi",
    desc: "Unggah gambar skema topologi atau konfigurasi untuk dianalisis oleh AI.",
    prompt: "Saya ingin melampirkan gambar topologi jaringan untuk dianalisis",
    glow: "purple",
    weight: 7,
  },
  {
    id: "snmp_monitor",
    icon: "📡",
    badge: "SNMP",
    title: "Traffic & Resource Monitor",
    desc: "Pantau utilisasi bandwidth dan traffic octets interface secara realtime.",
    prompt: "Cek traffic bandwidth dan utilisasi resource router",
    glow: "cyan",
    weight: 6,
  },
  {
    id: "devices_vault",
    icon: "🔐",
    badge: "Inventory",
    title: "Brankas Kredensial & Inventory",
    desc: "Kelola perangkat jaringan dan multi-kredensial terenkripsi di SQLite.",
    prompt: "Tampilkan daftar semua perangkat jaringan yang tersimpan di inventory",
    glow: "purple",
    weight: 5,
  },
];

const DEFAULT_CHIPS = [
  { label: "Cek kesehatan router", icon: "🛡️" },
  { label: "Ping ke 8.8.8.8", icon: "🌐" },
  { label: "Jalankan /ip route print", icon: "⚡" },
  { label: "Apa isi Workspace-ku?", icon: "📁" },
];

export default function Hero({ greeting, onQuickPrompt, prompts = DEFAULT_CHIPS, heroModel }) {
  const [recentTools, setRecentTools] = useState([]);

  // Muat tren penggunaan tool dari localStorage
  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY_RECENT_TOOLS);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) setRecentTools(parsed);
      }
    } catch {
      // storage disabled / fallback
    }
  }, []);

  // Susun 3 kartu rekomendasi dinamis berdasarkan tren pemakaian
  const dynamicCards = useMemo(() => {
    const list = [...ALL_SMART_TOOLS];
    // Naikkan bobot tool yang baru saja dipakai
    list.sort((a, b) => {
      const aRecentIdx = recentTools.indexOf(a.id);
      const bRecentIdx = recentTools.indexOf(b.id);
      const aScore = aRecentIdx !== -1 ? 100 - aRecentIdx * 10 : a.weight;
      const bScore = bRecentIdx !== -1 ? 100 - bRecentIdx * 10 : b.weight;
      return bScore - aScore;
    });
    return list.slice(0, 3);
  }, [recentTools]);

  // Handler klik tool: catat ke tren pemakaian agar semakin dinamis
  function handleSelectTool(tool) {
    try {
      const updated = [tool.id, ...recentTools.filter((id) => id !== tool.id)].slice(0, 8);
      setRecentTools(updated);
      localStorage.setItem(STORAGE_KEY_RECENT_TOOLS, JSON.stringify(updated));
    } catch {
      // ignore
    }
    onQuickPrompt?.(tool.prompt);
  }

  // Teks sapaan terpusat ala Claude
  const titleText =
    heroModel?.greeting ||
    greeting ||
    "Halo, ada yang bisa kubantu hari ini?";

  const subtitleText =
    heroModel?.subtitle ||
    "Ketik pertanyaan jaringanmu, gunakan / untuk tool langsung, atau lampirkan dokumen.";

  return (
    <div className="flex-1 flex flex-col items-center justify-center text-center px-3 sm:px-6 py-6 sm:py-10 max-w-4xl mx-auto w-full select-none">
      {/* Centered Glowing Brand Emblem */}
      <div className="relative w-28 h-28 sm:w-36 sm:h-36 mb-5 flex items-center justify-center">
        <span
          className="absolute inset-0 rounded-full bg-core-glow blur-2xl opacity-50 animate-pulse pointer-events-none"
          aria-hidden="true"
        />
        <BrandEmblem size={96} glow className="relative z-10 transition-transform duration-300 hover:scale-105" />
      </div>

      {/* Claude-style Centered Greeting */}
      <h1 className="text-2xl sm:text-3xl md:text-4xl font-semibold tracking-tight text-white mb-2 leading-tight">
        <span className="shimmer-text">{titleText}</span>
      </h1>
      <p className="text-xs sm:text-sm text-text-secondary max-w-lg leading-relaxed mb-6 font-normal">
        {subtitleText}
      </p>

      {/* Quick Action Chips (Minimalist Glass Pills with Hover Glow) */}
      {prompts?.length > 0 && (
        <div className="flex flex-wrap items-center justify-center gap-2 mb-8">
          {prompts.map((p) => (
            <button
              key={p.label}
              type="button"
              onClick={() => onQuickPrompt?.(p.label)}
              className="flex items-center gap-1.5 text-xs px-3.5 py-1.5 rounded-pill bg-white/[0.03] border border-white/10 text-text-secondary hover:text-white hover:border-cyan-400/60 hover:shadow-[0_0_15px_rgba(56,189,248,0.25)] transition duration-200"
            >
              <span>{p.icon}</span>
              <span>{p.label}</span>
            </button>
          ))}
        </div>
      )}

      {/* Dynamic Tool Recommendation Cards (Glassmorphism + Neon Glowing Borders) */}
      <div className="w-full">
        <div className="flex items-center justify-between px-1 mb-2.5">
          <span className="text-[11px] font-semibold tracking-wider uppercase text-cyan-400/80 flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-ping" />
            Rekomendasi Tool Dinamis
          </span>
          <span className="text-[10px] text-text-secondary/60">
            Disesuaikan dengan tren otomatisasi Anda
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 w-full">
          {dynamicCards.map((c) => {
            const isCyan = c.glow === "cyan";
            return (
              <button
                key={c.id}
                type="button"
                onClick={() => handleSelectTool(c)}
                className={`text-left p-4 rounded-card border transition-all duration-250 group relative overflow-hidden backdrop-blur-md bg-surface/50 border-white/10 ${
                  isCyan
                    ? "hover:border-cyan-400/60 hover:shadow-[0_0_22px_-2px_rgba(56,189,248,0.3)] hover:bg-surface/80"
                    : "hover:border-purple-400/60 hover:shadow-[0_0_22px_-2px_rgba(168,85,247,0.3)] hover:bg-surface/80"
                }`}
              >
                {/* Subtle glass reflection highlight */}
                <div className="absolute inset-0 bg-gradient-to-br from-white/[0.04] to-transparent pointer-events-none" />

                <div className="flex items-center justify-between mb-2.5 relative z-10">
                  <span className="text-2xl filter drop-shadow group-hover:scale-110 transition-transform duration-200">
                    {c.icon}
                  </span>
                  <span
                    className={`text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-pill border ${
                      isCyan
                        ? "text-cyan-300 bg-cyan-500/10 border-cyan-500/20 group-hover:border-cyan-400/50"
                        : "text-purple-300 bg-purple-500/10 border-purple-500/20 group-hover:border-purple-400/50"
                    }`}
                  >
                    {c.badge}
                  </span>
                </div>

                <div className="relative z-10">
                  <div
                    className={`text-sm font-semibold text-text-primary transition-colors ${
                      isCyan ? "group-hover:text-cyan-300" : "group-hover:text-purple-300"
                    }`}
                  >
                    {c.title}
                  </div>
                  <p className="text-xs text-text-secondary mt-1 leading-relaxed line-clamp-2">
                    {c.desc}
                  </p>
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
