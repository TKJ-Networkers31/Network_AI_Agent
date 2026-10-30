// src/components/topology/TopologyNodeInspector.jsx
// Evidence-based Node Inspector, Governance Overrides, and Link Verification Drawer for AIRA Topology Fabric V2.

import { useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Eye,
  Globe,
  Pencil,
  Plus,
  Shield,
  Trash2,
  X,
  Zap,
} from "lucide-react";
import {
  API_BASE,
  FRESHNESS_BADGES,
  MANAGEMENT_LABELS,
  OWNERSHIP_BADGES,
  REACHABILITY_BADGES,
  SCOPE_LABELS,
  STATUS_CONFIG,
  formatRelativeTime,
} from "./topologyConstants.js";

export default function TopologyNodeInspector({
  node,
  links,
  nodesMap,
  onClose,
  onSelectNode,
  onEditNode,
  onDeleteNode,
  onOpenAddLink,
  onDeleteLink,
  onPingNode,
  onTroubleshoot,
  onRefreshTopology,
  onOpenNmsDetail,
  onOpenSnmpWizard,
  pinging,
  troubleshooting,
  pushToast,
}) {
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [evidenceList, setEvidenceList] = useState([]);
  const [classifyOpen, setClassifyOpen] = useState(false);
  const [savingClass, setSavingClass] = useState(false);
  const [classForm, setClassForm] = useState({
    ownership_status: "owned",
    topology_scope: "enterprise_internal",
    trust_zone: "internal",
    device_role: "",
    reason: "",
  });

  useEffect(() => {
    if (!node) return;
    setEvidenceList([]);
    setEvidenceOpen(false);
    setClassifyOpen(false);
    setClassForm({
      ownership_status: node.ownership_status || "unknown",
      topology_scope: node.topology_scope || "unclassified",
      trust_zone: node.trust_zone || "unknown",
      device_role: node.device_role || "",
      reason: "",
    });
  }, [node?.id]);

  useEffect(() => {
    if (!node || !evidenceOpen) return;
    let active = true;
    (async () => {
      setEvidenceLoading(true);
      try {
        const res = await fetch(`${API_BASE}/nodes/${encodeURIComponent(node.id)}/evidence`);
        const json = await res.json();
        if (active && json.success) {
          setEvidenceList(json.evidence || []);
        }
      } catch {
        if (active) pushToast("Gagal memuat bukti observasi node.", "error");
      } finally {
        if (active) setEvidenceLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [node?.id, evidenceOpen, pushToast]);

  if (!node) return null;

  const ownCfg = OWNERSHIP_BADGES[node.ownership_status] || OWNERSHIP_BADGES.unknown;
  const reachCfg = REACHABILITY_BADGES[node.reachability_status] || REACHABILITY_BADGES.unknown;
  const freshCfg = FRESHNESS_BADGES[node.observation_freshness] || FRESHNESS_BADGES.unknown;
  const connectedLinks = links.filter((l) => l.source === node.id || l.target === node.id);

  const applyClassification = async (payload, toastMsg) => {
    setSavingClass(true);
    try {
      const res = await fetch(`${API_BASE}/nodes/${encodeURIComponent(node.id)}/classify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const json = await res.json();
      if (!res.ok || !json.success) {
        pushToast(json.detail || "Gagal memperbarui klasifikasi node.", "error");
        return;
      }
      pushToast(toastMsg || "Klasifikasi perangkat berhasil disimpan.", "success");
      setClassifyOpen(false);
      onRefreshTopology();
    } catch {
      pushToast("Gagal menghubungi endpoint klasifikasi.", "error");
    } finally {
      setSavingClass(false);
    }
  };

  const handleVerifyLink = async (linkId) => {
    try {
      const res = await fetch(`${API_BASE}/links/verify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          link_id: linkId,
          verification_status: "confirmed",
          reason: `Confirmed physical wiring on ${node.name} by administrator.`,
        }),
      });
      const json = await res.json();
      if (json.success) {
        pushToast("Kabel dikonfirmasi sebagai Physical Link terverifikasi!", "success");
        onRefreshTopology();
      } else {
        pushToast(json.detail || "Gagal memverifikasi link.", "error");
      }
    } catch {
      pushToast("Gagal memverifikasi link.", "error");
    }
  };

  return (
    <aside className="absolute right-0 top-12 bottom-0 w-80 sm:w-[410px] bg-black/95 backdrop-blur-2xl border-l border-white/10 p-4 overflow-y-auto shadow-2xl z-40 transition-all">
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-white/10 mb-3">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className={`px-2 py-0.5 rounded-pill text-[10px] font-semibold border ${ownCfg.className}`}>
            {ownCfg.short}
          </span>
          <span className={`px-2 py-0.5 rounded-pill text-[10px] font-medium border ${reachCfg.className}`}>
            {reachCfg.label}
          </span>
          <span className="text-[10px] text-text-secondary capitalize">
            {SCOPE_LABELS[node.topology_scope] || node.topology_scope || node.device_type}
          </span>
        </div>

        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={() => onEditNode({ ...node })}
            className="w-7 h-7 rounded-full flex items-center justify-center text-text-secondary hover:text-text-primary hover:bg-white/10 transition"
            title="Edit detail perangkat"
          >
            <Pencil className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => onDeleteNode(node.id)}
            className="w-7 h-7 rounded-full flex items-center justify-center text-red-400/80 hover:text-red-400 hover:bg-red-500/10 transition"
            title="Hapus perangkat"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={onClose}
            className="w-7 h-7 rounded-full flex items-center justify-center text-text-secondary hover:text-text-primary hover:bg-white/10 transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Title & Identity */}
      <div className="mb-3">
        <div className="flex items-center gap-2">
          <h3 className="text-base font-bold text-text-primary truncate">{node.name}</h3>
          {node.metadata?.is_isp_boundary && (
            <span className="px-1.5 py-0.5 rounded bg-cyan-500/20 text-cyan-200 border border-cyan-400/30 text-[9px] font-bold">
              ISP BOUNDARY
            </span>
          )}
        </div>
        <p className="text-[11px] text-text-secondary font-mono truncate">
          {node.identity || node.name} • <span className="text-text-secondary/60">{node.id}</span>
        </p>
      </div>

      {/* Multi-Dimensional Status Banner */}
      <div className="mb-3 p-2.5 rounded-xl bg-white/5 border border-white/10 space-y-1 text-[11px]">
        <div className="flex items-center justify-between">
          <span className="text-text-secondary">Management:</span>
          <span className="font-mono text-text-primary">
            {MANAGEMENT_LABELS[node.management_status] || node.management_status || "not_attempted"}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-text-secondary">Freshness:</span>
          <span className={`font-mono font-medium ${freshCfg.className}`}>
            {freshCfg.label} ({formatRelativeTime(node.last_seen)})
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-text-secondary">Provenance & Confidence:</span>
          <span className="font-mono text-sky-300">
            {node.provenance || "discovery"} • {(node.confidence || "unknown").toUpperCase()}
          </span>
        </div>
        {node.availability_reason && (
          <p className="text-[10px] text-text-secondary/90 pt-1 border-t border-white/5 leading-snug">
            {node.availability_reason}
          </p>
        )}
      </div>

      {/* NMS Monitoring & Live Telemetry Actions */}
      <div className="mb-3 p-2.5 rounded-xl bg-cyan-950/20 border border-cyan-500/30 text-[11px] space-y-2">
        <div className="flex items-center justify-between">
          <span className="font-semibold text-cyan-200 flex items-center gap-1.5">
            <Activity className="w-3.5 h-3.5 text-cyan-400" />
            NMS Live Telemetry &amp; Traffic
          </span>
          <div className="flex items-center gap-1">
            {node.nms_status && (
              <span className={`text-[9px] px-1.5 py-0.5 rounded font-mono font-semibold ${
                node.nms_status === "UP" ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30" :
                node.nms_status === "DOWN" ? "bg-red-500/20 text-red-300 border border-red-500/30 animate-pulse" :
                "bg-amber-500/20 text-amber-300 border border-amber-500/30"
              }`}>
                {node.nms_status}
              </span>
            )}
            {node.is_stale && (
              <span className="text-[9px] px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40 font-semibold" title="Data pemantauan kedaluwarsa">
                STALE
              </span>
            )}
          </div>
        </div>

        {/* NMS Details */}
        <div className="text-[10px] space-y-1 text-white/70 bg-black/30 p-2 rounded-lg border border-white/5">
          <div className="flex justify-between">
            <span>Metode Pemantauan:</span>
            <span className="font-mono text-cyan-300">{node.monitoring_method || (node.ip ? "icmp_ping" : "-")}</span>
          </div>
          {node.last_check_at && (
            <div className="flex justify-between">
              <span>Terakhir Dicek:</span>
              <span className="font-mono text-white/50">{new Date(node.last_check_at * 1000).toLocaleTimeString()}</span>
            </div>
          )}
          {node.consecutive_failures > 0 && (
            <div className="flex justify-between text-red-400 font-semibold">
              <span>Kegagalan Berturut-turut:</span>
              <span className="font-mono">{node.consecutive_failures}x</span>
            </div>
          )}
          {(node.routeros_model || node.routeros_version) && (
            <div className="flex justify-between text-white/60">
              <span>Perangkat RouterOS:</span>
              <span className="font-mono">{node.routeros_model || ""} {node.routeros_version ? `(v${node.routeros_version})` : ""}</span>
            </div>
          )}
        </div>

        <div className="flex items-center gap-2 pt-1">
          {onOpenNmsDetail && (
            <button
              onClick={() => onOpenNmsDetail(node.id)}
              className="flex-1 py-1.5 px-2 rounded-lg bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/40 text-cyan-300 font-semibold text-[10px] text-center transition"
            >
              Lihat Grafik &amp; Traffic
            </button>
          )}
          {onOpenSnmpWizard && (
            <button
              onClick={() => onOpenSnmpWizard(node)}
              className="py-1.5 px-2.5 rounded-lg bg-emerald-500/20 hover:bg-emerald-500/30 border border-emerald-500/40 text-emerald-300 font-semibold text-[10px] text-center transition flex items-center gap-1"
            >
              <Shield className="w-3 h-3" />
              Setup SNMP
            </button>
          )}
        </div>
      </div>

      {/* Observability Warning (when downstream branch cannot be fully inspected) */}
      {node.observability && node.observability !== "fully_observable" && node.observability_reason && (
        <div className="mb-3 p-2.5 rounded-xl bg-amber-500/10 border border-amber-500/25 text-[11px] text-amber-200 flex items-start gap-2">
          <Eye className="w-3.5 h-3.5 text-amber-400 shrink-0 mt-0.5" />
          <div>
            <span className="font-semibold block text-[10px] uppercase tracking-wider text-amber-300">
              Observability: {node.observability.replace(/_/g, " ")}
            </span>
            <span className="text-[10px] text-amber-100/80 leading-snug">{node.observability_reason}</span>
          </div>
        </div>
      )}

      {/* Hardware & Addressing Grid */}
      <div className="grid grid-cols-2 gap-2 mb-3 text-xs">
        <div className="bg-white/5 border border-white/10 rounded-xl p-2">
          <span className="text-[10px] text-text-secondary block">Primary IP</span>
          <span className="font-mono font-medium text-sky-400 truncate block">{node.ip || "Unspecified"}</span>
          {node.all_ips?.length > 1 && (
            <span className="text-[9px] text-text-secondary font-mono block truncate" title={node.all_ips.join(", ")}>
              +{node.all_ips.length - 1} more IP(s)
            </span>
          )}
        </div>
        <div className="bg-white/5 border border-white/10 rounded-xl p-2">
          <span className="text-[10px] text-text-secondary block">ICMP Latency</span>
          <span className="font-mono font-medium text-emerald-400">
            {node.latency_ms > 0 ? `${node.latency_ms} ms` : "Unprobed"}
          </span>
        </div>
        <div className="bg-white/5 border border-white/10 rounded-xl p-2">
          <span className="text-[10px] text-text-secondary block">MAC Address</span>
          <span className="text-[11px] font-mono text-text-primary truncate block">{node.mac || "Unspecified"}</span>
        </div>
        <div className="bg-white/5 border border-white/10 rounded-xl p-2">
          <span className="text-[10px] text-text-secondary block">Model / Serial</span>
          <span className="text-[11px] text-text-primary truncate block">
            {node.metadata?.board || node.metadata?.model || node.device_type}
            {node.serial_number ? ` (${node.serial_number})` : ""}
          </span>
        </div>
      </div>

      {/* Quick Governance Actions */}
      <div className="mb-3 bg-white/5 border border-white/10 rounded-xl p-2.5 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-text-secondary flex items-center gap-1">
            <Shield className="w-3 h-3 text-sky-400" /> Ownership & Scope Governance
          </span>
          <button
            onClick={() => setClassifyOpen((v) => !v)}
            className="text-[10px] text-sky-400 hover:text-sky-300"
          >
            {classifyOpen ? "Tutup Form" : "Custom Override"}
          </button>
        </div>

        <div className="flex flex-wrap gap-1.5">
          <button
            disabled={savingClass}
            onClick={() =>
              applyClassification(
                {
                  ownership_status: "owned",
                  topology_scope: "enterprise_internal",
                  trust_zone: "internal",
                  is_isp_boundary: false,
                  reason: "Confirmed company-owned internal device by administrator.",
                },
                `${node.name} ditandai sebagai Company-Owned Internal.`
              )
            }
            className="px-2.5 py-1 rounded-pill bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 hover:bg-emerald-500/25 text-[10px] font-medium flex items-center gap-1"
          >
            <CheckCircle2 className="w-3 h-3" /> Confirm Owned
          </button>

          <button
            disabled={savingClass}
            onClick={() =>
              applyClassification(
                {
                  ownership_status: "third_party",
                  topology_scope: "isp_upstream",
                  trust_zone: "isp",
                  is_isp_boundary: true,
                  reason: "Marked as ISP upstream boundary device.",
                },
                `${node.name} ditandai sebagai ISP Boundary.`
              )
            }
            className="px-2.5 py-1 rounded-pill bg-cyan-500/15 text-cyan-200 border border-cyan-400/30 hover:bg-cyan-500/25 text-[10px] font-medium flex items-center gap-1"
          >
            <Globe className="w-3 h-3" /> Mark ISP
          </button>

          <button
            disabled={savingClass}
            onClick={() =>
              applyClassification(
                {
                  excluded_from_discovery: true,
                  reason: "Excluded from recursive topology discovery by administrator.",
                },
                `${node.name} dikecualikan dari recursive discovery.`
              )
            }
            className="px-2.5 py-1 rounded-pill bg-rose-500/15 text-rose-300 border border-rose-500/30 hover:bg-rose-500/25 text-[10px] font-medium"
          >
            Exclude Scan
          </button>
        </div>

        {classifyOpen && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              applyClassification(classForm, "Custom override klasifikasi disimpan.");
            }}
            className="pt-2 border-t border-white/10 space-y-2 text-[11px]"
          >
            <div className="grid grid-cols-2 gap-1.5">
              <div>
                <label className="text-text-secondary block mb-0.5 text-[10px]">Ownership</label>
                <select
                  value={classForm.ownership_status}
                  onChange={(e) => setClassForm({ ...classForm, ownership_status: e.target.value })}
                  className="w-full bg-black border border-white/15 rounded-lg px-2 py-1 text-text-primary"
                >
                  <option value="owned">owned</option>
                  <option value="managed_external">managed_external</option>
                  <option value="third_party">third_party</option>
                  <option value="unknown">unknown</option>
                </select>
              </div>
              <div>
                <label className="text-text-secondary block mb-0.5 text-[10px]">Scope</label>
                <select
                  value={classForm.topology_scope}
                  onChange={(e) => setClassForm({ ...classForm, topology_scope: e.target.value })}
                  className="w-full bg-black border border-white/15 rounded-lg px-2 py-1 text-text-primary"
                >
                  <option value="enterprise_internal">enterprise_internal</option>
                  <option value="enterprise_edge">enterprise_edge</option>
                  <option value="isp_upstream">isp_upstream</option>
                  <option value="external">external</option>
                  <option value="vpn_remote">vpn_remote</option>
                  <option value="unclassified">unclassified</option>
                </select>
              </div>
            </div>
            <input
              type="text"
              placeholder="Alasan audit (opsional)..."
              value={classForm.reason}
              onChange={(e) => setClassForm({ ...classForm, reason: e.target.value })}
              className="w-full bg-black/60 border border-white/15 rounded-lg px-2.5 py-1 text-text-primary"
            />
            <button
              type="submit"
              disabled={savingClass}
              className="w-full py-1.5 rounded-pill bg-sky-500 text-black font-semibold text-[11px]"
            >
              Simpan Override Klasifikasi
            </button>
          </form>
        )}
      </div>

      {/* Supporting Evidence Viewer */}
      <div className="mb-3 bg-white/5 border border-white/10 rounded-xl overflow-hidden">
        <button
          onClick={() => setEvidenceOpen((v) => !v)}
          className="w-full px-3 py-2 flex items-center justify-between text-[11px] font-semibold text-text-primary hover:bg-white/5 transition"
        >
          <span>Supporting Evidence & Confidence Reason</span>
          {evidenceOpen ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
        </button>

        {evidenceOpen && (
          <div className="px-3 pb-3 pt-1 border-t border-white/10 space-y-2 text-[11px]">
            {node.confidence_reason && (
              <p className="text-sky-300/90 text-[10px] leading-snug bg-sky-500/10 border border-sky-500/20 rounded-lg p-2">
                {node.confidence_reason}
              </p>
            )}
            {evidenceLoading ? (
              <p className="text-text-secondary text-[10px]">Memuat bukti observasi...</p>
            ) : evidenceList.length === 0 ? (
              <p className="text-text-secondary text-[10px]">Belum ada rekaman bukti detail untuk perangkat ini.</p>
            ) : (
              evidenceList.map((ev) => (
                <div key={ev.id} className="p-2 rounded-lg bg-black/60 border border-white/10 space-y-0.5">
                  <div className="flex items-center justify-between">
                    <span className="font-mono font-semibold text-emerald-300 text-[10px]">{ev.evidence_type}</span>
                    <span className="text-[9px] text-text-secondary">
                      {ev.freshness} • {formatRelativeTime(ev.observed_at)}
                    </span>
                  </div>
                  {(ev.local_interface || ev.remote_interface) && (
                    <p className="text-[10px] font-mono text-purple-300">
                      Port: {ev.local_interface || "?"} ➔ {ev.remote_interface || "? unspecified"}
                    </p>
                  )}
                  <p className="text-[10px] text-text-secondary">{ev.explanation}</p>
                </div>
              ))
            )}
          </div>
        )}
      </div>

      {/* Connected Links */}
      <div className="mb-4">
        <div className="flex items-center justify-between mb-2">
          <span className="text-[10px] font-semibold uppercase text-text-secondary tracking-wider">
            Links & Wiring ({connectedLinks.length})
          </span>
          <button
            onClick={onOpenAddLink}
            className="text-[10px] text-sky-400 hover:text-sky-300 flex items-center gap-1 transition"
          >
            <Plus className="w-3 h-3" />
            <span>Manual Link</span>
          </button>
        </div>

        <div className="space-y-1.5">
          {connectedLinks.map((link) => {
            const otherId = link.source === node.id ? link.target : link.source;
            const otherNode = nodesMap[otherId];
            const localPort = link.source === node.id ? link.source_port : link.target_port;
            const remotePort = link.source === node.id ? link.target_port : link.source_port;
            const vs = link.verification_status || "unknown";

            return (
              <div
                key={link.id}
                className="p-2 rounded-xl bg-white/5 border border-white/10 hover:border-sky-500/30 transition text-xs space-y-1"
              >
                <div className="flex items-center justify-between">
                  <button
                    onClick={() => otherNode && onSelectNode(otherNode)}
                    className="font-medium text-text-primary hover:text-sky-300 text-left truncate"
                  >
                    {otherNode?.name || otherId}
                  </button>
                  <div className="flex items-center gap-1 shrink-0">
                    <span
                      className={`px-1.5 py-0.5 rounded text-[9px] font-mono uppercase ${
                        vs === "confirmed" || vs === "manual"
                          ? "bg-emerald-500/15 text-emerald-300"
                          : vs === "conflicting"
                          ? "bg-rose-500/20 text-rose-300"
                          : vs === "observed"
                          ? "bg-sky-500/15 text-sky-300"
                          : "bg-slate-500/20 text-slate-300"
                      }`}
                    >
                      {vs} • {link.link_type}
                    </span>
                    {vs !== "confirmed" && vs !== "manual" && (
                      <button
                        onClick={() => handleVerifyLink(link.id)}
                        className="px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30 text-[9px]"
                        title="Konfirmasi sebagai kabel fisik terverifikasi"
                      >
                        ✓
                      </button>
                    )}
                    <button
                      onClick={() => onDeleteLink(link.id)}
                      className="w-5 h-5 rounded flex items-center justify-center text-red-400/70 hover:text-red-400 hover:bg-red-500/10"
                      title="Hapus link"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>
                </div>

                <div className="flex items-center justify-between text-[10px] font-mono text-text-secondary">
                  <span>
                    {localPort || "? local"} ➔ {remotePort || "? unspecified"}
                  </span>
                  <span className="text-purple-300">{link.bandwidth || link.link_type}</span>
                </div>

                {vs === "conflicting" && link.confidence_reason && (
                  <p className="text-[10px] text-rose-300 flex items-center gap-1">
                    <AlertTriangle className="w-3 h-3 shrink-0" /> {link.confidence_reason}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Diagnostic Actions */}
      <div className="space-y-2 pt-2 border-t border-white/10">
        <button
          onClick={() => onTroubleshoot(node)}
          disabled={troubleshooting}
          className="w-full py-2.5 px-4 rounded-pill bg-sakura-gradient text-white text-xs font-semibold shadow-sakura-glow hover:brightness-110 transition flex items-center justify-center gap-1.5 disabled:opacity-50"
        >
          <Zap className="w-3.5 h-3.5 text-amber-300" />
          <span>{troubleshooting ? "Menganalisis..." : "Troubleshoot dengan AIRA"}</span>
        </button>

        <button
          onClick={() => onPingNode(node.id)}
          disabled={pinging}
          className="w-full py-2 px-4 rounded-pill bg-white/5 border border-white/10 hover:bg-white/10 text-text-secondary hover:text-text-primary text-xs font-medium transition flex items-center justify-center gap-1.5 disabled:opacity-50"
        >
          <Activity className="w-3.5 h-3.5 text-sky-400" />
          <span>{pinging ? "Probing ICMP..." : "Test Reachability (ICMP Ping)"}</span>
        </button>
      </div>
    </aside>
  );
}
