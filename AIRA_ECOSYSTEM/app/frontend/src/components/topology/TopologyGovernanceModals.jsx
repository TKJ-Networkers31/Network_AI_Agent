// src/components/topology/TopologyGovernanceModals.jsx
// Enterprise Trust Boundary Policy Settings, Review & Conflict Queue, and Accessible Canvas Legend.

import { useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Globe,
  HelpCircle,
  Shield,
  Sliders,
  X,
} from "lucide-react";
import { API_BASE, DISCOVERY_MODES, VIEW_MODES, formatRelativeTime } from "./topologyConstants.js";

function splitCsvLines(text) {
  return String(text || "")
    .split(/[\n,]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

function joinLines(arr) {
  return Array.isArray(arr) ? arr.join("\n") : "";
}

export function PolicySettingsModal({ open, policy, inventoryDevices, onClose, onSaved, pushToast }) {
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    seed_device_id: "",
    discovery_mode: "seed_only",
    view_mode: "internal_and_edge",
    discovery_depth: 1,
    enterprise_subnets: "",
    management_subnets: "",
    approved_discovery_scopes: "",
    excluded_subnets: "",
    isp_boundary_interfaces: "",
    known_isp_devices: "",
    known_external_devices: "",
    allow_routed_expansion: false,
    auto_include_unknown_neighbors: true,
    require_review_for_unknown_devices: true,
    freshness_threshold_sec: 300,
    probe_cooldown_sec: 15,
  });

  useEffect(() => {
    if (!open || !policy) return;
    setForm({
      seed_device_id: policy.seed_device_id || "",
      discovery_mode: policy.discovery_mode || "seed_only",
      view_mode: policy.view_mode || "internal_and_edge",
      discovery_depth: policy.discovery_depth ?? 1,
      enterprise_subnets: joinLines(policy.enterprise_subnets),
      management_subnets: joinLines(policy.management_subnets),
      approved_discovery_scopes: joinLines(policy.approved_discovery_scopes),
      excluded_subnets: joinLines(policy.excluded_subnets),
      isp_boundary_interfaces: joinLines(policy.isp_boundary_interfaces),
      known_isp_devices: joinLines(policy.known_isp_devices),
      known_external_devices: joinLines(policy.known_external_devices),
      allow_routed_expansion: Boolean(policy.allow_routed_expansion),
      auto_include_unknown_neighbors: policy.auto_include_unknown_neighbors !== false,
      require_review_for_unknown_devices: policy.require_review_for_unknown_devices !== false,
      freshness_threshold_sec: policy.freshness_threshold_sec ?? 300,
      probe_cooldown_sec: policy.probe_cooldown_sec ?? 15,
    });
  }, [open, policy]);

  if (!open) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = {
        seed_device_id: form.seed_device_id,
        discovery_mode: form.discovery_mode,
        view_mode: form.view_mode,
        discovery_depth: Number(form.discovery_depth) || 1,
        enterprise_subnets: splitCsvLines(form.enterprise_subnets),
        management_subnets: splitCsvLines(form.management_subnets),
        approved_discovery_scopes: splitCsvLines(form.approved_discovery_scopes),
        excluded_subnets: splitCsvLines(form.excluded_subnets),
        isp_boundary_interfaces: splitCsvLines(form.isp_boundary_interfaces),
        known_isp_devices: splitCsvLines(form.known_isp_devices),
        known_external_devices: splitCsvLines(form.known_external_devices),
        allow_routed_expansion: Boolean(form.allow_routed_expansion),
        auto_include_unknown_neighbors: Boolean(form.auto_include_unknown_neighbors),
        require_review_for_unknown_devices: Boolean(form.require_review_for_unknown_devices),
        freshness_threshold_sec: Number(form.freshness_threshold_sec) || 300,
        probe_cooldown_sec: Number(form.probe_cooldown_sec) || 15,
      };
      const res = await fetch(`${API_BASE}/policy`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const json = await res.json();
      if (!res.ok || !json.success) {
        pushToast(json.detail || "Gagal menyimpan kebijakan topologi.", "error");
        return;
      }
      pushToast("Kebijakan batas Enterprise & ISP berhasil disimpan.", "success");
      onSaved(json.policy);
      onClose();
    } catch {
      pushToast("Gagal menghubungi API kebijakan topologi.", "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-md flex items-center justify-center p-4 z-50">
      <div className="bg-black border border-white/10 rounded-3xl p-6 max-w-2xl w-full max-h-[90vh] overflow-y-auto shadow-2xl relative">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 w-8 h-8 rounded-full flex items-center justify-center text-text-secondary hover:text-text-primary hover:bg-white/10 transition"
        >
          <X className="w-4 h-4" />
        </button>

        <div className="flex items-center gap-2.5 mb-4">
          <div className="w-9 h-9 rounded-xl bg-sky-500/10 border border-sky-500/20 flex items-center justify-center text-sky-400">
            <Sliders className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-text-primary">ISP Boundary & Discovery Policy</h3>
            <p className="text-[11px] text-text-secondary">
              Atur batas jaringan internal perusahaan, interface WAN/ISP, subnet terlarang, dan kedalaman interogasi.
            </p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 text-xs">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <label className="text-text-secondary block mb-1">Seed Router Utama</label>
              <select
                value={form.seed_device_id}
                onChange={(e) => setForm({ ...form, seed_device_id: e.target.value })}
                className="w-full bg-black border border-white/10 rounded-xl px-2.5 py-2 text-text-primary outline-none focus:border-sky-500/50"
              >
                <option value="">Auto (Perangkat Aktif Pertama)</option>
                {(inventoryDevices || []).map((d) => (
                  <option key={d.name} value={d.name}>
                    {d.name} ({d.host})
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="text-text-secondary block mb-1">Mode Discovery</label>
              <select
                value={form.discovery_mode}
                onChange={(e) => setForm({ ...form, discovery_mode: e.target.value })}
                className="w-full bg-black border border-white/10 rounded-xl px-2.5 py-2 text-text-primary outline-none focus:border-sky-500/50"
              >
                {DISCOVERY_MODES.map((m) => (
                  <option key={m.value} value={m.value}>
                    {m.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="text-text-secondary block mb-1">Default View Scope</label>
              <select
                value={form.view_mode}
                onChange={(e) => setForm({ ...form, view_mode: e.target.value })}
                className="w-full bg-black border border-white/10 rounded-xl px-2.5 py-2 text-text-primary outline-none focus:border-sky-500/50"
              >
                {VIEW_MODES.map((v) => (
                  <option key={v.value} value={v.value}>
                    {v.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="text-text-secondary block mb-1">Enterprise Internal Subnets (CIDR, pisah baris/koma)</label>
              <textarea
                rows={2}
                placeholder="10.0.0.0/8&#10;192.168.88.0/24"
                value={form.enterprise_subnets}
                onChange={(e) => setForm({ ...form, enterprise_subnets: e.target.value })}
                className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 font-mono text-[11px] text-text-primary outline-none focus:border-sky-500/50"
              />
            </div>

            <div>
              <label className="text-text-secondary block mb-1">Excluded Subnets (Jangan pernah dipindai)</label>
              <textarea
                rows={2}
                placeholder="100.64.0.0/10&#10;198.51.100.0/24"
                value={form.excluded_subnets}
                onChange={(e) => setForm({ ...form, excluded_subnets: e.target.value })}
                className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 font-mono text-[11px] text-text-primary outline-none focus:border-sky-500/50"
              />
            </div>

            <div>
              <label className="text-text-secondary block mb-1">ISP Boundary Interfaces (mis. ether1, R1:sfp1)</label>
              <textarea
                rows={2}
                placeholder="ether1&#10;pppoe-out1"
                value={form.isp_boundary_interfaces}
                onChange={(e) => setForm({ ...form, isp_boundary_interfaces: e.target.value })}
                className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 font-mono text-[11px] text-text-primary outline-none focus:border-sky-500/50"
              />
            </div>

            <div>
              <label className="text-text-secondary block mb-1">Known ISP / External Gateways (IP / MAC / Identity)</label>
              <textarea
                rows={2}
                placeholder="203.0.113.1&#10;Telkom-PE"
                value={form.known_isp_devices}
                onChange={(e) => setForm({ ...form, known_isp_devices: e.target.value })}
                className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 font-mono text-[11px] text-text-primary outline-none focus:border-sky-500/50"
              />
            </div>

            <div>
              <label className="text-text-secondary block mb-1">Management Subnets (CIDR)</label>
              <input
                type="text"
                placeholder="10.255.0.0/24"
                value={form.management_subnets}
                onChange={(e) => setForm({ ...form, management_subnets: e.target.value })}
                className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 font-mono text-[11px] text-text-primary outline-none focus:border-sky-500/50"
              />
            </div>

            <div>
              <label className="text-text-secondary block mb-1">Approved Expansion Scopes (CIDR)</label>
              <input
                type="text"
                placeholder="10.10.0.0/16"
                value={form.approved_discovery_scopes}
                onChange={(e) => setForm({ ...form, approved_discovery_scopes: e.target.value })}
                className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 font-mono text-[11px] text-text-primary outline-none focus:border-sky-500/50"
              />
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="text-text-secondary block mb-1">Max Hop Depth (1–5)</label>
              <input
                type="number"
                min={1}
                max={5}
                value={form.discovery_depth}
                onChange={(e) => setForm({ ...form, discovery_depth: e.target.value })}
                className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-1.5 font-mono text-text-primary outline-none focus:border-sky-500/50"
              />
            </div>
            <div>
              <label className="text-text-secondary block mb-1">Freshness Window (s)</label>
              <input
                type="number"
                min={30}
                max={86400}
                value={form.freshness_threshold_sec}
                onChange={(e) => setForm({ ...form, freshness_threshold_sec: e.target.value })}
                className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-1.5 font-mono text-text-primary outline-none focus:border-sky-500/50"
              />
            </div>
            <div>
              <label className="text-text-secondary block mb-1">Ping Cooldown (s)</label>
              <input
                type="number"
                min={1}
                max={600}
                value={form.probe_cooldown_sec}
                onChange={(e) => setForm({ ...form, probe_cooldown_sec: e.target.value })}
                className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-1.5 font-mono text-text-primary outline-none focus:border-sky-500/50"
              />
            </div>
          </div>

          <div className="space-y-2 bg-white/5 border border-white/10 rounded-2xl p-3">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={form.require_review_for_unknown_devices}
                onChange={(e) => setForm({ ...form, require_review_for_unknown_devices: e.target.checked })}
                className="accent-sky-400"
              />
              <span>Tandai tetangga tak dikenal sebagai <strong>Pending Review</strong> (tidak pernah otomatis dianggap milik perusahaan)</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={form.auto_include_unknown_neighbors}
                onChange={(e) => setForm({ ...form, auto_include_unknown_neighbors: e.target.checked })}
                className="accent-sky-400"
              />
              <span>Tampilkan perangkat <em>Unknown</em> di mode All Observed / Edge dengan badge peringatan</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={form.allow_routed_expansion}
                onChange={(e) => setForm({ ...form, allow_routed_expansion: e.target.checked })}
                className="accent-sky-400"
              />
              <span>Izinkan ekspansi lintas-subnet/VPN untuk router yang disetujui di Approved Scopes & Inventory</span>
            </label>
          </div>

          <div className="pt-2 flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-pill bg-white/5 hover:bg-white/10 text-text-secondary transition"
            >
              Batal
            </button>
            <button
              type="submit"
              disabled={saving}
              className="px-5 py-2 rounded-pill bg-sakura-gradient text-white font-semibold shadow-sakura-glow hover:brightness-110 transition disabled:opacity-50"
            >
              {saving ? "Menyimpan..." : "Simpan Policy"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export function ReviewQueueModal({ open, onClose, onUpdated, pushToast }) {
  const [tab, setTab] = useState("nodes");
  const [loading, setLoading] = useState(false);
  const [queue, setQueue] = useState({ pending_nodes: [], unverified_links: [], conflicts: [] });

  const loadQueue = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/review`);
      const json = await res.json();
      if (json.success) setQueue(json);
    } catch {
      pushToast("Gagal memuat antrean review.", "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) loadQueue();
  }, [open]);

  if (!open) return null;

  const quickClassifyNode = async (nodeId, payload, msg) => {
    try {
      const res = await fetch(`${API_BASE}/nodes/${encodeURIComponent(nodeId)}/classify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const json = await res.json();
      if (json.success) {
        pushToast(msg, "success");
        await loadQueue();
        onUpdated();
      } else {
        pushToast(json.detail || "Gagal mengklasifikasikan perangkat.", "error");
      }
    } catch {
      pushToast("Gagal menyimpan klasifikasi.", "error");
    }
  };

  const quickVerifyLink = async (linkId) => {
    try {
      const res = await fetch(`${API_BASE}/links/verify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          link_id: linkId,
          verification_status: "confirmed",
          reason: "Confirmed via Review Queue by administrator.",
        }),
      });
      const json = await res.json();
      if (json.success) {
        pushToast("Link berhasil diverifikasi sebagai kabel fisik!", "success");
        await loadQueue();
        onUpdated();
      } else {
        pushToast(json.detail || "Gagal memverifikasi link.", "error");
      }
    } catch {
      pushToast("Gagal memverifikasi link.", "error");
    }
  };

  const resolveConflict = async (conflictId, status) => {
    try {
      const res = await fetch(`${API_BASE}/conflicts/${conflictId}/resolve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      });
      const json = await res.json();
      if (json.success) {
        pushToast(`Konflik ditandai '${status}'.`, "success");
        await loadQueue();
        onUpdated();
      }
    } catch {
      pushToast("Gagal memperbarui status konflik.", "error");
    }
  };

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-md flex items-center justify-center p-4 z-50">
      <div className="bg-black border border-white/10 rounded-3xl p-6 max-w-2xl w-full max-h-[88vh] flex flex-col shadow-2xl relative">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 w-8 h-8 rounded-full flex items-center justify-center text-text-secondary hover:text-text-primary hover:bg-white/10 transition"
        >
          <X className="w-4 h-4" />
        </button>

        <div className="flex items-center gap-2.5 mb-4">
          <div className="w-9 h-9 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400">
            <Shield className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-text-primary">Governance Review & Conflict Queue</h3>
            <p className="text-[11px] text-text-secondary">
              Konfirmasi kepemilikan perangkat tak dikenal, verifikasi kabel fisik, dan tinjau konflik port/IP.
            </p>
          </div>
        </div>

        <div className="flex gap-1.5 mb-3 bg-white/5 p-1 rounded-pill border border-white/10 w-fit text-xs">
          <button
            onClick={() => setTab("nodes")}
            className={`px-3 py-1 rounded-pill transition ${tab === "nodes" ? "bg-sky-500 text-black font-semibold" : "text-text-secondary"}`}
          >
            Unknown Devices ({queue.pending_nodes?.length || 0})
          </button>
          <button
            onClick={() => setTab("links")}
            className={`px-3 py-1 rounded-pill transition ${tab === "links" ? "bg-sky-500 text-black font-semibold" : "text-text-secondary"}`}
          >
            Unverified Links ({queue.unverified_links?.length || 0})
          </button>
          <button
            onClick={() => setTab("conflicts")}
            className={`px-3 py-1 rounded-pill transition ${tab === "conflicts" ? "bg-rose-500 text-white font-semibold" : "text-text-secondary"}`}
          >
            Conflicts ({queue.conflicts?.length || 0})
          </button>
        </div>

        <div className="flex-1 overflow-y-auto space-y-2 pr-1 text-xs">
          {loading && <p className="text-text-secondary py-6 text-center">Memuat antrean review...</p>}

          {!loading && tab === "nodes" && (
            queue.pending_nodes.length === 0 ? (
              <p className="text-text-secondary py-8 text-center">Semua perangkat pada graf telah terklasifikasi.</p>
            ) : (
              queue.pending_nodes.map((n) => (
                <div key={n.id} className="p-3 rounded-2xl bg-white/5 border border-white/10 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-text-primary">{n.name}</span>
                      <span className="text-[10px] font-mono text-sky-400">{n.ip || n.mac || "no-ip"}</span>
                      <span className="text-[10px] px-2 py-0.5 rounded-pill bg-amber-500/15 text-amber-300 border border-amber-500/30">
                        {n.topology_scope}
                      </span>
                    </div>
                    <p className="text-[11px] text-text-secondary mt-0.5">{n.confidence_reason || "Ownership requires administrator confirmation."}</p>
                  </div>
                  <div className="flex flex-wrap gap-1.5 shrink-0">
                    <button
                      onClick={() =>
                        quickClassifyNode(
                          n.id,
                          { ownership_status: "owned", topology_scope: "enterprise_internal", trust_zone: "internal", reason: "Confirmed company-owned internal device" },
                          `${n.name} dikonfirmasi sebagai Owned Internal.`
                        )
                      }
                      className="px-2.5 py-1 rounded-pill bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 hover:bg-emerald-500/25 text-[11px] flex items-center gap-1"
                    >
                      <CheckCircle2 className="w-3 h-3" /> Owned
                    </button>
                    <button
                      onClick={() =>
                        quickClassifyNode(
                          n.id,
                          { ownership_status: "third_party", topology_scope: "isp_upstream", trust_zone: "isp", is_isp_boundary: true, reason: "Marked as ISP upstream boundary device" },
                          `${n.name} ditandai sebagai ISP Boundary.`
                        )
                      }
                      className="px-2.5 py-1 rounded-pill bg-cyan-500/15 text-cyan-200 border border-cyan-400/30 hover:bg-cyan-500/25 text-[11px] flex items-center gap-1"
                    >
                      <Globe className="w-3 h-3" /> ISP
                    </button>
                    <button
                      onClick={() =>
                        quickClassifyNode(
                          n.id,
                          { excluded_from_discovery: true, ownership_status: "third_party", topology_scope: "external", trust_zone: "external", reason: "Excluded from enterprise topology" },
                          `${n.name} dikecualikan dari topologi internal.`
                        )
                      }
                      className="px-2.5 py-1 rounded-pill bg-rose-500/15 text-rose-300 border border-rose-500/30 hover:bg-rose-500/25 text-[11px]"
                    >
                      Exclude
                    </button>
                  </div>
                </div>
              ))
            )
          )}

          {!loading && tab === "links" && (
            queue.unverified_links.length === 0 ? (
              <p className="text-text-secondary py-8 text-center">Tidak ada link observasi/inferensi yang menunggu verifikasi.</p>
            ) : (
              queue.unverified_links.map((l) => (
                <div key={l.id} className="p-3 rounded-2xl bg-white/5 border border-white/10 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                  <div>
                    <div className="font-mono text-xs text-text-primary">
                      {l.source} <span className="text-sky-400">({l.source_port || "?"})</span> ➔ {l.target}{" "}
                      <span className="text-purple-400">({l.target_port || "? unspecified"})</span>
                    </div>
                    <p className="text-[11px] text-text-secondary mt-0.5">
                      [{l.verification_status.toUpperCase()} • {l.link_type}] {l.confidence_reason}
                    </p>
                  </div>
                  <button
                    onClick={() => quickVerifyLink(l.id)}
                    className="px-3 py-1 rounded-pill bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 hover:bg-emerald-500/25 text-[11px] shrink-0"
                  >
                    ✓ Confirm Physical
                  </button>
                </div>
              ))
            )
          )}

          {!loading && tab === "conflicts" && (
            queue.conflicts.length === 0 ? (
              <p className="text-text-secondary py-8 text-center">Tidak ada konflik identitas, IP, atau port yang terbuka.</p>
            ) : (
              queue.conflicts.map((c) => (
                <div key={c.id} className="p-3 rounded-2xl bg-rose-500/10 border border-rose-500/25 space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-rose-300 flex items-center gap-1">
                      <AlertTriangle className="w-3.5 h-3.5" /> {c.conflict_type} — {c.subject_id}
                    </span>
                    <span className="text-[10px] text-text-secondary">{formatRelativeTime(c.created_at)}</span>
                  </div>
                  <p className="text-[11px] text-text-primary">{c.reason}</p>
                  <div className="flex justify-end gap-2 pt-1">
                    <button
                      onClick={() => resolveConflict(c.id, "ignored")}
                      className="px-2.5 py-1 rounded-pill bg-white/5 hover:bg-white/10 text-text-secondary text-[11px]"
                    >
                      Ignore
                    </button>
                    <button
                      onClick={() => resolveConflict(c.id, "resolved")}
                      className="px-3 py-1 rounded-pill bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 text-[11px]"
                    >
                      Mark Resolved
                    </button>
                  </div>
                </div>
              ))
            )
          )}
        </div>
      </div>
    </div>
  );
}

export function TopologyLegendOverlay({ open, onToggle }) {
  if (!open) {
    return (
      <button
        onClick={onToggle}
        className="absolute bottom-4 right-4 bg-black/85 backdrop-blur-xl border border-white/10 rounded-pill px-3 py-1.5 text-[11px] text-text-secondary hover:text-text-primary flex items-center gap-1.5 shadow-lg z-20"
      >
        <HelpCircle className="w-3.5 h-3.5 text-sky-400" />
        <span>Legend</span>
      </button>
    );
  }

  return (
    <div className="absolute bottom-4 right-4 w-72 bg-black/90 backdrop-blur-xl border border-white/15 rounded-2xl p-3.5 text-[11px] shadow-2xl z-20 space-y-2.5">
      <div className="flex items-center justify-between border-b border-white/10 pb-1.5">
        <span className="font-semibold text-text-primary">Topology V2 Visual Legend</span>
        <button onClick={onToggle} className="text-text-secondary hover:text-text-primary">
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      <div className="space-y-1.5">
        <span className="text-[10px] uppercase tracking-wider text-text-secondary block font-semibold">
          Link Verification & Type
        </span>
        <div className="flex items-center gap-2">
          <span className="w-8 h-0.5 bg-gradient-to-r from-sky-400 to-purple-500 inline-block" />
          <span className="text-emerald-300 font-mono">✓ Verified / Manual</span>
          <span className="text-text-secondary ml-auto">Physical</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-8 h-0.5 bg-sky-400 inline-block" />
          <span className="text-sky-300 font-mono">Observed (?)</span>
          <span className="text-text-secondary ml-auto">1-Sided L2</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-8 border-t border-dashed border-slate-400 inline-block" />
          <span className="text-slate-300 font-mono">Inferred / Routed</span>
          <span className="text-text-secondary ml-auto">ARP / L3</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-8 border-t-2 border-dotted border-purple-400 inline-block" />
          <span className="text-purple-300 font-mono">VPN</span>
          <span className="text-text-secondary ml-auto">Tunnel</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-8 border-t-2 border-dashed border-rose-500 inline-block" />
          <span className="text-rose-400 font-mono">⚠ Conflict</span>
          <span className="text-text-secondary ml-auto">Port Mismatch</span>
        </div>
      </div>

      <div className="space-y-1 pt-1 border-t border-white/10">
        <span className="text-[10px] uppercase tracking-wider text-text-secondary block font-semibold">
          Ownership & Boundary Badges
        </span>
        <div className="flex flex-wrap gap-1">
          <span className="px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 text-[9px]">OWNED</span>
          <span className="px-1.5 py-0.5 rounded bg-cyan-500/15 text-cyan-200 border border-cyan-400/35 text-[9px]">ISP / 3RD</span>
          <span className="px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-300 border border-amber-500/35 text-[9px]">REVIEW</span>
          <span className="px-1.5 py-0.5 rounded bg-sky-500/15 text-sky-300 border border-sky-500/30 text-[9px]">MGD-EXT</span>
        </div>
      </div>
    </div>
  );
}
