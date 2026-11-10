/**
 * src/platform/adaptive-experience/blocks/ConfigDiffBlock.jsx
 *
 * Side-by-side or unified diff comparison for configuration changes.
 */

import React from "react";
import { FileCode, Check, AlertCircle } from "lucide-react";

export default function ConfigDiffBlock({ block }) {
  const data = block?.data || {};
  const device = data.device || "Router";
  const diffText = data.diff_text || data.diff || "";
  const lines = diffText ? diffText.split("\n") : [];

  return (
    <div className="my-2 p-4 rounded-xl border border-white/10 bg-slate-900/90 backdrop-blur-md shadow-lg space-y-3 font-sans">
      <div className="flex items-center justify-between border-b border-white/5 pb-2.5">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-purple-500/10 text-purple-400">
            <FileCode size={18} />
          </div>
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-white/90">
              Audit Perubahan Konfigurasi (Diff)
            </h4>
            <p className="text-[11px] text-white/50">{device}</p>
          </div>
        </div>
        <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-purple-950/60 border border-purple-500/30 text-purple-300">
          PRE-FLIGHT VALIDATION
        </span>
      </div>

      <div className="p-3 rounded-lg border border-white/5 bg-black/60 overflow-x-auto font-mono text-xs">
        {lines.length === 0 ? (
          <div className="text-white/40 italic">Tidak ada perubahan konfigurasi terdeteksi.</div>
        ) : (
          lines.map((line, idx) => {
            let color = "text-white/70";
            let bg = "";
            if (line.startsWith("+")) {
              color = "text-emerald-400";
              bg = "bg-emerald-500/10";
            } else if (line.startsWith("-")) {
              color = "text-rose-400";
              bg = "bg-rose-500/10";
            } else if (line.startsWith("@@")) {
              color = "text-cyan-400 font-bold";
            }

            return (
              <div key={idx} className={`px-1.5 py-0.5 rounded ${bg} ${color} whitespace-pre`}>
                {line}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
