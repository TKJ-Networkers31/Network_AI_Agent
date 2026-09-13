import { useEffect, useState } from "react";
import TopBar from "../components/TopBar.jsx";
import { api } from "../api.js";
import { useToast } from "../components/Toast.jsx";
import ConnectionPanel from "../components/connection/ConnectionPanel.jsx";

export default function AkaneWorkspace({ onOpenMenu }) {
  const [devices, setDevices] = useState([]);
  const [connecting, setConnecting] = useState(null);
  const [manualOpen, setManualOpen] = useState(false);
  const [form, setForm] = useState({ host: "", username: "admin", password: "", port: 22 });
  const { notify } = useToast();

  function loadDevices() {
    api
      .devices()
      .then((res) => {
        if (res.success) setDevices(res.devices);
      })
      .catch(() => {});
  }

  useEffect(() => {
    loadDevices();
  }, []);

  async function handleQuickConnect(deviceName) {
    setConnecting(deviceName);
    try {
      const res = await api.connections.open({ device_name: deviceName });
      notify({
        type: "success",
        message: res.reused ? `Sudah tersambung ke ${deviceName}.` : `Terhubung ke ${deviceName}.`,
        duration: 2500,
      });
    } catch (err) {
      notify({ type: "error", message: err.message });
    } finally {
      setConnecting(null);
    }
  }

  async function handleManualConnect(e) {
    e.preventDefault();
    setConnecting("__manual__");
    try {
      await api.connections.open({
        host: form.host.trim(),
        username: form.username.trim(),
        password: form.password || undefined,
        port: Number(form.port) || 22,
      });
      notify({ type: "success", message: `Terhubung ke ${form.host}.`, duration: 2500 });
      setManualOpen(false);
      setForm({ host: "", username: "admin", password: "", port: 22 });
    } catch (err) {
      notify({ type: "error", message: err.message });
    } finally {
      setConnecting(null);
    }
  }

  return (
    <div className="space-y-6">
      <TopBar
        title="AKANE Workspace"
        subtitle="Persistent SSH Connection Engine - satu login, banyak perintah"
        onMenuClick={onOpenMenu}
      />

      <section className="bg-card border border-border rounded-xl2 p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold text-white">Devices (inventory)</h3>
          <button
            onClick={() => setManualOpen((v) => !v)}
            className="text-xs px-3 py-1.5 rounded-lg bg-white/5 text-white/70 hover:text-white"
          >
            {manualOpen ? "Tutup form manual" : "+ Sambung host manual"}
          </button>
        </div>

        {manualOpen && (
          <form
            onSubmit={handleManualConnect}
            className="mb-4 grid grid-cols-1 sm:grid-cols-4 gap-2 bg-white/5 rounded-lg p-3"
          >
            <input
              required
              placeholder="Host / IP"
              value={form.host}
              onChange={(e) => setForm((f) => ({ ...f, host: e.target.value }))}
              className="bg-white/5 border border-border rounded-lg px-3 py-2 text-sm outline-none focus:border-accent"
            />
            <input
              required
              placeholder="Username"
              value={form.username}
              onChange={(e) => setForm((f) => ({ ...f, username: e.target.value }))}
              className="bg-white/5 border border-border rounded-lg px-3 py-2 text-sm outline-none focus:border-accent"
            />
            <input
              type="password"
              placeholder="Password (opsional, fallback .env)"
              value={form.password}
              onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
              className="bg-white/5 border border-border rounded-lg px-3 py-2 text-sm outline-none focus:border-accent"
            />
            <button
              type="submit"
              disabled={connecting === "__manual__"}
              className="bg-accent-gradient text-white text-sm font-semibold rounded-lg px-3 py-2 disabled:opacity-50"
            >
              {connecting === "__manual__" ? "Menyambung..." : "Connect"}
            </button>
          </form>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {devices.map((d) => (
            <div
              key={d.name}
              className="flex items-center justify-between bg-white/5 border border-border rounded-lg px-4 py-3"
            >
              <div>
                <div className="text-sm font-medium text-white">{d.name}</div>
                <div className="text-xs text-white/40 font-mono">{d.host}</div>
              </div>
              <button
                onClick={() => handleQuickConnect(d.name)}
                disabled={connecting === d.name}
                className="text-xs px-3 py-1.5 rounded-lg bg-accent-gradient text-white font-semibold disabled:opacity-50"
              >
                {connecting === d.name ? "..." : "Connect"}
              </button>
            </div>
          ))}

          {devices.length === 0 && (
            <p className="text-white/40 text-sm">Belum ada device di inventory/router.yaml.</p>
          )}
        </div>
      </section>

      <section>
        <h3 className="font-semibold text-white mb-3 px-1">Active Connections</h3>
        <ConnectionPanel />
      </section>
    </div>
  );
}