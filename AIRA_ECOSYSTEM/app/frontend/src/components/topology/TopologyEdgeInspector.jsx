// src/components/topology/TopologyEdgeInspector.jsx
// Multi-Layer Edge & Empirical Evidence Inspector for AIRA Topology Fabric V2 (Phase 4.5).

import { useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  Layers,
  Link2,
  Network,
  Shield,
  Trash2,
  X,
  Zap,
} from "lucide-react";
import {
  API_BASE,
  CONFIDENCE_TIERS,
  RELATIONSHIP_CLASSES,
  formatRelativeTime,
  getMultiLayerEdgeVisualConfig,
} from "./topologyConstants.js";

export default function TopologyEdgeInspector({
  edge,
  nodesMap = {},
  onClose,
  onSelectNode,
  onDeleteEdge,
  onTroubleshoot,
  onRefreshTopology,
  pushToast,
  readOnly = false,
  historicalEvidence = [],
}) {
  const [evidenceOpen, setEvidenceOpen] = useState(true);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [evidenceList, setEvidenceList] = useState([]);
  const [verifying, setVerifying] = useState(false);

  const edgeId = edge?.id || edge?.link_id;
  const srcId = edge?.source_node_id || edge?.source;
  const dstId = edge?.target_node_id || edge?.target;
  const srcNode = nodesMap[srcId];
  const dstNode = nodesMap[dstId];

  // Fetch or resolve empirical evidence
  useEffect(() => {
    if (!edgeId) return;

    // In historical snapshot mode, resolve evidence directly from snapshot graph.evidence
    if (readOnly && historicalEvidence && historicalEvidence.length > 0) {
      const matched = historicalEvidence.filter(
        (ev) => ev.edge_id === edgeId || ev.id === edgeId || (ev.source_node_id === srcId && ev.target_node_id === dstId)
      );
      setEvidenceList(matched);
      return;
    }

    // In live mode, fetch empirical evidence from API
    let active = true;
    (async () => {
      setEvidenceLoading(true);
      try {
        const res = await fetch(`${API_BASE}/edges/${encodeURIComponent(edgeId)}/evidence`);
        if (res.ok) {
          const json = await res.json();
          if (active && json.success) {
            setEvidenceList(json.evidence || []);
            return;
          }
        }
        // Fallback: if edge already carries embedded evidence objects or sources
        if (active && edge?.evidence && Array.isArray(edge.evidence)) {
          setEvidenceList(edge.evidence);
        } else if (active && edge?.evidence_sources && Array.isArray(edge.evidence_sources)) {
          setEvidenceList(
            edge.evidence_sources.map((src, idx) => ({
              id: `ev-${idx}`,
              evidence_type: typeof src === "string" ? src : src.type || "observed",
              explanation: typeof src === "string" ? `Empirical evidence source: ${src}` : src.explanation || "",
              confidence_score: edge.confidence_score || 0.8,
            }))
          );
        }
      } catch {
        if (active && edge?.evidence && Array.isArray(edge.evidence)) {
          setEvidenceList(edge.evidence);
        }
      } finally {
        if (active) setEvidenceLoading(false);
      }
    })();

    return () => {
      active = false;
    };
  }, [edgeId, readOnly, historicalEvidence, srcId, dstId, edge]);

  if (!edge) return null;

  const vis = getMultiLayerEdgeVisualConfig(edge, srcNode, dstNode, false);
  const relClass = edge.relationship_class || RELATIONSHIP_CLASSES.PHYSICAL;
  const operStatus = (edge.operational_status || edge.oper_status || edge.status || "up").toLowerCase();
  const verStatus = (edge.verification_status || "unknown").toLowerCase();
  const confidenceTierKey = (edge.confidence_tier || "medium").toUpperCase();
  const confTierCfg = CONFIDENCE_TIERS[confidenceTierKey] || CONFIDENCE_TIERS.MEDIUM;
  const confPercent = Math.round((edge.confidence_score !== undefined ? edge.confidence_score : 0.8) * 100);

  const localPort = edge.source_interface_name || edge.source_port || "unspecified";
  const remotePort = edge.target_interface_name || edge.target_port || "unspecified";

  const handleVerifyEdge = async () => {
    if (readOnly) return;
    setVerifying(true);
    try {
      const res = await fetch(`${API_BASE}/links/verify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          link_id: edgeId,
          verification_status: "confirmed",
          source_port: localPort !== "unspecified" ? localPort : null,
          target_port: remotePort !== "unspecified" ? remotePort : null,
          link_type: edge.relationship_class || "physical",
          reason: "Konfirmasi administratif adjacency fisik oleh administrator.",
        }),
      });
      const json = await res.json();
      if (json.success) {
        pushToast?.("Relasi berhasil diverifikasi secara administratif!", "success");
        onRefreshTopology?.();
      } else {
        pushToast?.(json.detail || "Gagal memverifikasi relasi.", "error");
      }
    } catch {
      pushToast?.("Gagal menghubungi server untuk verifikasi relasi.", "error");
    } finally {
      setVerifying(false);
    }
  };

  return (
    <aside className="absolute right-0 top-12 bottom-0 w-80 sm:w-[420px] bg-black/95 backdrop-blur-2xl border-l border-white/10 p-4 overflow-y-auto shadow-2xl z-40 transition-all">
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-white/10 mb-3">
        <div className="flex flex-wrap items-center gap-1.5">
          <span
            className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider border"
            style={{
              backgroundColor: `${vis.stroke}20`,
              borderColor: `${vis.stroke}60`,
              color: vis.stroke,
            }}
          >
            {vis.label}
          </span>
          <span
            className={`px-2 py-0.5 rounded-full text-[10px] font-semibold border ${
              operStatus === "up"
                ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
                : operStatus === "down"
                ? "bg-rose-500/20 text-rose-300 border-rose-500/30"
                : "bg-amber-500/20 text-amber-300 border-amber-500/30"
            }`}
          >
            {operStatus.toUpperCase()}
          </span>
          <span className="text-[10px] text-text-secondary capitalize font-mono">
            {verStatus}
          </span>
        </div>

        <div className="flex items-center gap-1 shrink-0">
          {readOnly && (
            <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-purple-500/20 text-purple-300 border border-purple-500/30">
              Snapshot
            </span>
          )}
          {!readOnly && onDeleteEdge && (
            <button
              onClick={() => onDeleteEdge(edgeId)}
              className="w-7 h-7 rounded-full flex items-center justify-center text-red-400/80 hover:text-red-400 hover:bg-red-500/10 transition"
              title="Hapus relasi"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          )}
          <button
            onClick={onClose}
            className="w-7 h-7 rounded-full flex items-center justify-center text-text-secondary hover:text-text-primary hover:bg-white/10 transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Endpoints & Direction */}
      <div className="mb-3 p-3 rounded-xl bg-white/5 border border-white/10 space-y-2">
        <div className="flex items-center justify-between text-xs">
          <div className="flex-1 min-w-0 pr-2">
            <span className="text-[10px] text-text-secondary block font-mono">SOURCE</span>
            <button
              onClick={() => srcNode && onSelectNode?.(srcNode)}
              className="font-bold text-text-primary hover:text-sky-300 truncate text-left block"
              title={srcNode?.name || srcId}
            >
              {srcNode?.name || srcId}
            </button>
            <span className="text-[10px] font-mono text-purple-300 block truncate">
              port: {localPort}
            </span>
          </div>

          <div className="flex flex-col items-center justify-center px-2 shrink-0">
            {vis.directional ? (
              <ArrowRight className="w-5 h-5 text-purple-400 animate-pulse" />
            ) : (
              <Link2 className="w-5 h-5 text-emerald-400" />
            )}
            <span className="text-[9px] text-text-secondary font-mono mt-0.5">
              {vis.directional ? "routed" : "bidirectional"}
            </span>
          </div>

          <div className="flex-1 min-w-0 pl-2 text-right">
            <span className="text-[10px] text-text-secondary block font-mono">TARGET</span>
            <button
              onClick={() => dstNode && onSelectNode?.(dstNode)}
              className="font-bold text-text-primary hover:text-sky-300 truncate text-right block ml-auto"
              title={dstNode?.name || dstId}
            >
              {dstNode?.name || dstId}
            </button>
            <span className="text-[10px] font-mono text-purple-300 block truncate">
              port: {remotePort}
            </span>
          </div>
        </div>

        {/* Quick Node Navigation Buttons */}
        <div className="grid grid-cols-2 gap-2 pt-2 border-t border-white/5">
          <button
            onClick={() => srcNode && onSelectNode?.(srcNode)}
            disabled={!srcNode}
            className="py-1 px-2 rounded-lg bg-white/5 hover:bg-white/10 text-[10px] text-text-secondary hover:text-text-primary truncate transition disabled:opacity-40"
          >
            Lihat {srcNode?.name || "Source"}
          </button>
          <button
            onClick={() => dstNode && onSelectNode?.(dstNode)}
            disabled={!dstNode}
            className="py-1 px-2 rounded-lg bg-white/5 hover:bg-white/10 text-[10px] text-text-secondary hover:text-text-primary truncate transition disabled:opacity-40"
          >
            Lihat {dstNode?.name || "Target"}
          </button>
        </div>
      </div>

      {/* Confidence & Rationale Banner */}
      <div className="mb-3 p-2.5 rounded-xl bg-white/5 border border-white/10 space-y-1.5 text-[11px]">
        <div className="flex items-center justify-between">
          <span className="text-text-secondary">Confidence Tier:</span>
          <div className="flex items-center gap-1.5">
            <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${confTierCfg.badgeClass}`}>
              {confTierCfg.label}
            </span>
            <span className="font-mono text-sky-300 font-semibold">{confPercent}%</span>
          </div>
        </div>

        {edge.confidence_reason && (
          <p className="text-[10px] text-sky-200/90 pt-1 border-t border-white/5 leading-snug">
            {edge.confidence_reason}
          </p>
        )}

        {edge.verification_status === "conflicting" && (
          <div className="p-2 rounded-lg bg-rose-500/15 border border-rose-500/30 text-rose-200 text-[10px] flex items-start gap-1.5">
            <AlertTriangle className="w-3.5 h-3.5 text-rose-400 shrink-0 mt-0.5" />
            <span>
              Terdeteksi konflik topologi pada relasi ini! Terdapat bukti observasi yang bertentangan
              mengenai port atau keberadaan relasi fisik.
            </span>
          </div>
        )}
      </div>

      {/* Layer-Specific Technical Metadata */}
      <div className="mb-3 bg-white/5 border border-white/10 rounded-xl p-3 space-y-2 text-[11px]">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-text-secondary block flex items-center gap-1">
          <Layers className="w-3 h-3 text-sky-400" /> Atribut Layer &amp; Protokol
        </span>

        <div className="grid grid-cols-2 gap-2">
          <div className="bg-black/40 border border-white/5 rounded-lg p-2">
            <span className="text-[10px] text-text-secondary block">Layer</span>
            <span className="font-bold text-text-primary capitalize">{relClass}</span>
          </div>
          <div className="bg-black/40 border border-white/5 rounded-lg p-2">
            <span className="text-[10px] text-text-secondary block">Kapasitas / Bandwidth</span>
            <span className="font-mono text-text-primary">{edge.bandwidth || "1 Gbps"}</span>
          </div>
        </div>

        {/* Layer 2 Attributes */}
        {relClass === RELATIONSHIP_CLASSES.LAYER2 && (
          <div className="pt-2 border-t border-white/5 space-y-1">
            <div className="flex items-center justify-between text-[10px]">
              <span className="text-text-secondary">VLAN ID:</span>
              <span className="font-mono text-sky-300">{edge.vlan_id || edge.vlan || "Untagged / Default"}</span>
            </div>
            {edge.is_lag_member && (
              <div className="flex items-center justify-between text-[10px]">
                <span className="text-text-secondary">LAG Bundle:</span>
                <span className="font-mono text-purple-300">{edge.lag_id || "Active Aggregation"}</span>
              </div>
            )}
          </div>
        )}

        {/* Layer 3 Attributes */}
        {relClass === RELATIONSHIP_CLASSES.LAYER3 && (
          <div className="pt-2 border-t border-white/5 space-y-1">
            <div className="flex items-center justify-between text-[10px]">
              <span className="text-text-secondary">Next Hop:</span>
              <span className="font-mono text-purple-300">{edge.next_hop || dstNode?.ip || "Direct Subnet"}</span>
            </div>
            <div className="flex items-center justify-between text-[10px]">
              <span className="text-text-secondary">Subnet / CIDR:</span>
              <span className="font-mono text-text-primary">{edge.network_cidr || "Connected Subnet"}</span>
            </div>
          </div>
        )}

        {/* Logical Attributes */}
        {relClass === RELATIONSHIP_CLASSES.LOGICAL && (
          <div className="pt-2 border-t border-white/5 space-y-1">
            <div className="flex items-center justify-between text-[10px]">
              <span className="text-text-secondary">Tunnel / Subtype:</span>
              <span className="font-mono text-amber-300 uppercase">{edge.subtype || edge.tunnel_type || "VPN Tunnel"}</span>
            </div>
          </div>
        )}

        {/* Lifecycle Timestamps */}
        <div className="pt-2 border-t border-white/5 flex items-center justify-between text-[10px] text-text-secondary">
          <span className="flex items-center gap-1">
            <Clock className="w-3 h-3 text-text-secondary/70" />
            Terakhir Terlihat:
          </span>
          <span className="font-mono text-text-primary">
            {formatRelativeTime(edge.last_seen || edge.last_verified || edge.last_checked)}
          </span>
        </div>
      </div>

      {/* Governance & Verification Controls */}
      {!readOnly && (
        <div className="mb-3 bg-white/5 border border-white/10 rounded-xl p-3 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-text-secondary flex items-center gap-1">
              <Shield className="w-3 h-3 text-emerald-400" /> Tata Kelola Adjacency
            </span>
          </div>

          {verStatus !== "confirmed" && verStatus !== "manual" ? (
            <div className="space-y-1">
              <button
                onClick={handleVerifyEdge}
                disabled={verifying}
                className="w-full py-1.5 px-3 rounded-pill bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 hover:bg-emerald-500/25 text-[11px] font-medium flex items-center justify-center gap-1.5 transition disabled:opacity-50"
              >
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>{verifying ? "Mengonfirmasi..." : "Konfirmasi Administratif Adjacency Fisik"}</span>
              </button>
              <p className="text-[10px] text-text-secondary text-center">
                Menetapkan verifikasi administratif (user_managed), independen dari protokol LLDP/MNDP.
              </p>
            </div>
          ) : (
            <div className="p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 text-[10px] flex items-center gap-1.5">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
              <span>Adjacency fisik telah dikonfirmasi secara administratif oleh administrator.</span>
            </div>
          )}
        </div>
      )}

      {/* Empirical Evidence Drawer */}
      <div className="mb-4 bg-white/5 border border-white/10 rounded-xl overflow-hidden">
        <button
          onClick={() => setEvidenceOpen((v) => !v)}
          className="w-full px-3 py-2.5 flex items-center justify-between text-[11px] font-semibold text-text-primary hover:bg-white/5 transition"
        >
          <span className="flex items-center gap-1.5">
            <Network className="w-3.5 h-3.5 text-sky-400" />
            <span>Bukti Empiris &amp; Telemetri ({evidenceList.length})</span>
          </span>
          {evidenceOpen ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
        </button>

        {evidenceOpen && (
          <div className="px-3 pb-3 pt-1 border-t border-white/10 space-y-2 text-[11px]">
            {evidenceLoading ? (
              <p className="text-text-secondary text-[10px] py-1">Memuat bukti empiris dari database...</p>
            ) : evidenceList.length === 0 ? (
              <p className="text-text-secondary text-[10px] py-1">
                Belum ada rekaman bukti empiris granular untuk relasi ini. Relasi dibentuk berdasarkan konfigurasi manual atau topologi dasar.
              </p>
            ) : (
              evidenceList.map((ev, idx) => (
                <div key={ev.id || idx} className="p-2.5 rounded-lg bg-black/60 border border-white/10 space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="font-mono font-bold text-emerald-300 text-[10px] uppercase">
                      {ev.evidence_type || "TELEMETRY"}
                    </span>
                    <span className="text-[9px] text-text-secondary font-mono">
                      {ev.freshness || "observed"} • {formatRelativeTime(ev.observed_at)}
                    </span>
                  </div>

                  {(ev.local_interface || ev.remote_interface) && (
                    <p className="text-[10px] font-mono text-purple-300">
                      Port: {ev.local_interface || "?"} ➔ {ev.remote_interface || "?"}
                    </p>
                  )}

                  <p className="text-[10px] text-text-secondary leading-snug">
                    {ev.explanation || "Observasi adjacency jaringan tercatat melalui protokol discovery."}
                  </p>

                  {ev.raw_excerpt && (
                    <div className="mt-1 p-1.5 rounded bg-black border border-white/5 text-[9px] font-mono text-emerald-400/90 overflow-x-auto whitespace-pre">
                      {ev.raw_excerpt}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        )}
      </div>

      {/* Troubleshooting Action */}
      <div className="pt-2 border-t border-white/10">
        <button
          onClick={() => onTroubleshoot?.({ type: "edge", edge, srcNode, dstNode })}
          className="w-full py-2.5 px-4 rounded-pill bg-sakura-gradient text-white text-xs font-semibold shadow-sakura-glow hover:brightness-110 transition flex items-center justify-center gap-1.5"
        >
          <Zap className="w-3.5 h-3.5 text-amber-300" />
          <span>Troubleshoot Relasi dengan AIRA</span>
        </button>
      </div>
    </aside>
  );
}
