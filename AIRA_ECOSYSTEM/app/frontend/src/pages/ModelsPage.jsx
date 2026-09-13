// Taruh file ini di: AIRA_ECOSYSTEM/app/frontend/src/pages/ModelsPage.jsx (BARU)
//
// Workspace REI -> Model Management. List model + status online/offline,
// provider badge, default badge, fallback badge, Add/Edit dialog, Delete
// confirmation, Test Connection. Setiap aksi langsung memuat ulang list
// dari server supaya tampilan selalu mencerminkan state terbaru.

import { useEffect, useState } from "react";
import TopBar from "../components/TopBar.jsx";
import { api } from "../api.js";
import { useToast } from "../components/Toast.jsx";

const PROVIDER_OPTIONS = [
  { value: "ollama", label: "Ollama (lokal)" },
  { value: "openrouter", label: "OpenRouter" },
  { value: "gemini", label: "Google Gemini" },
];

const EMPTY_FORM = {
  nickname: "",
  provider: "ollama",
  model_id: "",
  endpoint: "",
  api_key: "",
  enabled: true,
};

const PROVIDER_COLORS = {
  openrouter: "bg-fuchsia-500/10 text-fuchsia-300 border-fuchsia-500/20",
  gemini: "bg-sky-500/10 text-sky-300 border-sky-500/20",
  ollama: "bg-emerald-500/10 text-emerald-300 border-emerald-500/20",
};

function ProviderBadge({ provider }) {
  const color = PROVIDER_COLORS[provider] || "bg-white/5 text-white/50 border-white/10";

  return (
    <span className={`text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full border ${color}`}>
      {provider}
    </span>
  );
}

function StatusDot({ status }) {
  const cfg =
    status === "online"
      ? { dot: "bg-emerald-400", label: "Online" }
      : status === "offline"
      ? { dot: "bg-red-400", label: "Offline" }
      : { dot: "bg-white/30", label: "Belum dicek" };

  return (
    <span className="flex items-center gap-1.5 text-[11px] text-white/50 shrink-0">
      <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`} />
      {cfg.label}
    </span>
  );
}

function ModelDialog({ title, initial, isEdit, onCancel, onSubmit }) {
  const [form, setForm] = useState(initial);
  const [saving, setSaving] = useState(false);

  function update(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setSaving(true);
    try {
      await onSubmit(form);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 px-4">
      <div className="bg-panel border border-border rounded-xl2 w-full max-w-md p-5 max-h-[90vh] overflow-y-auto">
        <h3 className="font-semibold text-white mb-4">{title}</h3>

        <form onSubmit={handleSubmit} className="space-y-3">
          {!isEdit && (
            <div>
              <label className="text-xs text-white/50 block mb-1">Nickname</label>
              <input
                required
                value={form.nickname}
                onChange={(e) => update("nickname", e.target.value)}
                className="w-full bg-white/5 border border-border rounded-lg px-3 py-2 text-sm outline-none focus:border-accent"
                placeholder="mis. ollama-qwen3-4b"
              />
            </div>
          )}

          <div>
            <label className="text-xs text-white/50 block mb-1">Provider</label>
            <select
              value={form.provider}
              onChange={(e) => update("provider", e.target.value)}
              className="w-full bg-white/5 border border-border rounded-lg px-3 py-2 text-sm outline-none focus:border-accent"
            >
              {PROVIDER_OPTIONS.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="text-xs text-white/50 block mb-1">Model ID</label>
            <input
              required
              value={form.model_id}
              onChange={(e) => update("model_id", e.target.value)}
              className="w-full bg-white/5 border border-border rounded-lg px-3 py-2 text-sm outline-none focus:border-accent"
              placeholder="mis. qwen3:4b atau nvidia/nemotron-3.5-lightning:free"
            />
          </div>

          <div>
            <label className="text-xs text-white/50 block mb-1">Endpoint (opsional)</label>
            <input
              value={form.endpoint || ""}
              onChange={(e) => update("endpoint", e.target.value)}
              className="w-full bg-white/5 border border-border rounded-lg px-3 py-2 text-sm outline-none focus:border-accent"
              placeholder="kosongkan untuk pakai default sesuai provider"
            />
          </div>

          <div>
            <label className="text-xs text-white/50 block mb-1">
              API Key {isEdit ? "(kosongkan jika tidak ingin mengubah)" : "(opsional untuk Ollama)"}
            </label>
            <input
              type="password"
              value={form.api_key || ""}
              onChange={(e) => update("api_key", e.target.value)}
              className="w-full bg-white/5 border border-border rounded-lg px-3 py-2 text-sm outline-none focus:border-accent"
              placeholder={isEdit ? "••••••••" : "kosongkan untuk pakai .env"}
              autoComplete="new-password"
            />
          </div>

          <label className="flex items-center gap-2 text-sm text-white/70 select-none">
            <input
              type="checkbox"
              checked={form.enabled}
              onChange={(e) => update("enabled", e.target.checked)}
              className="accent-accent"
            />
            Enabled
          </label>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onCancel}
              className="text-sm px-4 py-2 rounded-lg bg-white/5 text-white/60 hover:text-white"
            >
              Batal
            </button>
            <button
              type="submit"
              disabled={saving}
              className="text-sm px-4 py-2 rounded-lg bg-accent-gradient text-white font-semibold disabled:opacity-50"
            >
              {saving ? "Menyimpan..." : "Simpan"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function ModelsPage({ onOpenMenu }) {
  const [models, setModels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [editTarget, setEditTarget] = useState(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);
  const [testingId, setTestingId] = useState(null);
  const { notify } = useToast();

  function load() {
    setLoading(true);
    api.models
      .list()
      .then((res) => setModels(res.models))
      .catch((e) => notify({ type: "error", message: e.message }))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleCreate(form) {
    try {
      await api.models.create({
        nickname: form.nickname.trim(),
        provider: form.provider,
        model_id: form.model_id.trim(),
        endpoint: form.endpoint?.trim() || null,
        api_key: form.api_key?.trim() || null,
        enabled: form.enabled,
      });
      notify({ type: "success", message: "Model ditambahkan.", duration: 2500 });
      setShowAdd(false);
      load();
    } catch (err) {
      notify({ type: "error", message: err.message });
    }
  }

  async function handleUpdate(nickname, form) {
    try {
      const payload = {
        provider: form.provider,
        model_id: form.model_id.trim(),
        endpoint: form.endpoint?.trim() || null,
        enabled: form.enabled,
      };

      if (form.api_key && form.api_key.trim()) {
        payload.api_key = form.api_key.trim();
      }

      await api.models.update(nickname, payload);
      notify({ type: "success", message: "Model diperbarui.", duration: 2500 });
      setEditTarget(null);
      load();
    } catch (err) {
      notify({ type: "error", message: err.message });
    }
  }

  async function handleDelete(nickname) {
    try {
      await api.models.remove(nickname);
      notify({ type: "success", message: `Model "${nickname}" dihapus.`, duration: 2500 });
      setConfirmDeleteId(null);
      load();
    } catch (err) {
      notify({ type: "error", message: err.message });
    }
  }

  async function handleSetDefault(nickname) {
    try {
      await api.models.setDefault(nickname);
      notify({ type: "success", message: `"${nickname}" dijadikan default.`, duration: 2500 });
      load();
    } catch (err) {
      notify({ type: "error", message: err.message });
    }
  }

  async function handleToggleFallback(model) {
    try {
      await api.models.setFallback(model.nickname, !model.is_fallback);
      load();
    } catch (err) {
      notify({ type: "error", message: err.message });
    }
  }

  async function handleToggleEnabled(model) {
    try {
      await api.models.setEnabled(model.nickname, !model.enabled);
      load();
    } catch (err) {
      notify({ type: "error", message: err.message });
    }
  }

  async function handleTestConnection(nickname) {
    setTestingId(nickname);
    try {
      const res = await api.models.testConnection(nickname);
      notify({
        type: res.online ? "success" : "error",
        message: `${nickname}: ${res.online ? "Online" : "Offline"}${res.message ? ` (${res.message})` : ""}`,
        duration: 3500,
      });
      load();
    } catch (err) {
      notify({ type: "error", message: err.message });
    } finally {
      setTestingId(null);
    }
  }

  return (
    <div>
      <TopBar
        title="Model Management"
        subtitle="Workspace REI · kelola provider LLM, default, fallback, dan health check"
        onMenuClick={onOpenMenu}
      />

      <div className="flex justify-end mb-4">
        <button
          onClick={() => setShowAdd(true)}
          className="bg-accent-gradient text-white text-sm font-semibold px-4 py-2 rounded-lg"
        >
          + Tambah Model
        </button>
      </div>

      {loading && <p className="text-white/40 text-sm">Memuat model...</p>}

      <div className="space-y-3">
        {models.map((m) => (
          <div key={m.nickname} className="bg-card border border-border rounded-xl2 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
              <div className="flex items-center gap-2 flex-wrap min-w-0">
                <span className="font-semibold text-white truncate">{m.nickname}</span>
                <ProviderBadge provider={m.provider} />
                {m.is_default && (
                  <span className="text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full bg-accent/20 text-accent-light border border-accent/30">
                    Default
                  </span>
                )}
                {m.is_fallback && (
                  <span className="text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-300 border border-amber-500/20">
                    Fallback
                  </span>
                )}
                {!m.enabled && (
                  <span className="text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full bg-white/5 text-white/40 border border-white/10">
                    Disabled
                  </span>
                )}
              </div>
              <StatusDot status={m.last_status} />
            </div>

            <div className="text-xs text-white/50 mb-3 space-y-0.5">
              <div>
                Model ID: <span className="text-white/80 font-mono">{m.model_id}</span>
              </div>
              {m.endpoint && (
                <div>
                  Endpoint: <span className="text-white/70 font-mono">{m.endpoint}</span>
                </div>
              )}
              <div>API Key: {m.has_api_key ? "sudah diset" : "belum diset (pakai .env jika ada)"}</div>
            </div>

            {confirmDeleteId === m.nickname ? (
              <div className="flex items-center justify-between gap-2 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
                <span className="text-xs text-red-300">Hapus model ini?</span>
                <div className="flex gap-1.5">
                  <button
                    onClick={() => handleDelete(m.nickname)}
                    className="text-[11px] font-medium px-2.5 py-1 rounded-md bg-red-500/20 text-red-300 hover:bg-red-500/30"
                  >
                    Hapus
                  </button>
                  <button
                    onClick={() => setConfirmDeleteId(null)}
                    className="text-[11px] px-2.5 py-1 rounded-md bg-white/5 text-white/50 hover:text-white"
                  >
                    Batal
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                <button
                  onClick={() => handleTestConnection(m.nickname)}
                  disabled={testingId === m.nickname}
                  className="text-[11px] px-2.5 py-1.5 rounded-lg bg-white/5 text-white/70 hover:text-white disabled:opacity-50"
                >
                  {testingId === m.nickname ? "Menguji..." : "Test Connection"}
                </button>
                <button
                  onClick={() => handleSetDefault(m.nickname)}
                  disabled={m.is_default || !m.enabled}
                  className="text-[11px] px-2.5 py-1.5 rounded-lg bg-white/5 text-white/70 hover:text-white disabled:opacity-30"
                >
                  Set Default
                </button>
                <button
                  onClick={() => handleToggleFallback(m)}
                  className="text-[11px] px-2.5 py-1.5 rounded-lg bg-white/5 text-white/70 hover:text-white"
                >
                  {m.is_fallback ? "Lepas Fallback" : "Set Fallback"}
                </button>
                <button
                  onClick={() => handleToggleEnabled(m)}
                  className="text-[11px] px-2.5 py-1.5 rounded-lg bg-white/5 text-white/70 hover:text-white"
                >
                  {m.enabled ? "Disable" : "Enable"}
                </button>
                <button
                  onClick={() => setEditTarget(m)}
                  className="text-[11px] px-2.5 py-1.5 rounded-lg bg-white/5 text-white/70 hover:text-white"
                >
                  Edit
                </button>
                <button
                  onClick={() => setConfirmDeleteId(m.nickname)}
                  className="text-[11px] px-2.5 py-1.5 rounded-lg bg-red-500/10 text-red-300 hover:bg-red-500/20"
                >
                  Hapus
                </button>
              </div>
            )}
          </div>
        ))}

        {!loading && models.length === 0 && (
          <p className="text-white/40 text-sm text-center py-8">
            Belum ada model terdaftar. Klik &quot;+ Tambah Model&quot; untuk menambahkan.
          </p>
        )}
      </div>

      {showAdd && (
        <ModelDialog
          title="Tambah Model"
          initial={EMPTY_FORM}
          isEdit={false}
          onCancel={() => setShowAdd(false)}
          onSubmit={handleCreate}
        />
      )}

      {editTarget && (
        <ModelDialog
          title={`Edit Model — ${editTarget.nickname}`}
          initial={{
            nickname: editTarget.nickname,
            provider: editTarget.provider,
            model_id: editTarget.model_id,
            endpoint: editTarget.endpoint || "",
            api_key: "",
            enabled: editTarget.enabled,
          }}
          isEdit
          onCancel={() => setEditTarget(null)}
          onSubmit={(form) => handleUpdate(editTarget.nickname, form)}
        />
      )}
    </div>
  );
}