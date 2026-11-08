// src/components/models/DefaultRoutingCard.jsx
import React from "react";
import { LABEL_OPTIONS } from "./constants.js";

export default function DefaultRoutingCard({
  models = [],
  routing = {},
  policy = {},
  savingKey,
  onChangeDefault,
  onChangeFallback,
  onChangeRetry,
}) {
  const enabledModels = models.filter((m) => m.enabled);

  return (
    <div className="bg-surface/70 backdrop-blur-xl border border-border rounded-card p-6 space-y-6">
      <div>
        <h3 className="text-base font-semibold text-text-primary">Default Routing & Policy</h3>
        <p className="text-xs text-text-secondary mt-1">
          Atur model default untuk setiap kategori tugas yang dideteksi oleh Classifier, serta fallback saat model utama offline.
        </p>
      </div>

      {/* Grid routing per task label */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {LABEL_OPTIONS.map((item) => {
          const currentId = routing[item.value] || "";
          const isSaving = savingKey === item.value;

          return (
            <div
              key={item.value}
              className="bg-white/[0.02] border border-border rounded-xl p-3 space-y-2"
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-text-primary capitalize">
                  {item.label}
                </span>
                {isSaving && (
                  <span className="text-[10px] text-sakura animate-pulse">Menyimpan...</span>
                )}
              </div>

              <select
                value={currentId}
                disabled={isSaving}
                onChange={(e) => onChangeDefault(item.value, e.target.value || null)}
                className="w-full bg-white/5 border border-border rounded-control px-2.5 py-1.5 text-xs text-text-primary outline-none focus:border-sakura/50"
              >
                <option value="" className="bg-zinc-900 text-text-secondary">
                  -- Pilih Model Default --
                </option>
                {enabledModels.map((m) => (
                  <option key={m.id} value={m.id} className="bg-zinc-900 text-text-primary">
                    {m.display_name} ({m.provider})
                  </option>
                ))}
              </select>
            </div>
          );
        })}
      </div>

      {/* Fallback & Retry Policy */}
      <div className="border-t border-border pt-4 grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-text-primary flex items-center gap-2">
            Fallback Model
            {savingKey === "__fallback__" && (
              <span className="text-[10px] text-sakura animate-pulse">Menyimpan...</span>
            )}
          </label>
          <select
            value={policy.fallback_model_id || ""}
            disabled={savingKey === "__fallback__"}
            onChange={(e) => onChangeFallback(e.target.value || null)}
            className="w-full bg-white/5 border border-border rounded-control px-3 py-2 text-xs text-text-primary outline-none focus:border-sakura/50"
          >
            <option value="" className="bg-zinc-900 text-text-secondary">
              -- Tidak ada fallback --
            </option>
            {enabledModels.map((m) => (
              <option key={m.id} value={m.id} className="bg-zinc-900 text-text-primary">
                {m.display_name} ({m.provider})
              </option>
            ))}
          </select>
          <p className="text-[11px] text-text-secondary">
            Digunakan saat model default untuk suatu label mengalami error/offline.
          </p>
        </div>

        <div className="space-y-1.5">
          <label className="text-xs font-medium text-text-primary flex items-center gap-2">
            Retry Provider Count
            {savingKey === "__retry__" && (
              <span className="text-[10px] text-sakura animate-pulse">Menyimpan...</span>
            )}
          </label>
          <select
            value={policy.retry_provider ?? 0}
            disabled={savingKey === "__retry__"}
            onChange={(e) => onChangeRetry(Number(e.target.value))}
            className="w-full bg-white/5 border border-border rounded-control px-3 py-2 text-xs text-text-primary outline-none focus:border-sakura/50"
          >
            <option value={0} className="bg-zinc-900">0 (Tidak ada retry)</option>
            <option value={1} className="bg-zinc-900">1 kali retry</option>
            <option value={2} className="bg-zinc-900">2 kali retry</option>
            <option value={3} className="bg-zinc-900">3 kali retry</option>
          </select>
          <p className="text-[11px] text-text-secondary">
            Jumlah percobaan ulang jika provider mengembalikan response error (5xx / 429).
          </p>
        </div>
      </div>
    </div>
  );
}
