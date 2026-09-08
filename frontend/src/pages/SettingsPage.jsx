import { useEffect, useState } from "react";
import TopBar from "../components/TopBar.jsx";
import { api } from "../api.js";

export default function SettingsPage() {
  const [providers, setProviders] = useState([]);
  const [activeKey, setActiveKey] = useState(null);
  const [usage, setUsage] = useState(null);
  const [credits, setCredits] = useState(null);
  const [error, setError] = useState(null);

  function load() {
    api
      .providers()
      .then((res) => {
        setProviders(res.providers);
        setActiveKey(res.active_key);
      })
      .catch((e) => setError(e.message));

    api.tokenUsage().then(setUsage).catch(() => {});
    api.credits().then(setCredits).catch(() => {});
  }

  useEffect(() => {
    load();
  }, []);

  async function handleSelect(key) {
    try {
      await api.selectProvider(key);
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div>
      <TopBar title="Settings" subtitle="Model aktif & pemakaian token" />

      {error && (
        <div className="text-sm mb-4 px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/20 text-red-300">
          {error}
        </div>
      )}

      <div className="bg-card border border-border rounded-xl2 p-5 mb-6">
        <h3 className="font-semibold mb-4 text-white">Model / Provider Aktif</h3>
        <div className="space-y-2">
          {providers.map((p) => (
            <label
              key={p.key}
              className={`flex items-center justify-between px-4 py-3 rounded-lg border cursor-pointer transition
                ${
                  p.key === activeKey
                    ? "border-accent bg-accent/10"
                    : "border-border hover:bg-white/5"
                }`}
            >
              <div>
                <div className="text-sm text-white/90">{p.label}</div>
                <div className="text-[10px] uppercase tracking-wide text-white/40">
                  {p.type}
                </div>
              </div>
              <input
                type="radio"
                name="provider"
                checked={p.key === activeKey}
                onChange={() => handleSelect(p.key)}
                className="accent-accent w-4 h-4"
              />
            </label>
          ))}
        </div>
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
              {credits?.error || "Provider aktif bukan API eksternal."}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
