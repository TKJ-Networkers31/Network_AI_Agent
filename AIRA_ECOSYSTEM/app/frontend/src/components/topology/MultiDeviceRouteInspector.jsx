// src/components/topology/MultiDeviceRouteInspector.jsx
// AIRA OS — Multi-Device Route Path & Evidence Inspector (WP 4.6.5)

import { AlertTriangle, ArrowRight, CheckCircle2, GitBranch, Layers, ShieldAlert, X } from "lucide-react";

export default function MultiDeviceRouteInspector({
  segment,
  overlayPayload,
  nodesMap = {},
  onClose,
  onSelectSegment,
}) {
  if (!segment) return null;

  const srcNode = nodesMap[segment.source_device_id];
  const tgtNode = segment.target_device_id ? nodesMap[segment.target_device_id] : null;
  const candidate = segment.selected_route_candidate || {};
  const recursiveDeps = Array.isArray(segment.recursive_dependency) ? segment.recursive_dependency : [];
  const evidenceSources = Array.isArray(segment.evidence_sources) ? segment.evidence_sources : [];
  const unresolvedInfo = Array.isArray(segment.unresolved_info) ? segment.unresolved_info : [];
  const allSegments = overlayPayload?.overlay?.segments || [];
  const inconsistencies = overlayPayload?.inconsistencies || [];
  const pctConf = Math.round((Number(segment.confidence) || 0) * 100);

  return (
    <div className="fixed right-4 top-28 bottom-4 w-96 max-w-[92vw] bg-[#060a12]/95 border border-cyan-500/30 rounded-3xl shadow-2xl z-40 flex flex-col overflow-hidden backdrop-blur-xl text-xs">
      {/* Header */}
      <div className="px-4 py-3 border-b border-white/10 flex items-center justify-between bg-cyan-950/20">
        <div className="flex items-center gap-2">
          <GitBranch className="w-4 h-4 text-cyan-400" />
          <div>
            <h3 className="font-bold text-text-primary text-xs">Multi-Device Route Inspector</h3>
            <p className="text-[10px] text-cyan-300/80">
              Ephemeral L3 Path Segment · Non-Physical Overlay
            </p>
          </div>
        </div>
        <button
          onClick={onClose}
          className="w-7 h-7 rounded-full flex items-center justify-center text-text-secondary hover:text-white hover:bg-white/10 transition"
          title="Tutup Route Inspector"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {/* Epistemic Notice */}
        <div className="p-2.5 rounded-2xl bg-cyan-500/10 border border-cyan-500/25 text-[10px] text-cyan-200 leading-relaxed">
          <strong>Epistemic Boundary:</strong> Segmen rute ini dihitung dari RIB control-plane dan korelasi lintas-perangkat. Tidak mengubah atau membuktikan kabel fisik (<code>is_physical_link: false</code>).
        </div>

        {/* Hop Summary Banner */}
        <div className="p-3 rounded-2xl bg-white/[0.03] border border-white/10 space-y-2">
          <div className="flex items-center justify-between text-[10px]">
            <span className="px-2 py-0.5 rounded-pill bg-cyan-500/20 text-cyan-300 font-mono font-bold">
              Hop #{segment.hop_index} ({segment.branch_id || "main"})
            </span>
            <span
              className={`px-2 py-0.5 rounded-pill font-mono font-semibold ${
                segment.completeness === "COMPLETE"
                  ? "bg-emerald-500/20 text-emerald-300"
                  : "bg-amber-500/20 text-amber-300"
              }`}
            >
              {segment.completeness || "UNKNOWN"} · {pctConf}% conf
            </span>
          </div>

          <div className="flex items-center gap-2 text-xs font-semibold text-white pt-1">
            <span className="truncate">{srcNode?.name || segment.source_device_id}</span>
            <ArrowRight className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
            <span className="truncate text-cyan-300">
              {tgtNode?.name || segment.next_device_hypothesis || "UNRESOLVED"}
            </span>
          </div>
        </div>

        {/* 13 Mandatory Inspector Fields (Section 9.6) */}
        <div className="p-3 rounded-2xl bg-white/[0.02] border border-white/10 space-y-1.5">
          <div className="text-[10px] uppercase tracking-wider font-bold text-text-secondary mb-1 flex items-center gap-1">
            <Layers className="w-3 h-3 text-sky-400" /> Detail Pemilihan Rute
          </div>

          <InspectorRow label="Source Device" value={segment.source_device_id} mono />
          <InspectorRow label="Destination Prefix" value={segment.destination_prefix || "—"} mono />
          <InspectorRow label="Routing Table (VRF)" value={segment.routing_table || "main"} mono />
          <InspectorRow
            label="Selected Candidate"
            value={`${candidate.dst_prefix || segment.destination_prefix || "—"} [${candidate.protocol || "rib"}]`}
            mono
          />
          <InspectorRow label="Gateway" value={segment.gateway || "—"} mono />
          <InspectorRow label="Immediate Gateway" value={segment.immediate_gateway || segment.gateway || "—"} mono />
          <InspectorRow label="Egress Interface" value={segment.egress_interface || "—"} mono />
          <InspectorRow label="Next Device Hypothesis" value={segment.next_device_hypothesis || "UNRESOLVED"} mono />
          <InspectorRow
            label="Topology Confirmed"
            value={segment.confirmed_by_topology_adjacency ? "Ya (Confirmed L1/L2)" : "Tidak (L3 Inferred Only)"}
          />
          <InspectorRow label="Confidence" value={`${pctConf}% (${segment.overlay_segment_type})`} mono />
          <InspectorRow label="Completeness" value={segment.completeness || "UNKNOWN"} mono />
        </div>

        {/* Recursive Dependency Chain */}
        <div className="p-3 rounded-2xl bg-white/[0.02] border border-white/10 space-y-1.5">
          <div className="text-[10px] uppercase tracking-wider font-bold text-purple-300">
            Recursive Dependency
          </div>
          {recursiveDeps.length > 0 ? (
            <ul className="space-y-1 text-[11px] font-mono text-purple-200">
              {recursiveDeps.map((step, idx) => (
                <li key={idx} className="px-2 py-1 rounded bg-purple-500/10 border border-purple-500/20">
                  {typeof step === "string" ? step : JSON.stringify(step)}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-[11px] text-text-secondary">
              Direct next-hop resolution (tidak ada rantai rekursif tambahan).
            </p>
          )}
        </div>

        {/* Evidence Sources */}
        <div className="p-3 rounded-2xl bg-white/[0.02] border border-white/10 space-y-1.5">
          <div className="text-[10px] uppercase tracking-wider font-bold text-emerald-300 flex items-center gap-1">
            <CheckCircle2 className="w-3 h-3" /> Evidence Sources ({evidenceSources.length})
          </div>
          {evidenceSources.length > 0 ? (
            <div className="flex flex-wrap gap-1">
              {evidenceSources.map((evId, idx) => (
                <span
                  key={idx}
                  className="px-2 py-0.5 rounded-pill bg-emerald-500/10 border border-emerald-500/25 text-emerald-200 font-mono text-[10px]"
                >
                  {evId}
                </span>
              ))}
            </div>
          ) : (
            <p className="text-[11px] text-text-secondary">Tidak ada ID bukti tercatat.</p>
          )}
        </div>

        {/* Unresolved Information / Warnings */}
        {unresolvedInfo.length > 0 && (
          <div className="p-3 rounded-2xl bg-amber-500/10 border border-amber-500/30 space-y-1">
            <div className="text-[10px] uppercase tracking-wider font-bold text-amber-300 flex items-center gap-1">
              <AlertTriangle className="w-3 h-3" /> Unresolved Information
            </div>
            <ul className="list-disc pl-4 space-y-1 text-[11px] text-amber-100">
              {unresolvedInfo.map((note, idx) => (
                <li key={idx}>{note}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Cross-Device Inconsistencies */}
        {inconsistencies.length > 0 && (
          <div className="p-3 rounded-2xl bg-rose-500/10 border border-rose-500/30 space-y-2">
            <div className="text-[10px] uppercase tracking-wider font-bold text-rose-300 flex items-center gap-1">
              <ShieldAlert className="w-3 h-3" /> Cross-Device Inconsistencies ({inconsistencies.length})
            </div>
            <div className="space-y-1.5 max-h-44 overflow-y-auto pr-1">
              {inconsistencies.map((inc) => (
                <div
                  key={inc.finding_id}
                  className="p-2 rounded-xl bg-black/40 border border-rose-500/20 text-[10px] space-y-0.5"
                >
                  <div className="flex items-center justify-between font-mono font-bold text-rose-200">
                    <span>{inc.inconsistency_type}</span>
                    <span className="text-[9px] px-1.5 py-0.2 rounded bg-rose-500/20">
                      {inc.epistemic_class}
                    </span>
                  </div>
                  <p className="text-slate-300 leading-snug">{inc.explanation}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Other Hops Quick Switcher */}
        {allSegments.length > 1 && onSelectSegment && (
          <div className="p-3 rounded-2xl bg-white/[0.02] border border-white/10 space-y-1.5">
            <div className="text-[10px] uppercase tracking-wider font-bold text-text-secondary">
              Semua Segmen Jalur ({allSegments.length})
            </div>
            <div className="space-y-1">
              {allSegments.map((seg) => (
                <button
                  key={seg.segment_id}
                  onClick={() => onSelectSegment(seg)}
                  className={`w-full text-left px-2.5 py-1.5 rounded-xl border text-[10px] font-mono flex items-center justify-between transition ${
                    seg.segment_id === segment.segment_id
                      ? "bg-cyan-500/20 border-cyan-400/50 text-cyan-200"
                      : "bg-white/[0.02] border-white/5 text-text-secondary hover:text-white"
                  }`}
                >
                  <span>
                    #{seg.hop_index} {seg.source_device_id} → {seg.next_device_hypothesis}
                  </span>
                  <span>{Math.round((seg.confidence || 0) * 100)}%</span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function InspectorRow({ label, value, mono = false }) {
  return (
    <div className="flex items-start justify-between gap-2 text-[11px] py-0.5 border-b border-white/[0.04] last:border-b-0">
      <span className="text-text-secondary shrink-0">{label}</span>
      <span className={`text-right text-text-primary break-all ${mono ? "font-mono text-[10.5px]" : ""}`}>
        {value}
      </span>
    </div>
  );
}
