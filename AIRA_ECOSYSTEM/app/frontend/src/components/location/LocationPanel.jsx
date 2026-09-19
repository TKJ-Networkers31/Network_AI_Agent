import { useCallback, useEffect, useState } from "react";
import { MapPin, RefreshCw, Server, Smartphone } from "lucide-react";
import { useSessionsContext } from "../../context/SessionsContext.jsx";
import { useToast } from "../Toast.jsx";
import {
  locationApi,
  canUseGps,
  getGpsEnabled,
  setGpsEnabled,
  getBrowserPosition,
} from "../../services/location.js";

const SOURCE_LABEL = {
  manual: "Manual",
  browser: "GPS browser",
  ip: "Perkiraan IP",
  network: "Jaringan lokal",
};

function relationText(rel) {
  if (!rel) return "";
  if (rel.kind === "same_machine") return "Kamu membuka AIRA langsung dari mesin hosting.";
  if (rel.kind === "same_network") return "Kamu berada di jaringan yang sama dengan server hosting.";
  if (rel.distance_km != null) return `Jarak kamu ke server hosting sekitar ${rel.distance_km} km.`;
  return "";
}

function LocationCard({ icon: Icon, title, hint, location, children }) {
  const hasCoords = location && location.latitude != null && location.longitude != null;

  return (
    <div className="bg-card border border-border rounded-xl2 p-5 flex flex-col gap-3">
      <div className="flex items-start gap-3">
        <span className="shrink-0 w-9 h-9 rounded-control bg-white/5 border border-border flex items-center justify-center text-sakura">
          <Icon size={18} strokeWidth={1.9} />
        </span>
        <div className="min-w-0">
          <h3 className="font-semibold text-white leading-tight">{title}</h3>
          <p className="text-xs text-white/40 mt-0.5">{hint}</p>
        </div>
      </div>

      {location ? (
        <div className="space-y-1.5">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm text-white">{location.name}</span>
            <span className="text-[10px] uppercase tracking-wide bg-accent/10 text-accent-light px-2 py-0.5 rounded-full">
              {SOURCE_LABEL[location.source] || location.source}
            </span>
          </div>

          <dl className="text-xs text-white/50 space-y-0.5">
            {hasCoords && (
              <div className="flex justify-between gap-2">
                <dt>Koordinat</dt>
                <dd className="font-mono text-white/70">
                  {location.latitude.toFixed(4)}, {location.longitude.toFixed(4)}
                </dd>
              </div>
            )}
            {location.accuracy != null && (
              <div className="flex justify-between gap-2">
                <dt>Akurasi</dt>
                <dd className="text-white/70">±{Math.round(location.accuracy)} m</dd>
              </div>
            )}
            {location.timezone && (
              <div className="flex justify-between gap-2">
                <dt>Zona waktu</dt>
                <dd className="text-white/70">{location.timezone}</dd>
              </div>
            )}
            {location.ip && (
              <div className="flex justify-between gap-2">
                <dt>IP klien</dt>
                <dd className="font-mono text-white/70">{location.ip}</dd>
              </div>
            )}
          </dl>
        </div>
      ) : (
        <p className="text-sm text-white/40">Belum diketahui.</p>
      )}

      {children}
    </div>
  );
}

const BTN =
  "text-xs px-3 py-1.5 rounded-lg bg-white/5 text-white/70 hover:text-white hover:bg-white/10 transition disabled:opacity-40 disabled:cursor-not-allowed";

export default function LocationPanel() {
  const { activeId } = useSessionsContext();
  const { notify } = useToast();

  const [snap, setSnap] = useState(null);
  const [busy, setBusy] = useState(null);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({ query: "", latitude: "", longitude: "" });
  const [gpsOn, setGpsOn] = useState(getGpsEnabled);

  const gpsPossible = canUseGps();

  const load = useCallback(async () => {
    try {
      if (activeId) {
        setSnap(await locationApi.snapshot(activeId));
      } else {
        const res = await locationApi.host();
        setSnap({ host: res.host, access: null, relation: null });
      }
    } catch (err) {
      notify({ type: "error", message: err.message });
    }
  }, [activeId, notify]);

  useEffect(() => {
    load();
  }, [load]);

  async function run(key, action, successMessage) {
    setBusy(key);
    try {
      await action();
      if (successMessage) notify({ type: "success", message: successMessage, duration: 2500 });
      await load();
    } catch (err) {
      notify({ type: "error", message: err.message });
    } finally {
      setBusy(null);
    }
  }

  async function reportAccess(withGps) {
    const coords = withGps ? await getBrowserPosition({ maxAgeMs: 0 }) : {};
    await locationApi.reportAccess({ session_id: activeId, ...coords });
  }

  function enableGps() {
    if (!gpsPossible) {
      notify({
        type: "warning",
        message:
          "GPS browser hanya jalan di https:// atau localhost. Sekarang lokasi akses diperkirakan dari jaringan/IP.",
        duration: 6000,
      });
      return;
    }

    run(
      "gps",
      async () => {
        await reportAccess(true);
        setGpsEnabled(true);
        setGpsOn(true);
      },
      "GPS browser aktif."
    );
  }

  function disableGps() {
    run(
      "gps",
      async () => {
        setGpsEnabled(false);
        setGpsOn(false);
        await locationApi.clearGps(activeId);
      },
      "GPS dimatikan, kembali ke perkiraan jaringan."
    );
  }

  function saveHost(e) {
    e.preventDefault();

    const payload = {};
    if (form.query.trim()) payload.query = form.query.trim();
    if (form.latitude !== "" && form.longitude !== "") {
      payload.latitude = Number(form.latitude);
      payload.longitude = Number(form.longitude);
    }

    if (!payload.query && payload.latitude === undefined) {
      notify({ type: "warning", message: "Isi nama tempat atau koordinat." });
      return;
    }

    run(
      "host",
      async () => {
        await locationApi.setHost(payload);
        setEditing(false);
        setForm({ query: "", latitude: "", longitude: "" });
      },
      "Lokasi hosting disimpan."
    );
  }

  const host = snap?.host || null;
  const access = snap?.access || null;
  const canCopyAccess = access?.source === "browser" && access.latitude != null;

  return (
    <section className="space-y-3">
      <h3 className="font-semibold text-white px-1">Lokasi</h3>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <LocationCard
          icon={Server}
          title="Lokasi hosting"
          hint="Di mana server AIRA berjalan"
          location={host}
        >
          {host?.source === "ip" && (
            <p className="text-[11px] text-amber-300/80">
              Ini perkiraan dari IP publik dan bisa meleset kota. Kalau salah, isi manual.
            </p>
          )}

          <div className="flex flex-wrap gap-2">
            <button
              className={BTN}
              disabled={busy === "host"}
              onClick={() => run("host", () => locationApi.detectHost(), "Lokasi hosting dideteksi.")}
            >
              Deteksi otomatis
            </button>
            <button className={BTN} onClick={() => setEditing((v) => !v)}>
              {editing ? "Tutup" : "Edit manual"}
            </button>
            {canCopyAccess && (
              <button
                className={BTN}
                disabled={busy === "host"}
                onClick={() =>
                  run(
                    "host",
                    () =>
                      locationApi.setHost({
                        label: access.label || undefined,
                        latitude: access.latitude,
                        longitude: access.longitude,
                      }),
                    "Lokasi hosting diganti dengan lokasi akses."
                  )
                }
              >
                Pakai lokasi akses ini
              </button>
            )}
          </div>

          {editing && (
            <form onSubmit={saveHost} className="space-y-2 bg-white/5 rounded-lg p-3">
              <input
                value={form.query}
                onChange={(e) => setForm((f) => ({ ...f, query: e.target.value }))}
                placeholder="Nama tempat (mis. Bandung)"
                className="w-full bg-white/5 border border-border rounded-lg px-3 py-2 text-sm outline-none focus:border-accent"
              />
              <div className="grid grid-cols-2 gap-2">
                <input
                  value={form.latitude}
                  onChange={(e) => setForm((f) => ({ ...f, latitude: e.target.value }))}
                  placeholder="Latitude (opsional)"
                  className="bg-white/5 border border-border rounded-lg px-3 py-2 text-sm outline-none focus:border-accent"
                />
                <input
                  value={form.longitude}
                  onChange={(e) => setForm((f) => ({ ...f, longitude: e.target.value }))}
                  placeholder="Longitude (opsional)"
                  className="bg-white/5 border border-border rounded-lg px-3 py-2 text-sm outline-none focus:border-accent"
                />
              </div>
              <button
                type="submit"
                disabled={busy === "host"}
                className="bg-accent-gradient text-white text-sm font-semibold px-4 py-2 rounded-lg disabled:opacity-50"
              >
                {busy === "host" ? "Menyimpan..." : "Simpan"}
              </button>
            </form>
          )}
        </LocationCard>

        <LocationCard
          icon={Smartphone}
          title="Lokasi akses"
          hint="Di mana kamu membuka AIRA sekarang"
          location={access}
        >
          {!activeId && (
            <p className="text-[11px] text-white/40">Buka atau mulai sebuah chat dulu untuk melihat lokasi akses.</p>
          )}

          {relationText(snap?.relation) && (
            <p className="text-xs text-white/60 flex items-center gap-1.5">
              <MapPin size={13} strokeWidth={1.9} className="text-sakura shrink-0" />
              {relationText(snap.relation)}
            </p>
          )}

          {!gpsPossible && (
            <p className="text-[11px] text-white/40">
              GPS browser butuh https:// atau localhost. Lewat http://IP-LAN, lokasi akses diperkirakan dari
              jaringan/IP klien.
            </p>
          )}

          <div className="flex flex-wrap gap-2">
            {gpsOn ? (
              <button className={BTN} disabled={!activeId || busy === "gps"} onClick={disableGps}>
                Matikan GPS browser
              </button>
            ) : (
              <button className={BTN} disabled={!activeId || busy === "gps"} onClick={enableGps}>
                Pakai GPS browser
              </button>
            )}
            <button
              className={`${BTN} inline-flex items-center gap-1.5`}
              disabled={!activeId || busy === "refresh"}
              onClick={() => run("refresh", () => reportAccess(gpsOn && gpsPossible), "Lokasi akses diperbarui.")}
            >
              <RefreshCw size={12} strokeWidth={2} /> Perbarui
            </button>
          </div>
        </LocationCard>
      </div>
    </section>
  );
}