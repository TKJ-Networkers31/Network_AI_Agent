// src/components/models/ModelDialog.jsx
import React, { useState } from "react";
import { LABEL_OPTIONS, PROVIDER_OPTIONS } from "./constants.js";

export default function ModelDialog({
  title,
  initial,
  isEdit,
  testing,
  onCancel,
  onSubmit,
  onDelete,
  onTest,
}) {
  const [form, setForm] = useState(initial);
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm px-4">
      <div className="bg-[#18181b] border border-white/10 rounded-2xl w-full max-w-lg p-6 shadow-2xl space-y-4">
        <div className="flex items-center justify-between border-b border-white/10 pb-3">
          <h3 className="font-semibold text-lg text-white">{title}</h3>
          <button
            type="button"
            onClick={onCancel}
            className="text-white/40 hover:text-white transition"
          >
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-white/60 block mb-1">Provider</label>
              <select
                value={form.provider}
                onChange={(e) => update("provider", e.target.value)}
                className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-sakura/50"
              >
                {PROVIDER_OPTIONS.map((p) => (
                  <option key={p.value} value={p.value} className="bg-zinc-900 text-white">
                    {p.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="text-xs text-white/60 block mb-1">Task Label</label>
              <select
                value={form.label}
                onChange={(e) => update("label", e.target.value)}
                className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-sakura/50"
              >
                {LABEL_OPTIONS.map((l) => (
                  <option key={l.value} value={l.value} className="bg-zinc-900 text-white">
                    {l.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label className="text-xs text-white/60 block mb-1">Display Name</label>
            <input
              required
              value={form.display_name}
              onChange={(e) => update("display_name", e.target.value)}
              placeholder="mis. Qwen 2.5 Coder 7B"
              className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-sakura/50"
            />
          </div>

          <div>
            <label className="text-xs text-white/60 block mb-1">Model ID</label>
            <input
              required
              value={form.model_id}
              onChange={(e) => update("model_id", e.target.value)}
              placeholder="mis. qwen2.5-coder:7b atau gemini-1.5-pro"
              className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white font-mono outline-none focus:border-sakura/50"
            />
          </div>

          <div>
            <label className="text-xs text-white/60 block mb-1">Context Window (Tokens)</label>
            <input
              type="number"
              value={form.context_window || ""}
              onChange={(e) => update("context_window", Number(e.target.value))}
              placeholder="mis. 32768 (0 jika tidak tahu)"
              className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-sakura/50"
            />
          </div>

          <div className="flex items-center gap-2 pt-1">
            <input
              type="checkbox"
              id="enabled"
              checked={form.enabled}
              onChange={(e) => update("enabled", e.target.checked)}
              className="rounded border-white/20 bg-white/5 text-sakura focus:ring-sakura/50"
            />
            <label htmlFor="enabled" className="text-sm text-white/80 cursor-pointer">
              Aktifkan Model ini (Enabled)
            </label>
          </div>

          <div className="flex items-center justify-between pt-4 border-t border-white/10">
            <div>
              {isEdit && (
                confirmDelete ? (
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={onDelete}
                      className="px-3 py-1.5 text-xs rounded-lg bg-red-600 hover:bg-red-700 text-white font-medium transition"
                    >
                      Konfirmasi Hapus
                    </button>
                    <button
                      type="button"
                      onClick={() => setConfirmDelete(false)}
                      className="text-xs text-white/60 hover:text-white"
                    >
                      Batal
                    </button>
                  </div>
                ) : (
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setConfirmDelete(true)}
                      className="px-3 py-1.5 text-xs rounded-lg bg-red-500/10 text-red-400 hover:bg-red-500/20 border border-red-500/20 transition"
                    >
                      Hapus
                    </button>
                    <button
                      type="button"
                      onClick={onTest}
                      disabled={testing}
                      className="px-3 py-1.5 text-xs rounded-lg bg-white/5 text-white/70 hover:text-white border border-white/10 transition disabled:opacity-50"
                    >
                      {testing ? "Menguji..." : "Test Koneksi"}
                    </button>
                  </div>
                )
              )}
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={onCancel}
                className="px-4 py-2 text-sm text-white/70 hover:text-white transition"
              >
                Batal
              </button>
              <button
                type="submit"
                disabled={saving}
                className="px-5 py-2 text-sm font-semibold text-white bg-sakura-gradient rounded-full hover:opacity-95 transition disabled:opacity-50"
              >
                {saving ? "Menyimpan..." : isEdit ? "Simpan Perubahan" : "Tambah Model"}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
