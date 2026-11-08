// src/pages/InfrastructurePage.jsx
// AIRA OS - Unified Infrastructure Engineering Workspace
// Mengintegrasikan Topologi Jaringan, Inventaris Perangkat, Monitoring NMS,
// serta Antrean Pending Discovered Devices & Single-Seed Discovery ke dalam satu tampilan terpadu.

import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  ArrowRight,
  CheckCircle2,
  Compass,
  Cpu,
  Eye,
  Key,
  Layers,
  Loader2,
  Lock,
  Network,
  Play,
  Plus,
  RefreshCw,
  Search,
  Server,
  Shield,
  ShieldAlert,
  Sparkles,
  Terminal,
  X,
} from "lucide-react";
import TopologyPage from "./TopologyPage.jsx";
import DevicesPage from "./DevicesPage.jsx";
import NmsPage from "./NmsPage.jsx";
import { useToast } from "../components/Toast.jsx";
import TopBar from "../components/TopBar.jsx";

const TAB_CONFIG = [
  { id: "topology", label: "Topologi", icon: Network },
  { id: "devices", label: "Perangkat", icon: Server },
  { id: "pending", label: "Pending Discovered", icon: Sparkles },
  { id: "nms", label: "Monitoring NMS", icon: Activity },
  { id: "discovery", label: "Discovery Engine", icon: Compass },
];

export default function InfrastructurePage({ onOpenMenu }) {
  const [activeTab, setActiveTab] = useState("topology");
  const [pendingDevices, setPendingDevices] = useState([]);
  const [loadingPending, setLoadingPending] = useState(false);
  const [promoteModalDevice, setPromoteModalDevice] = useState(null);
  const [promoting, setPromoting] = useState(false);
  const [seedForm, setSeedForm] = useState({
    device_name: "",
    host: "",
    mode: "all",
  });
  const [discovering, setDiscovering] = useState(false);
  const [discoveryResult, setDiscoveryResult] = useState(null);

  const { notify } = useToast();

  const fetchPending = useCallback(async () => {
    setLoadingPending(true);
    try {
      const res = await fetch("/api/devices/pending-discovered");
      const data = await res.json();
      if (data.success) {
        setPendingDevices(data.pending_devices || []);
      }
    } catch {
      // silent fail on network blip
    } finally {
      setLoadingPending(false);
    }
  }, []);

  useEffect(() => {
    fetchPending();
    const interval = setInterval(fetchPending, 15000);
    return () => clearInterval(interval);
  }, [fetchPending]);

  const handlePromoteSubmit = async (e) => {
    e.preventDefault();
    if (!promoteModalDevice) return;
    setPromoting(true);

    const form = e.target;
    const payload = {
      node_id: promoteModalDevice.node_id,
      name: form.name.value.trim(),
      host: form.host.value.trim(),
      port: parseInt(form.port.value, 10) || 22,
      username: form.username.value.trim() || "admin",
      password: form.password.value || "",
      device_type: form.device_type.value || "mikrotik",
      snmp_community: form.snmp_community.value.trim() || undefined,
      note: form.note.value.trim() || undefined,
    };

    try {
      const res = await fetch("/api/devices/promote-discovered", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        throw new Error(data.detail || data.error || "Gagal mempromosikan perangkat.");
      }
      notify({
        type: "success",
        message: `Perangkat '${payload.name}' berhasil dipromosikan ke inventory!`,
      });
      setPromoteModalDevice(null);
      fetchPending();
    } catch (err) {
      notify({ type: "error", message: err.message });
    } finally {
      setPromoting(false);
    }
  };

  const handleRunDiscovery = async (e) => {
    e.preventDefault();
    if (!seedForm.host && !seedForm.device_name) {
      notify({ type: "error", message: "Masukkan IP Host atau Nama Seed Router." });
      return;
    }
    setDiscovering(true);
    setDiscoveryResult(null);
    try {
      const res = await fetch("/api/topology/discover", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          device_name: seedForm.device_name || undefined,
          host: seedForm.host || undefined,
          mode: seedForm.mode,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || data.error || "Discovery gagal dijalankan.");
      }
      setDiscoveryResult(data);
      notify({
        type: "success",
        message: `Discovery selesai: ${data.nodes_found || 0} node, ${data.edges_found || 0} link ditemukan.`,
      });
      fetchPending();
    } catch (err) {
      notify({ type: "error", message: err.message });
    } finally {
      setDiscovering(false);
    }
  };

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Infrastructure Top Subnav */}
      <div className="shrink-0 -mx-3 sm:-mx-5 lg:-mx-6 mb-2 px-3 sm:px-5 lg:px-6 py-2 bg-neutral-900/90 backdrop-blur-md border-b border-white/[0.08] flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-1.5 overflow-x-auto py-0.5">
          {TAB_CONFIG.map((t) => {
            const Icon = t.icon;
            const isSelected = activeTab === t.id;
            return (
              <button
                key={t.id}
                onClick={() => setActiveTab(t.id)}
                className={`flex items-center gap-2 px-3.5 py-1.5 rounded-full text-xs font-medium transition whitespace-nowrap ${
                  isSelected
                    ? "bg-cyan-500/15 text-cyan-300 border border-cyan-500/30 shadow-[0_0_12px_rgba(6,182,212,0.15)]"
                    : "text-neutral-400 hover:text-white hover:bg-white/[0.05] border border-transparent"
                }`}
              >
                <Icon size={14} className={isSelected ? "text-cyan-400" : "text-neutral-400"} />
                <span>{t.label}</span>
                {t.id === "pending" && pendingDevices.length > 0 && (
                  <span className="px-1.5 py-0.2 rounded-full text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">
                    {pendingDevices.length}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        <div className="flex items-center gap-2 text-xs text-neutral-400">
          <span className="inline-block w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <span className="font-mono text-[11px] text-neutral-300">Live Infrastructure State</span>
        </div>
      </div>

      {/* Tab Contents */}
      <div className="flex-1 min-h-0">
        {activeTab === "topology" && <TopologyPage onOpenMenu={onOpenMenu} />}
        {activeTab === "devices" && <DevicesPage onOpenMenu={onOpenMenu} />}
        {activeTab === "nms" && <NmsPage onOpenMenu={onOpenMenu} />}

        {/* PENDING DISCOVERED VIEW */}
        {activeTab === "pending" && (
          <div className="h-full overflow-y-auto p-4 space-y-4">
            <TopBar
              title="Pending Discovered Devices"
              subtitle="Perangkat terdeteksi dari pemindaian topologi yang menunggu verifikasi & kredensial manajemen"
              onOpenMenu={onOpenMenu}
            />

            <div className="flex items-center justify-between pb-2 border-b border-white/[0.08]">
              <div>
                <h3 className="text-sm font-semibold text-white">Antrean Review Perangkat</h3>
                <p className="text-xs text-neutral-400">
                  {pendingDevices.length} perangkat terdeteksi di jaringan tetapi belum memiliki kredensial resmi.
                </p>
              </div>
              <button
                onClick={fetchPending}
                disabled={loadingPending}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-neutral-800 hover:bg-neutral-700 text-xs text-neutral-200 border border-neutral-700 transition"
              >
                <RefreshCw size={13} className={loadingPending ? "animate-spin text-cyan-400" : ""} />
                <span>Refresh Antrean</span>
              </button>
            </div>

            {pendingDevices.length === 0 ? (
              <div className="p-12 text-center border border-dashed border-white/10 rounded-2xl bg-neutral-900/30">
                <CheckCircle2 size={36} className="mx-auto text-emerald-400/80 mb-3" />
                <h4 className="text-sm font-medium text-white mb-1">Semua Perangkat Terkelola</h4>
                <p className="text-xs text-neutral-400 max-w-md mx-auto mb-4">
                  Tidak ada perangkat pending yang menunggu promosi. Semua perangkat yang terdeteksi dalam topologi
                  telah memiliki kredensial resmi atau dapat dipindai ulang melalui Discovery Engine.
                </p>
                <button
                  onClick={() => setActiveTab("discovery")}
                  className="px-4 py-2 rounded-xl bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 text-xs font-medium transition inline-flex items-center gap-2"
                >
                  <Compass size={14} />
                  <span>Jalankan Single-Seed Discovery</span>
                </button>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {pendingDevices.map((dev) => (
                  <div
                    key={dev.node_id}
                    className="p-4 rounded-xl bg-neutral-900/70 border border-white/[0.08] hover:border-amber-500/40 transition flex flex-col justify-between space-y-3"
                  >
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs font-mono text-cyan-400 font-semibold">{dev.ip || "No IP"}</span>
                        <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-amber-500/10 text-amber-300 border border-amber-500/20">
                          {dev.discovery_status || "Pending Review"}
                        </span>
                      </div>
                      <h4 className="text-sm font-medium text-white truncate" title={dev.name}>
                        {dev.name || dev.node_id}
                      </h4>
                      <p className="text-xs text-neutral-400 mt-1 line-clamp-2">
                        {dev.status_description || "Membutuhkan kredensial akses untuk dikelola sepenuhnya."}
                      </p>
                      <div className="mt-3 space-y-1 text-[11px] text-neutral-400 font-mono">
                        <div>Tipe: <span className="text-neutral-300">{dev.device_type}</span></div>
                        <div>Vendor: <span className="text-neutral-300">{dev.vendor || "Unknown"}</span></div>
                        <div>Node ID: <span className="text-neutral-400">{dev.node_id}</span></div>
                      </div>
                    </div>

                    <button
                      onClick={() => setPromoteModalDevice(dev)}
                      className="w-full py-2 px-3 rounded-lg bg-amber-500/15 hover:bg-amber-500/25 text-amber-300 border border-amber-500/30 text-xs font-medium transition flex items-center justify-center gap-1.5"
                    >
                      <Key size={13} />
                      <span>Promosikan ke Inventory</span>
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* DISCOVERY ENGINE VIEW */}
        {activeTab === "discovery" && (
          <div className="h-full overflow-y-auto p-4 space-y-6">
            <TopBar
              title="Single-Seed Network Discovery"
              subtitle="Pindai topologi jaringan secara rekursif mulai dari satu router gerbang"
              onOpenMenu={onOpenMenu}
            />

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Form Card */}
              <div className="lg:col-span-1 p-5 rounded-2xl bg-neutral-900/70 border border-white/[0.08] space-y-4">
                <div>
                  <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                    <Compass size={16} className="text-cyan-400" />
                    <span>Konfigurasi Seed Router</span>
                  </h3>
                  <p className="text-xs text-neutral-400 mt-1">
                    Discovery membaca tabel ARP, rute, bridge, dan neighbor discovery protokol (LLDP/CDP/MNDP) dari seed.
                  </p>
                </div>

                <form onSubmit={handleRunDiscovery} className="space-y-3.5">
                  <div>
                    <label className="text-xs font-medium text-neutral-300 block mb-1">Nama Perangkat (Jika Terdaftar)</label>
                    <input
                      type="text"
                      placeholder="mis. Core-1 atau CHR"
                      value={seedForm.device_name}
                      onChange={(e) => setSeedForm({ ...seedForm, device_name: e.target.value })}
                      className="w-full px-3 py-2 rounded-lg bg-neutral-950 border border-white/10 text-xs text-white placeholder-neutral-500 focus:outline-none focus:border-cyan-500"
                    />
                  </div>

                  <div>
                    <label className="text-xs font-medium text-neutral-300 block mb-1">IP Host / Seed IP Address</label>
                    <input
                      type="text"
                      placeholder="10.66.38.1"
                      value={seedForm.host}
                      onChange={(e) => setSeedForm({ ...seedForm, host: e.target.value })}
                      className="w-full px-3 py-2 rounded-lg bg-neutral-950 border border-white/10 text-xs text-white placeholder-neutral-500 focus:outline-none focus:border-cyan-500 font-mono"
                    />
                  </div>

                  <div>
                    <label className="text-xs font-medium text-neutral-300 block mb-1">Mode Discovery</label>
                    <select
                      value={seedForm.mode}
                      onChange={(e) => setSeedForm({ ...seedForm, mode: e.target.value })}
                      className="w-full px-3 py-2 rounded-lg bg-neutral-950 border border-white/10 text-xs text-white focus:outline-none focus:border-cyan-500"
                    >
                      <option value="all">Semua Protokol (Neighbor + ARP + Route + Bridge)</option>
                      <option value="neighbor">Neighbor Only (LLDP / CDP / MNDP)</option>
                      <option value="arp">ARP Discovery Only</option>
                      <option value="route">Route-Based Discovery</option>
                    </select>
                  </div>

                  <button
                    type="submit"
                    disabled={discovering}
                    className="w-full py-2.5 px-4 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-neutral-950 text-xs font-semibold shadow-lg shadow-cyan-500/20 transition disabled:opacity-50 flex items-center justify-center gap-2 mt-2"
                  >
                    {discovering ? (
                      <>
                        <Loader2 size={14} className="animate-spin" />
                        <span>Sedang Memindai Jaringan...</span>
                      </>
                    ) : (
                      <>
                        <Play size={14} />
                        <span>Mulai Discovery dari Seed</span>
                      </>
                    )}
                  </button>
                </form>
              </div>

              {/* Status / Results Card */}
              <div className="lg:col-span-2 space-y-4">
                {discoveryResult ? (
                  <div className="p-5 rounded-2xl bg-neutral-900/70 border border-cyan-500/30 space-y-4">
                    <div className="flex items-center justify-between">
                      <h4 className="text-sm font-semibold text-white flex items-center gap-2">
                        <CheckCircle2 size={16} className="text-cyan-400" />
                        <span>Hasil Pemindaian Jaringan</span>
                      </h4>
                      <span className="text-[11px] font-mono text-neutral-400">
                        Job ID: {discoveryResult.job_id || "direct"}
                      </span>
                    </div>

                    <div className="grid grid-cols-3 gap-3">
                      <div className="p-3 rounded-xl bg-neutral-950 border border-white/5 text-center">
                        <div className="text-xl font-bold text-cyan-400 font-mono">
                          {discoveryResult.nodes_found || 0}
                        </div>
                        <div className="text-[11px] text-neutral-400">Node Ditemukan</div>
                      </div>
                      <div className="p-3 rounded-xl bg-neutral-950 border border-white/5 text-center">
                        <div className="text-xl font-bold text-emerald-400 font-mono">
                          {discoveryResult.edges_found || 0}
                        </div>
                        <div className="text-[11px] text-neutral-400">Hubungan / Link</div>
                      </div>
                      <div className="p-3 rounded-xl bg-neutral-950 border border-white/5 text-center">
                        <div className="text-xl font-bold text-amber-400 font-mono">
                          {discoveryResult.pending_count || pendingDevices.length}
                        </div>
                        <div className="text-[11px] text-neutral-400">Menunggu Kredensial</div>
                      </div>
                    </div>

                    <div className="p-3 rounded-xl bg-neutral-950/80 border border-white/5 text-xs text-neutral-300 font-mono">
                      <div>Status: <span className="text-emerald-400">{discoveryResult.status || "Completed"}</span></div>
                      <div>Mode: <span className="text-neutral-400">{discoveryResult.mode || seedForm.mode}</span></div>
                      {discoveryResult.summary && (
                        <div className="mt-1 text-neutral-400">{discoveryResult.summary}</div>
                      )}
                    </div>

                    <div className="flex items-center gap-3 pt-2">
                      <button
                        onClick={() => setActiveTab("topology")}
                        className="px-4 py-2 rounded-xl bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 text-xs font-medium transition flex items-center gap-1.5"
                      >
                        <Network size={14} />
                        <span>Buka Kanvas Topologi</span>
                      </button>
                      <button
                        onClick={() => setActiveTab("pending")}
                        className="px-4 py-2 rounded-xl bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border border-amber-500/30 text-xs font-medium transition flex items-center gap-1.5"
                      >
                        <Sparkles size={14} />
                        <span>Review Pending Discovered</span>
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="p-12 text-center border border-dashed border-white/10 rounded-2xl bg-neutral-900/30">
                    <Compass size={40} className="mx-auto text-neutral-500 mb-3" />
                    <h4 className="text-sm font-medium text-white mb-1">Siap Menjalankan Discovery</h4>
                    <p className="text-xs text-neutral-400 max-w-sm mx-auto">
                      Pilih router utama atau masukkan IP gerbang untuk memulai pemindaian otomatis topologi tanpa
                      merusak inventaris terkelola yang ada.
                    </p>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* MODAL PROMOTE DISCOVERED DEVICE */}
      {promoteModalDevice && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="w-full max-w-md bg-neutral-900 border border-white/10 rounded-2xl p-5 shadow-2xl space-y-4 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between pb-3 border-b border-white/10">
              <div className="flex items-center gap-2">
                <Key size={18} className="text-amber-400" />
                <h3 className="text-sm font-semibold text-white">Promosikan ke Inventory</h3>
              </div>
              <button
                onClick={() => setPromoteModalDevice(null)}
                className="text-neutral-400 hover:text-white"
              >
                <X size={16} />
              </button>
            </div>

            <form onSubmit={handlePromoteSubmit} className="space-y-3">
              <div>
                <label className="text-xs text-neutral-300 block mb-1 font-medium">Nama Perangkat</label>
                <input
                  type="text"
                  name="name"
                  defaultValue={promoteModalDevice.name || promoteModalDevice.node_id}
                  required
                  className="w-full px-3 py-2 rounded-lg bg-neutral-950 border border-white/10 text-xs text-white focus:outline-none focus:border-amber-500"
                />
              </div>

              <div className="grid grid-cols-3 gap-2">
                <div className="col-span-2">
                  <label className="text-xs text-neutral-300 block mb-1 font-medium">Host / IP</label>
                  <input
                    type="text"
                    name="host"
                    defaultValue={promoteModalDevice.ip || ""}
                    required
                    className="w-full px-3 py-2 rounded-lg bg-neutral-950 border border-white/10 text-xs text-white font-mono focus:outline-none focus:border-amber-500"
                  />
                </div>
                <div>
                  <label className="text-xs text-neutral-300 block mb-1 font-medium">Port SSH</label>
                  <input
                    type="number"
                    name="port"
                    defaultValue={22}
                    className="w-full px-3 py-2 rounded-lg bg-neutral-950 border border-white/10 text-xs text-white font-mono focus:outline-none focus:border-amber-500"
                  />
                </div>
              </div>

              <div>
                <label className="text-xs text-neutral-300 block mb-1 font-medium">Tipe Perangkat</label>
                <select
                  name="device_type"
                  defaultValue={promoteModalDevice.device_type || "mikrotik"}
                  className="w-full px-3 py-2 rounded-lg bg-neutral-950 border border-white/10 text-xs text-white focus:outline-none focus:border-amber-500"
                >
                  <option value="mikrotik">MikroTik RouterOS</option>
                  <option value="cisco">Cisco IOS</option>
                  <option value="linux">Linux Server / Host</option>
                  <option value="switch">Switch L2/L3</option>
                  <option value="olt">OLT</option>
                  <option value="client">Client / Host</option>
                  <option value="other">Lainnya</option>
                </select>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-xs text-neutral-300 block mb-1 font-medium">Username</label>
                  <input
                    type="text"
                    name="username"
                    defaultValue="admin"
                    required
                    className="w-full px-3 py-2 rounded-lg bg-neutral-950 border border-white/10 text-xs text-white focus:outline-none focus:border-amber-500"
                  />
                </div>
                <div>
                  <label className="text-xs text-neutral-300 block mb-1 font-medium">Password</label>
                  <input
                    type="password"
                    name="password"
                    placeholder="••••••••"
                    className="w-full px-3 py-2 rounded-lg bg-neutral-950 border border-white/10 text-xs text-white focus:outline-none focus:border-amber-500"
                  />
                </div>
              </div>

              <div>
                <label className="text-xs text-neutral-300 block mb-1 font-medium">SNMP Community (Opsional)</label>
                <input
                  type="text"
                  name="snmp_community"
                  placeholder="public"
                  className="w-full px-3 py-2 rounded-lg bg-neutral-950 border border-white/10 text-xs text-white focus:outline-none focus:border-amber-500"
                />
              </div>

              <div>
                <label className="text-xs text-neutral-300 block mb-1 font-medium">Catatan (Opsional)</label>
                <input
                  type="text"
                  name="note"
                  placeholder="Dipromosikan dari discovery"
                  className="w-full px-3 py-2 rounded-lg bg-neutral-950 border border-white/10 text-xs text-white focus:outline-none focus:border-amber-500"
                />
              </div>

              <div className="pt-2 flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setPromoteModalDevice(null)}
                  className="px-3.5 py-2 rounded-lg text-xs text-neutral-400 hover:text-white transition"
                >
                  Batal
                </button>
                <button
                  type="submit"
                  disabled={promoting}
                  className="px-4 py-2 rounded-lg bg-amber-500 hover:bg-amber-400 text-neutral-950 font-semibold text-xs transition disabled:opacity-50 flex items-center gap-1.5"
                >
                  {promoting ? (
                    <>
                      <Loader2 size={13} className="animate-spin" />
                      <span>Menyimpan...</span>
                    </>
                  ) : (
                    <span>Promosikan Sekarang</span>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
