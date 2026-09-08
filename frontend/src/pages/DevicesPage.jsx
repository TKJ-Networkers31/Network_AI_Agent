import { useEffect, useState } from "react";
import TopBar from "../components/TopBar.jsx";
import { api } from "../api.js";

export default function DevicesPage() {
  const [devices, setDevices] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .devices()
      .then((res) => {
        if (res.success) setDevices(res.devices);
        else setError(res.error);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <TopBar
        title="Devices"
        subtitle="Daftar perangkat dari inventory/router.yaml"
      />

      {loading && <p className="text-white/40 text-sm">Memuat...</p>}
      {error && (
        <div className="text-sm px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/20 text-red-300">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {devices.map((d) => (
          <div
            key={d.name}
            className="bg-card border border-border rounded-xl2 p-5"
          >
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-semibold text-white">{d.name}</h3>
              <span className="text-[10px] uppercase tracking-wide bg-emerald-500/10 text-emerald-300 px-2 py-1 rounded-full">
                inventory
              </span>
            </div>
            <dl className="text-sm space-y-1 text-white/60">
              <div className="flex justify-between">
                <dt>Host</dt>
                <dd className="text-white/90">{d.host}</dd>
              </div>
              <div className="flex justify-between">
                <dt>Port</dt>
                <dd className="text-white/90">{d.port}</dd>
              </div>
              <div className="flex justify-between">
                <dt>Username</dt>
                <dd className="text-white/90">{d.username}</dd>
              </div>
            </dl>
          </div>
        ))}

        {!loading && devices.length === 0 && !error && (
          <p className="text-white/40 text-sm">
            Belum ada device di inventory/router.yaml.
          </p>
        )}
      </div>
    </div>
  );
}
