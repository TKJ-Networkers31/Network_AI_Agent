import { useEffect, useState } from "react";
import TopBar from "../components/TopBar.jsx";
import LocationPanel from "../components/location/LocationPanel.jsx";
import { api } from "../api.js";

export default function SettingsPage({ onOpenMenu }) {
  const [usage, setUsage] = useState(null);
  const [credits, setCredits] = useState(null);

  useEffect(() => {
    api.tokenUsage().then(setUsage).catch(() => {});
    api.credits().then(setCredits).catch(() => {});
  }, []);

  return (
    <div>
      <TopBar
        title="Settings"
        subtitle="Pemakaian token, saldo provider & lokasi"
        onMenuClick={onOpenMenu}
      />

      <div className="bg-card border border-border rounded-xl2 p-4 mb-6 flex items-center gap-3">
        <span className="text-lg">🧩</span>
        <p className="text-sm text-white/60">
          Mau ganti model aktif, atur fallback, atau cek status
          online/offline model? Semua itu sekarang ada di halaman{" "}
          <span className="text-accent-light font-medium">Models</span>.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="bg-card border border-border rounded-xl2 p-5">
          <h3 className="font-semibold mb-2 text-white">Token Sesi Ini</h3>
          {usage ? (
            <div className="text-sm text-white/70 space-y-1">
              <div>Total: {usage.session_total_tokens}</div>
              <div>Prompt: {usage.session_prompt_tokens}</div>
              <div>Completion: {usage.session_completion_tokens}</div>
            </div>
          ) : (
            <p className="text-white/40 text-sm">Belum ada pemakaian.</p>
          )}
        </div>

        <div className="bg-card border border-border rounded-xl2 p-5">
          <h3 className="font-semibold mb-2 text-white">Saldo OpenRouter</h3>
          {credits?.success ? (
            <div className="text-sm text-white/70 space-y-1">
              <div>Total: {credits.total_credits}</div>
              <div>Terpakai: {credits.total_usage}</div>
              <div>Sisa: {credits.remaining}</div>
            </div>
          ) : (
            <p className="text-white/40 text-sm">
              {credits?.error || "Provider aktif (default) bukan API eksternal."}
            </p>
          )}
        </div>
      </div>

      <div className="mt-6">
        <LocationPanel />
      </div>
    </div>
  );
}