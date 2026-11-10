// src/components/models/DefaultRoutingCard.jsx
import React from "react";
import { LABEL_OPTIONS } from "./constants.js";
import { HealthBadge } from "./Badges.jsx";

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
  const modelsById = Object.fromEntries(models.map((m) => [m.id, m]));

  return (
    <div className="bg-surface/70 backdrop-blur-xl border border-border rounded-card p-6 space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
        <div>
          <h3 className="text-base font-semibold text-text-primary">Default Routing & Policy</h3>
          <p className="text-xs text-text-secondary mt-1">
            Atur model default untuk setiap kategori tugas yang dideteksi oleh Classifier, serta fallback otomatis saat model utama offline.
          </p>
        </div>
      </div>

      {/* Grid routing per task label */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {LABEL_OPTIONS.map((item) => {
          const currentId = routing[item.value] || "";
          const isSaving = savingKey === item.value;
          const currentModel = modelsById[currentId];

          return (
            <div
              key={item.value}
              className="bg-white/[0.02] border border-border rounded-xl p-3 space-y-2"
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-text-primary capitalize">
                  {item.label}
                </span>
                {isSaving ? (
                  <span className="text-[10px] text-sakura animate-pulse">Menyimpan...</span>
                ) : currentModel?.health_status ? (
                  <HealthBadge status={currentModel.health_status} />
                ) : null}
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
                    {m.display_name} ({m.provider}) {m.health_status === "UNAVAILABLE" ? "⚠️ Offline" : ""}
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
          <label className="text-xs font-medium text-text-primary flex items-center justify-between">
            <span>Fallback Model (Redundansi Antar-Provider)</span>
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
            Digunakan saat model default mengalami timeout atau circuit breaker terbuka (wajib provider independen).
          </p>
        </div>

        <div className="space-y-1.5">
          <label className="text-xs font-medium text-text-primary flex items-center justify-between">
            <span>Retry Provider Count</span>
            {savingKey === "__retry__" && (
              <span className="text-[10px] text-sakura animate-pulse">Menyimpan...</span>
            )}
          </label>
          <div className="flex items-center gap-2">
            {[0, 1, 2, 3].map((n) => (
              <button
                key={n}
                type="button"
                onClick={() => onChangeRetry(n)}
                disabled={savingKey === "__retry__"}
                className={`flex-1 py-1.5 rounded-lg border text-xs font-medium transition ${
                  policy.retry_provider === n
                    ? "bg-sakura/20 border-sakura text-sakura"
                    : "bg-white/5 border-border text-text-secondary hover:text-text-primary"
                }`}
              >
                {n}x Retry
              </button>
            ))}
          </div>
          <p className="text-[11px] text-text-secondary">
            Batas percobaan ulang sebelum beralih ke fallback model.
          </p>
        </div>
      </div>
    </div>
  );
}
