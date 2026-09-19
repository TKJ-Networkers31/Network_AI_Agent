// Halaman Models (Sprint 1 - Model Router). Menggantikan halaman Model
// Management Phase 1.2: daftar model + label, Default Routing per tugas,
// fallback & retry. Filter/search hanya mengubah tampilan (client-side),
// jadi dropdown Default Routing selalu memakai daftar model lengkap.

import { useCallback, useEffect, useMemo, useState } from "react";
import TopBar from "../components/TopBar.jsx";
import { useToast } from "../components/Toast.jsx";
import { modelRouterApi as api } from "../modelRouterApi.js";
import { LABEL_OPTIONS, formatContext } from "../components/models/constants.js";
import { LabelBadge, ProviderBadge, StatusBadge } from "../components/models/Badges.jsx";
import ModelDialog from "../components/models/ModelDialog.jsx";
import DefaultRoutingCard from "../components/models/DefaultRoutingCard.jsx";

const EMPTY_FORM = {
  provider: "ollama", display_name: "", model_id: "",
  label: "general", context_window: 0, enabled: true,
};

const COLS = "grid grid-cols-[1.8fr_1fr_1fr_1fr_0.8fr] gap-3";

export default function ModelsPage({ onOpenMenu }) {
  const { notify } = useToast();

  const [models, setModels] = useState([]);
  const [routing, setRouting] = useState({});
  const [policy, setPolicy] = useState({ fallback_model_id: null, retry_provider: 0 });
  const [loading, setLoading] = useState(true);
  const [filterLabel, setFilterLabel] = useState("all");
  const [search, setSearch] = useState("");
  const [dialog, setDialog] = useState(null); // null | {mode:"add"} | {mode:"edit", model}
  const [savingKey, setSavingKey] = useState(null);
  const [testing, setTesting] = useState(false);

  const load = useCallback(async () => {
    try {
      const [list, route] = await Promise.all([api.list(), api.routing()]);
      setModels(list.models);
      setRouting(route.routing);
      setPolicy(route.policy);
    } catch (err) {
      notify({ type: "error", message: err.message });
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    load();
  }, [load]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return models.filter(
      (m) =>
        (filterLabel === "all" || m.label === filterLabel) &&
        (!q || m.display_name.toLowerCase().includes(q) || m.model_id.toLowerCase().includes(q))
    );
  }, [models, filterLabel, search]);

  async function handleSubmit(form) {
    const payload = {
      provider: form.provider,
      display_name: form.display_name.trim(),
      model_id: form.model_id.trim(),
      label: form.label,
      context_window: Number(form.context_window) || 0,
      enabled: form.enabled,
    };

    try {
      if (dialog.mode === "edit") await api.update(dialog.model.id, payload);
      else await api.create(payload);

      notify({
        type: "success",
        message: dialog.mode === "edit" ? "Model diperbarui." : "Model ditambahkan.",
        duration: 2500,
      });
      setDialog(null);
      await load();
    } catch (err) {
      notify({ type: "error", message: err.message });
    }
  }

  async function handleDelete() {
    try {
      await api.remove(dialog.model.id);
      notify({ type: "success", message: `"${dialog.model.display_name}" dihapus.`, duration: 2500 });
      setDialog(null);
      await load();
    } catch (err) {
      notify({ type: "error", message: err.message });
    }
  }

  async function handleTest() {
    setTesting(true);
    try {
      const res = await api.testConnection(dialog.model.id);
      notify({
        type: res.online ? "success" : "error",
        message: `${dialog.model.display_name}: ${res.online ? "Online" : "Offline"}${res.message && res.message !== "OK" ? ` (${res.message})` : ""}`,
        duration: 3500,
      });
    } catch (err) {
      notify({ type: "error", message: err.message });
    } finally {
      setTesting(false);
    }
  }

  async function saveRouting(key, action, successMessage) {
    setSavingKey(key);
    try {
      await action();
      notify({ type: "success", message: successMessage, duration: 2000 });
      await load();
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
        title="Models"
        subtitle="Routing otomatis · kelola model, label, default & fallback"
        onMenuClick={onOpenMenu}
      />

      {/* Toolbar */}
      <div className="flex flex-col sm:flex-row gap-2 sm:items-center">
        <select
          value={filterLabel}
          onChange={(e) => setFilterLabel(e.target.value)}
          className="bg-white/5 border border-border rounded-control px-3 py-2 text-sm text-text-primary outline-none focus:border-sakura/50"
        >
          <option value="all">All Models</option>
          {LABEL_OPTIONS.map((l) => (
            <option key={l.value} value={l.value}>{l.label}</option>
          ))}
        </select>

        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Cari model..."
          className="flex-1 bg-white/5 border border-border rounded-control px-3 py-2 text-sm text-text-primary outline-none focus:border-sakura/50"
        />

        <button
          onClick={() => setDialog({ mode: "add" })}
          className="bg-sakura-gradient text-white text-sm font-semibold px-4 py-2 rounded-pill whitespace-nowrap"
        >
          + Tambah Model
        </button>
      </div>

      {/* Tabel */}
      <div className="bg-surface/70 backdrop-blur-xl border border-border rounded-card overflow-hidden">
        <div className="overflow-x-auto">
          <div className="min-w-[640px]">
            <div className={`${COLS} px-4 py-2.5 text-[10px] uppercase tracking-wide text-text-secondary/70 border-b border-border`}>
              <span>Display</span><span>Provider</span><span>Label</span><span>Context</span><span>Status</span>
            </div>

            {filtered.map((m) => (
              <button
                key={m.id}
                type="button"
                onClick={() => setDialog({ mode: "edit", model: m })}
                className={`${COLS} w-full items-center text-left px-4 py-3 border-b border-border last:border-b-0 hover:bg-white/[0.04] transition`}
              >
                <span className="min-w-0">
                  <span className="block text-sm text-text-primary truncate">{m.display_name}</span>
                  <span className="block text-[11px] text-text-secondary font-mono truncate">{m.model_id}</span>
                </span>
                <span><ProviderBadge provider={m.provider} /></span>
                <span><LabelBadge label={m.label} /></span>
                <span className="text-xs text-text-secondary font-mono">{formatContext(m.context_window)}</span>
                <span><StatusBadge enabled={m.enabled} /></span>
              </button>
            ))}

            {!loading && filtered.length === 0 && (
              <p className="text-text-secondary text-sm text-center py-8">
                {models.length === 0
                  ? 'Belum ada model. Klik "+ Tambah Model".'
                  : "Tidak ada model yang cocok dengan filter."}
              </p>
            )}

            {loading && <p className="text-text-secondary text-sm text-center py-8">Memuat model...</p>}
          </div>
        </div>
      </div>

      <DefaultRoutingCard
        models={models}
        routing={routing}
        policy={policy}
        savingKey={savingKey}
        onChangeDefault={handleChangeDefault}
        onChangeFallback={handleChangeFallback}
        onChangeRetry={handleChangeRetry}
      />

      {dialog && (
        <ModelDialog
          key={dialog.model?.id || "new"}
          title={dialog.mode === "edit" ? `Edit — ${dialog.model.display_name}` : "Tambah Model"}
          initial={dialog.mode === "edit" ? { ...dialog.model } : EMPTY_FORM}
          isEdit={dialog.mode === "edit"}
          testing={testing}
          onCancel={() => setDialog(null)}
          onSubmit={handleSubmit}
          onDelete={handleDelete}
          onTest={handleTest}
        />
      )}
    </div>
  );
}