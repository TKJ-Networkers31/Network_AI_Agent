/**
 * src/platform/adaptive-experience/blocks/TraceroutePathBlock.jsx
 *
 * Hop-by-hop visualization for network routing diagnostics.
 */

import React from "react";
import { Route, CheckCircle2, XCircle, ArrowRight } from "lucide-react";

export default function TraceroutePathBlock({ block }) {
  const data = block?.data || {};
  const target = data.target || "Target";
  const reached = Boolean(data.reached);
  const hops = data.hops || [];

  const getLatencyBadge = (rtt) => {
    if (rtt === null || rtt === undefined || rtt <= 0) {
      return <span className="text-[10px] text-rose-400 font-mono">* * *</span>;
    }
    const num = Number(rtt);
    let color = "text-emerald-400 bg-emerald-950/60 border-emerald-500/30";
    if (num > 100) color = "text-rose-400 bg-rose-950/60 border-rose-500/30";
    else if (num > 40) color = "text-amber-400 bg-amber-950/60 border-amber-500/30";

    return (
      <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${color}`}>
        {num.toFixed(1)} ms
      </span>
    );
  };

  return (
    <div className="my-2 p-4 rounded-xl border border-white/10 bg-slate-900/80 backdrop-blur-md shadow-lg space-y-3 font-sans">
      <div className="flex items-center justify-between border-b border-white/5 pb-2.5">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-indigo-500/10 text-indigo-400">
            <Route size={18} />
          </div>
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-white/90">
              Jalur Hop-by-Hop Traceroute
            </h4>
            <p className="text-[11px] text-white/50">Tujuan: {target}</p>
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          {reached ? (
            <span className="flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-950/60 border border-emerald-500/30 text-emerald-300">
              <CheckCircle2 size={12} /> REACHED ({hops.length} Hops)
            </span>
          ) : (
            <span className="flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded-full bg-amber-950/60 border border-amber-500/30 text-amber-300">
              <XCircle size={12} /> PARSIAL ({hops.length} Hops)
            </span>
          )}
        </div>
      </div>

      <div className="space-y-1.5 font-mono text-xs">
        {hops.map((hop, idx) => {
          const isLast = idx === hops.length - 1;
          const isTimeout = hop.status === "TIMEOUT" || !hop.ip;
          return (
            <div
              key={idx}
              className={`flex items-center justify-between p-2 rounded-lg border transition-all ${
                isLast && reached
                  ? "border-emerald-500/40 bg-emerald-500/10"
                  : isTimeout
                  ? "border-white/5 bg-black/20 opacity-60"
                  : "border-white/5 bg-black/30 hover:border-white/15"
              }`}
            >
              <div className="flex items-center gap-2.5">
                <span className="w-5 h-5 rounded-full bg-white/10 text-white/70 flex items-center justify-center text-[10px] font-bold shrink-0">
                  {hop.hop ?? idx + 1}
                </span>
                <div>
                  <div className="font-semibold text-white/90 text-xs">
                    {hop.ip || "* * * (Request Timed Out)"}
                  </div>
                  {hop.host && hop.host !== hop.ip && (
                    <div className="text-[10px] text-white/40">{hop.host}</div>
                  )}
                </div>
              </div>

              <div>{getLatencyBadge(hop.avg_rtt_ms ?? (hop.rtts && hop.rtts[0]))}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
