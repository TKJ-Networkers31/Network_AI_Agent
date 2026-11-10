// src/pages/ModelsPage.jsx
// Centralized AI Model Management, Real-Time Synchronization & Provider Circuit Breaker UI.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import TopBar from "../components/TopBar.jsx";
import { useToast } from "../components/Toast.jsx";
import { modelRouterApi as api } from "../modelRouterApi.js";
import { CAPABILITY_OPTIONS, LABEL_OPTIONS, formatContext } from "../components/models/constants.js";
import {
  CapabilityBadge,
  CircuitBadge,
  HealthBadge,
  LabelBadge,
  LifecycleBadge,
  ProviderBadge,
  StatusBadge,
} from "../components/models/Badges.jsx";
import ModelDialog from "../components/models/ModelDialog.jsx";
import DefaultRoutingCard from "../components/models/DefaultRoutingCard.jsx";

const EMPTY_FORM = {
  provider: "nvidia", display_name: "", model_id: "",
  label: "general", context_window: 32768, enabled: true,
  publisher: "nvidia", priority: 10, model_type: "dense",
  supports_streaming: true, supports_tool_calling: false, supports_vision: false,
};

const COLS = "grid grid-cols-[1.6fr_0.9fr_0.8fr_1fr_0.7fr_0.6fr_0.7fr] gap-3";

function buildModelsWsUrl() {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const host =
    window.location.port === "5173"
      ? `${window.location.hostname}:8000`
      : window.location.host;
  return `${proto}//${host}/ws/models`;
}

export default function ModelsPage({ onOpenMenu }) {
  const { notify } = useToast();

  const [models, setModels] = useState([]);
  const [routing, setRouting] = useState({});
  const [policy, setPolicy] = useState({ fallback_model_id: null, retry_provider: 0 });
  const [providers, setProviders] = useState([]);
  const [syncStatus, setSyncStatus] = useState(null);
  const [loading, setLoading] = useState(true);

  // Filters
  const [filterLabel, setFilterLabel] = useState("all");
  const [filterCapability, setFilterCapability] = useState("all");
  const [filterProvider, setFilterProvider] = useState("all");
  const [search, setSearch] = useState("");

  // UI States
  const [dialog, setDialog] = useState(null); // null | {mode:"add"} | {mode:"edit", model}
  const [savingKey, setSavingKey] = useState(null);
  const [testing, setTesting] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [resettingProvider, setResettingProvider] = useState(null);
  const [wsStatus, setWsStatus] = useState("connecting"); // connecting | open | closed

  const wsRef = useRef(null);
  const isUnmounted = useRef(false);

  // REST loader (also serves as fallback if WebSocket disconnects)
  const load = useCallback(async (silent = false) => {
    try {
      if (!silent) setLoading(true);
      const [listRes, routeRes, provRes, syncRes] = await Promise.all([
        api.list(),
        api.routing(),
        api.getProviders().catch(() => ({ providers: [] })),
        api.getSyncStatus().catch(() => null),
      ]);
      setModels(listRes.models || []);
      setRouting(routeRes.routing || {});
      setPolicy(routeRes.policy || { fallback_model_id: null, retry_provider: 0 });
      setProviders(provRes.providers || []);
      if (syncRes) setSyncStatus(syncRes);
    } catch (err) {
      if (!silent) notify({ type: "error", message: err.message });
    } finally {
      if (!silent) setLoading(false);
    }
  }, [notify]);

  // Initial load
  useEffect(() => {
    load();
  }, [load]);

  // Real-Time WebSocket Synchronization
  useEffect(() => {
    isUnmounted.current = false;

    function connectWs() {
      if (isUnmounted.current) return;
      const existing = wsRef.current;
      if (existing && (existing.readyState === WebSocket.OPEN || existing.readyState === WebSocket.CONNECTING)) {
        return;
      }

      setWsStatus("connecting");
      let ws;
      try {
        ws = new WebSocket(buildModelsWsUrl());
      } catch {
        setWsStatus("closed");
        return;
      }
      wsRef.current = ws;

      ws.onopen = () => {
        if (wsRef.current === ws) {
          setWsStatus("open");
        }
      };

      ws.onmessage = (event) => {
        if (wsRef.current !== ws) return;
        try {
          const frame = JSON.parse(event.data);
          const type = frame.type;

          if (type === "model_registry_snapshot") {
            const data = frame.data || {};
            if (data.models) setModels(data.models);
            if (data.routing) setRouting(data.routing);
            if (data.policy) setPolicy(data.policy);
          } else if (
            type === "model_registry_updated" ||
            type === "model_status_changed" ||
            type === "provider_health_changed" ||
            type === "model_availability_changed" ||
            type === "model_priority_changed" ||
            type === "model_discovery_completed" ||
            type === "active_model_changed"
          ) {
            // Hot update: refresh data silently from backend
            load(true);
          }
        } catch {
          // ignore invalid frame
        }
      };

      ws.onclose = () => {
        if (wsRef.current === ws) {
          setWsStatus("closed");
          // Reconnect with backoff
          setTimeout(() => {
            if (!isUnmounted.current) connectWs();
          }, 5000);
        }
      };

      ws.onerror = () => {
        if (wsRef.current === ws) {
          setWsStatus("closed");
        }
      };
    }

    connectWs();

    // Fallback polling every 15 seconds
    const interval = setInterval(() => {
      if (!document.hidden) {
        load(true);
      }
    }, 15000);

    return () => {
      isUnmounted.current = true;
      clearInterval(interval);
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [load]);

  // Client-side filtering & search
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return models.filter((m) => {
      if (filterLabel !== "all" && m.label !== filterLabel) return false;
      if (filterProvider !== "all" && m.provider !== filterProvider) return false;
      if (filterCapability !== "all") {
        const caps = m.capabilities || [];
        if (filterCapability === "tool_calling" && !m.supports_tool_calling && !caps.includes("tool_calling")) {
          return false;
        }
        if (filterCapability === "streaming" && !m.supports_streaming && !caps.includes("streaming")) {
          return false;
        }
        if (filterCapability === "vision" && !m.supports_vision && !caps.includes("vision")) {
          return false;
        }
        if (filterCapability === "structured_output" && !m.supports_structured_output && !caps.includes("structured_output")) {
          return false;
        }
      }
      if (q) {
        const nameMatch = (m.display_name || "").toLowerCase().includes(q);
        const idMatch = (m.model_id || "").toLowerCase().includes(q);
        const pubMatch = (m.publisher || "").toLowerCase().includes(q);
        if (!nameMatch && !idMatch && !pubMatch) return false;
      }
      return true;
    });
  }, [models, filterLabel, filterProvider, filterCapability, search]);

  // Model Dialog Actions
  async function handleSubmit(form) {
    const payload = {
      provider: form.provider,
      display_name: form.display_name.trim(),
      model_id: form.model_id.trim(),
      label: form.label,
      publisher: (form.publisher || "").trim(),
      context_window: Number(form.context_window) || 0,
      priority: Number(form.priority) || 10,
      model_type: form.model_type || "dense",
      supports_streaming: Boolean(form.supports_streaming),
      supports_tool_calling: Boolean(form.supports_tool_calling),
      supports_vision: Boolean(form.supports_vision),
      enabled: form.enabled,
    };

    try {
      if (dialog.mode === "edit") {
        await api.update(dialog.model.id, payload);
      } else {
        await api.create(payload);
      }

      notify({
        type: "success",
        message: dialog.mode === "edit" ? "Model diperbarui." : "Model ditambahkan.",
        duration: 2500,
      });
      setDialog(null);
      await load(true);
    } catch (err) {
      notify({ type: "error", message: err.message });
    }
  }

  async function handleDelete() {
    try {
      await api.remove(dialog.model.id);
      notify({ type: "success", message: `"${dialog.model.display_name}" dihapus.`, duration: 2500 });
      setDialog(null);
      await load(true);
    } catch (err) {
      notify({ type: "error", message: err.message });
    }
  }

  async function handleTest() {
    setTesting(true);
    try {
      const res = await api.healthCheck(dialog.model.id);
      notify({
        type: res.online ? "success" : "error",
        message: `${dialog.model.display_name}: ${res.online ? "Online & Verified" : "Offline"} (${res.message || "OK"})`,
        duration: 3500,
      });
      await load(true);
    } catch (err) {
      notify({ type: "error", message: err.message });
    } finally {
      setTesting(false);
    }
  }

  // Quick toggle enabled status directly from table
  async function handleToggleStatus(e, model) {
    e.stopPropagation();
    const nextState = !model.enabled;
    try {
      await api.updateStatus(model.id, nextState);
      notify({
        type: "success",
        message: `${model.display_name} ${nextState ? "diaktifkan" : "dinonaktifkan"}.`,
        duration: 2000,
      });
      await load(true);
    } catch (err) {
      notify({ type: "error", message: err.message });
    }
  }

  // Remote Catalog Synchronization
  async function handleSyncCatalog() {
    setSyncing(true);
    try {
      const res = await api.syncRemote("nvidia");
      notify({
        type: "success",
        message: `Katalog tersinkronisasi: ${res.remote_count} model remote terverifikasi, ${res.updated_count} diperbarui.`,
        duration: 4000,
      });
      await load(true);
    } catch (err) {
      notify({ type: "error", message: `Sinkronisasi gagal: ${err.message}` });
    } finally {
      setSyncing(false);
    }
  }

  // Reset tripped circuit breaker
  async function handleResetCircuit(providerId) {
    setResettingProvider(providerId);
    try {
      await api.resetProviderCircuit(providerId);
      notify({
        type: "success",
        message: `Circuit breaker untuk ${providerId.toUpperCase()} berhasil di-reset.`,
        duration: 3000,
      });
      await load(true);
    } catch (err) {
      notify({ type: "error", message: err.message });
    } finally {
      setResettingProvider(null);
    }
  }

  // Routing changes
  async function saveRouting(key, action, successMessage) {
    setSavingKey(key);
    try {
      await action();
      notify({ type: "success", message: successMessage, duration: 2000 });
      await load(true);
    } catch (err) {
      notify({ type: "error", message: err.message });
    } finally {
      setSavingKey(null);
    }
  }

  const handleChangeDefault = (label, modelId) =>
    saveRouting(label, () => api.setDefault(label, modelId), `Default ${label} diperbarui.`);
  const handleChangeFallback = (modelId) =>
    saveRouting("__fallback__", () => api.setPolicy({ fallback_model_id: modelId }), "Fallback diperbarui.");
  const handleChangeRetry = (count) =>
    saveRouting("__retry__", () => api.setPolicy({ retry_provider: count }), "Retry diperbarui.");

  return (
    <div className="space-y-6">
      <TopBar
        title="AI Model Intelligence Registry"
        subtitle="Authoritative Model Catalog · Telemetri Circuit Breaker · Routing & Failover Otomatis"
        onMenuClick={onOpenMenu}
      />

      {/* Provider Health & Circuit Status Bar */}
      <div className="bg-surface/70 backdrop-blur-xl border border-border rounded-card p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-text-primary uppercase tracking-wide">
              Upstream Provider Circuit Telemetry
            </span>
            <span className="inline-flex items-center gap-1.5 text-[10px] text-text-secondary">
              <span
                className={`w-2 h-2 rounded-full ${
                  wsStatus === "open" ? "bg-emerald-400" : wsStatus === "connecting" ? "bg-amber-400 animate-pulse" : "bg-red-400"
                }`}
              />
              WS {wsStatus === "open" ? "Live Sync" : wsStatus === "connecting" ? "Connecting..." : "Polling Fallback"}
            </span>
          </div>

          <button
            onClick={handleSyncCatalog}
            disabled={syncing}
            className="flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded-lg bg-lime-500/10 text-lime-300 border border-lime-500/20 hover:bg-lime-500/20 transition disabled:opacity-50"
          >
            {syncing ? (
              <>
                <span className="w-3 h-3 border-2 border-lime-400 border-t-transparent rounded-full animate-spin" />
                Syncing NVIDIA NIM...
              </>
            ) : (
              <>⚡ Sync Remote Catalog</>
            )}
          </button>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {providers.map((p) => {
            const isTripped = p.circuit_state === "OPEN";
            const isResetting = resettingProvider === p.id;

            return (
              <div
                key={p.id}
                className="p-3 bg-white/[0.02] border border-border rounded-xl space-y-2"
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-text-primary capitalize">{p.name}</span>
                  <CircuitBadge state={p.circuit_state} />
                </div>

                <div className="flex items-center justify-between text-[11px] text-text-secondary font-mono">
                  <span>Latency: {p.avg_latency_s ? `${Math.round(p.avg_latency_s * 1000)}ms` : "N/A"}</span>
                  <span>{p.models_count || 0} Models</span>
                </div>

                {isTripped && (
                  <div className="pt-1 flex items-center justify-between">
                    <span className="text-[10px] text-red-400">Circuit Terbuka</span>
                    <button
                      type="button"
                      disabled={isResetting}
                      onClick={() => handleResetCircuit(p.id)}
                      className="px-2 py-0.5 text-[10px] rounded bg-red-600 hover:bg-red-500 text-white font-medium transition"
                    >
                      {isResetting ? "Resetting..." : "Reset Circuit"}
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Toolbar / Filters */}
      <div className="flex flex-col sm:flex-row gap-2 sm:items-center">
        {/* Label filter */}
        <select
          value={filterLabel}
          onChange={(e) => setFilterLabel(e.target.value)}
          className="bg-white/5 border border-border rounded-control px-3 py-2 text-sm text-text-primary outline-none focus:border-sakura/50"
        >
          <option value="all" className="bg-zinc-900 text-text-primary">Semua Label Tugas</option>
          {LABEL_OPTIONS.map((l) => (
            <option key={l.value} value={l.value} className="bg-zinc-900 text-text-primary">{l.label}</option>
          ))}
        </select>

        {/* Capability filter */}
        <select
          value={filterCapability}
          onChange={(e) => setFilterCapability(e.target.value)}
          className="bg-white/5 border border-border rounded-control px-3 py-2 text-sm text-text-primary outline-none focus:border-sakura/50"
        >
          {CAPABILITY_OPTIONS.map((c) => (
            <option key={c.value} value={c.value} className="bg-zinc-900 text-text-primary">{c.label}</option>
          ))}
        </select>

        {/* Provider filter */}
        <select
          value={filterProvider}
          onChange={(e) => setFilterProvider(e.target.value)}
          className="bg-white/5 border border-border rounded-control px-3 py-2 text-sm text-text-primary outline-none focus:border-sakura/50"
        >
          <option value="all" className="bg-zinc-900 text-text-primary">Semua Provider</option>
          <option value="nvidia" className="bg-zinc-900 text-text-primary">NVIDIA NIM</option>
          <option value="openrouter" className="bg-zinc-900 text-text-primary">OpenRouter</option>
          <option value="gemini" className="bg-zinc-900 text-text-primary">Google Gemini</option>
        </select>

        {/* Search */}
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Cari model, publisher, atau ID..."
          className="flex-1 bg-white/5 border border-border rounded-control px-3 py-2 text-sm text-text-primary outline-none focus:border-sakura/50"
        />

        <button
          onClick={() => setDialog({ mode: "add" })}
          className="bg-sakura-gradient text-white text-sm font-semibold px-4 py-2 rounded-pill whitespace-nowrap shadow-md hover:opacity-95 transition"
        >
          + Tambah Model
        </button>
      </div>

      {/* Tabel Model Catalog */}
      <div className="bg-surface/70 backdrop-blur-xl border border-border rounded-card overflow-hidden">
        <div className="overflow-x-auto">
          <div className="min-w-[840px]">
            <div className={`${COLS} px-4 py-2.5 text-[10px] uppercase tracking-wide text-text-secondary/70 border-b border-border`}>
              <span>Model & Publisher</span>
              <span>Provider</span>
              <span>Label</span>
              <span>Capabilities</span>
              <span>Context</span>
              <span>Priority</span>
              <span>Status</span>
            </div>

            {filtered.map((m) => (
              <div
                key={m.id}
                onClick={() => setDialog({ mode: "edit", model: m })}
                className={`${COLS} w-full items-center text-left px-4 py-3 border-b border-border last:border-b-0 hover:bg-white/[0.04] transition cursor-pointer`}
              >
                {/* Model & Publisher */}
                <div className="min-w-0 pr-2">
                  <div className="flex items-center gap-1.5">
                    <span className="text-sm font-medium text-text-primary truncate">{m.display_name}</span>
                    {m.publisher && (
                      <span className="text-[10px] font-mono text-text-secondary/80 bg-white/5 px-1.5 py-0.2 rounded">
                        {m.publisher}
                      </span>
                    )}
                  </div>
                  <span className="block text-[11px] text-text-secondary font-mono truncate">{m.model_id}</span>
                </div>

                {/* Provider */}
                <div>
                  <ProviderBadge provider={m.provider} />
                </div>

                {/* Label */}
                <div>
                  <LabelBadge label={m.label} />
                </div>

                {/* Capabilities */}
                <div className="flex flex-wrap gap-1">
                  {m.supports_tool_calling && <CapabilityBadge capability="tool_calling" />}
                  {m.supports_streaming && <CapabilityBadge capability="streaming" />}
                  {m.supports_vision && <CapabilityBadge capability="vision" />}
                  {m.supports_structured_output && <CapabilityBadge capability="structured_output" />}
                  {!m.supports_tool_calling && !m.supports_vision && (
                    <span className="text-[10px] text-text-secondary/50 font-mono">Text</span>
                  )}
                </div>

                {/* Context Window */}
                <div className="text-xs text-text-secondary font-mono">
                  {formatContext(m.context_window)}
                </div>

                {/* Priority */}
                <div className="text-xs text-text-secondary font-mono font-semibold">
                  P{m.priority !== undefined ? m.priority : 10}
                </div>

                {/* Status Toggle & Lifecycle */}
                <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
                  <button
                    type="button"
                    onClick={(e) => handleToggleStatus(e, m)}
                    className="focus:outline-none"
                    title={m.enabled ? "Klik untuk menonaktifkan" : "Klik untuk mengaktifkan"}
                  >
                    <StatusBadge enabled={m.enabled} />
                  </button>
                  {m.health_status && m.health_status !== "HEALTHY" && (
                    <HealthBadge status={m.health_status} />
                  )}
                </div>
              </div>
            ))}

            {!loading && filtered.length === 0 && (
              <p className="text-text-secondary text-sm text-center py-8">
                {models.length === 0
                  ? 'Belum ada model. Klik "+ Tambah Model" atau "Sync Remote Catalog".'
                  : "Tidak ada model yang cocok dengan filter."}
              </p>
            )}

            {loading && <p className="text-text-secondary text-sm text-center py-8">Memuat model...</p>}
          </div>
        </div>
      </div>

      {/* Default Routing & Failover Policy Card */}
      <DefaultRoutingCard
        models={models}
        routing={routing}
        policy={policy}
        savingKey={savingKey}
        onChangeDefault={handleChangeDefault}
        onChangeFallback={handleChangeFallback}
        onChangeRetry={handleChangeRetry}
      />

      {/* Edit / Add Modal */}
      {dialog && (
        <ModelDialog
          key={dialog.model?.id || "new"}
          title={dialog.mode === "edit" ? `Edit — ${dialog.model.display_name}` : "Tambah Model"}
          initial={dialog.mode === "edit" ? { ...dialog.model } : EMPTY_FORM}
          isEdit={dialog.mode === "edit"}
          testing={testing}
          providers={providers}
          onCancel={() => setDialog(null)}
          onSubmit={handleSubmit}
          onDelete={handleDelete}
          onTest={handleTest}
        />
      )}
    </div>
  );
}
