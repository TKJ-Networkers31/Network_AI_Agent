/**
 * src/platform/adaptive-experience/blocks/InvestigationTimelineBlock.jsx
 *
 * Chronological Investigation Timeline for Network RCA & Troubleshooting.
 */

import React from "react";
import { Clock, CheckCircle, AlertTriangle, ShieldCheck } from "lucide-react";

export default function InvestigationTimelineBlock({ block }) {
  const data = block?.data || {};
  const title = data.title || "Kronologi Investigasi Insiden";
  const events = data.events || data.timeline || [];

  return (
    <div className="my-2 p-4 rounded-xl border border-white/10 bg-slate-900/80 backdrop-blur-md shadow-lg space-y-3 font-sans">
      <div className="flex items-center justify-between border-b border-white/5 pb-2.5">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-indigo-500/10 text-indigo-400">
            <Clock size={18} />
          </div>
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-white/90">
              {title}
            </h4>
            <p className="text-[11px] text-white/50">{events.length} Kejadian Tercatat</p>
          </div>
        </div>
        <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-indigo-950/60 border border-indigo-500/30 text-indigo-300">
          EVIDENCE TIMELINE
        </span>
      </div>

      <div className="relative pl-4 space-y-3 before:absolute before:left-1.5 before:top-2 before:bottom-2 before:w-0.5 before:bg-white/10 font-mono text-xs">
        {events.map((ev, idx) => {
          const isError = ev.severity === "high" || ev.severity === "critical" || ev.error;
          return (
            <div key={idx} className="relative group">
              <div
                className={`absolute -left-[17px] top-1 w-2.5 h-2.5 rounded-full border-2 ${
                  isError
                    ? "bg-rose-500 border-rose-300"
                    : "bg-cyan-500 border-cyan-300"
                }`}
              />
              <div className="p-2.5 rounded-lg border border-white/5 bg-black/30 space-y-1">
                <div className="flex items-center justify-between text-[10px] text-white/40">
                  <span>{ev.timestamp || `T+${idx * 15}s`}</span>
                  <span className="uppercase text-white/60 font-semibold">{ev.source || "NMS/LOG"}</span>
                </div>
                <div className="font-sans text-xs text-white/90">{ev.description || ev.event || JSON.stringify(ev)}</div>
                {ev.evidence && (
                  <div className="text-[10px] text-cyan-400/80 font-mono">
                    Ref: {typeof ev.evidence === "string" ? ev.evidence : JSON.stringify(ev.evidence)}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
