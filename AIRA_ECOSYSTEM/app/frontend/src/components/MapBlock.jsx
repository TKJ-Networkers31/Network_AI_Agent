// Peta Leaflet interaktif dari blok ```map ... ``` di jawaban AIRA.
// Payload: { origin?, destination?{name}, via?, places?[], routes?[{via,km,min,pts,alt,blocked}],
//            route? (alias lama), steps?[{t,m}], avoid?{street,ok} }
// Popup dibuat lewat DOM (bukan string HTML) supaya aman dari XSS.

import { useEffect, useMemo, useRef, useState } from "react";
import L, { OSM_TILES, OSM_ATTRIBUTION, DEFAULT_CENTER } from "../utils/leaflet.js";
import { copyText } from "../utils/clipboard.js";

const isNum = (v) => typeof v === "number" && Number.isFinite(v);

const BASE_LAYERS = {
  "OpenStreetMap": { url: OSM_TILES, attribution: OSM_ATTRIBUTION, maxZoom: 19 },
  "Terang": {
    url: "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
    attribution: `${OSM_ATTRIBUTION} &copy; CARTO`, maxZoom: 20,
  },
  "Gelap": {
    url: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
    attribution: `${OSM_ATTRIBUTION} &copy; CARTO`, maxZoom: 20,
  },
  "Topografi": {
    url: "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
    attribution: `${OSM_ATTRIBUTION} &copy; OpenTopoMap`, maxZoom: 17,
  },
};

function parseMapJson(raw) {
  const text = String(raw ?? "").trim();
  const first = text.indexOf("{");
  const last = text.lastIndexOf("}");
  const sliced = first !== -1 && last > first ? text.slice(first, last + 1) : text;

  const attempts = [
    text,
    sliced.replace(/[\u201C\u201D]/g, '"').replace(/[\u2018\u2019]/g, "'").replace(/,\s*([}\]])/g, "$1"),
  ];

  for (const candidate of attempts) {
    try {
      const parsed = JSON.parse(candidate);
      if (parsed && typeof parsed === "object") return parsed;
    } catch {
      // coba kandidat berikutnya
    }
  }
  return null;
}

function toPoint(p) {
  if (!p || typeof p !== "object") return null;
  const lat = Number(p.lat ?? p.latitude);
  const lon = Number(p.lon ?? p.lng ?? p.longitude);
  if (!isNum(lat) || !isNum(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) return null;
  return { ...p, lat, lon };
}

function toLine(raw) {
  return (Array.isArray(raw) ? raw : [])
    .map((p) => (Array.isArray(p) ? [Number(p[0]), Number(p[1])] : null))
    .filter((p) => p && isNum(p[0]) && isNum(p[1]));
}

function normalize(data) {
  if (!data) return null;

  const origin = toPoint(data.origin);
  const destination = toPoint(data.destination);
  const via = toPoint(data.via);
  const places = (Array.isArray(data.places) ? data.places : []).map(toPoint).filter(Boolean);

  let routes = (Array.isArray(data.routes) ? data.routes : [])
    .map((r, i) => ({
      via: typeof r.via === "string" ? r.via : "",
      km: Number(r.km),
      min: Number(r.min),
      alt: Boolean(r.alt) || i > 0,
      blocked: Boolean(r.blocked),
      pts: toLine(r.pts),
    }))
    .filter((r) => r.pts.length > 1);

  if (routes.length === 0) {
    const legacy = toLine(data.route);
    if (legacy.length > 1) routes = [{ via: "", km: NaN, min: NaN, alt: false, blocked: false, pts: legacy }];
  }

  const steps = (Array.isArray(data.steps) ? data.steps : [])
    .filter((s) => s && typeof s.t === "string")
    .map((s) => ({ t: s.t, m: Number(s.m) }));

  const avoid = data.avoid && typeof data.avoid.street === "string" ? data.avoid : null;

  if (!origin && !destination && places.length === 0 && routes.length === 0) return null;

  return { origin, destination, via, places, routes, steps, avoid };
}

function buildPopup(title, lines = [], url) {
  const root = document.createElement("div");

  const strong = document.createElement("strong");
  strong.textContent = title;
  root.appendChild(strong);

  lines.filter(Boolean).forEach((text) => {
    const row = document.createElement("div");
    row.textContent = text;
    root.appendChild(row);
  });

  if (url && /^https?:\/\//.test(url)) {
    const link = document.createElement("a");
    link.href = url;
    link.target = "_blank";
    link.rel = "noreferrer";
    link.textContent = "Buka di OpenStreetMap";
    root.appendChild(link);
  }

  return root;
}

function routeStyle(active, route) {
  if (route.blocked) return { color: "#F87171", weight: active ? 6 : 4, opacity: active ? 0.9 : 0.55, dashArray: "2 10" };
  if (active) return { color: "#60A5FA", weight: 7, opacity: 0.95, dashArray: null };
  return { color: route.alt ? "#94A3B8" : "#60A5FA", weight: 5, opacity: 0.6, dashArray: "9 9" };
}

function formatRoute(r) {
  const parts = [];
  if (isNum(r.km)) parts.push(`${r.km} km`);
  if (isNum(r.min)) parts.push(`${r.min} mnt`);
  return parts.join(" · ");
}

const BTN =
  "px-2 py-1 rounded-pill text-[11px] text-white/50 hover:text-white hover:bg-white/10 transition";

export default function MapBlock({ code }) {
  const hostRef = useRef(null);
  const mapRef = useRef(null);
  const layersRef = useRef({ routes: [], markers: [], all: null });

  const [selected, setSelected] = useState(0);
  const [full, setFull] = useState(false);
  const [showSteps, setShowSteps] = useState(false);
  const [showRaw, setShowRaw] = useState(false);
  const [copied, setCopied] = useState("");

  const data = useMemo(() => normalize(parseMapJson(code)), [code]);

  // ------------------------------------------------ bangun peta (sekali per data)
  useEffect(() => {
    if (!data || !hostRef.current) return undefined;

    let map;
    let timer;
    let pin = null;

    try {
      map = L.map(hostRef.current, { scrollWheelZoom: false });
      mapRef.current = map;

      const bases = Object.fromEntries(
        Object.entries(BASE_LAYERS).map(([name, cfg]) => [
          name,
          L.tileLayer(cfg.url, { maxZoom: cfg.maxZoom, attribution: cfg.attribution, subdomains: "abc" }),
        ])
      );
      bases["OpenStreetMap"].addTo(map);
      L.control.layers(bases, null, { position: "topright", collapsed: true }).addTo(map);
      L.control.scale({ imperial: false }).addTo(map);

      // scroll-zoom aktif setelah peta diklik, mati lagi saat kursor keluar
      map.on("focus", () => map.scrollWheelZoom.enable());
      map.on("blur", () => map.scrollWheelZoom.disable());
      map.getContainer().addEventListener("mouseleave", () => map.scrollWheelZoom.disable());

      const points = [];
      layersRef.current = { routes: [], markers: [], all: null };

      // ---- rute
      data.routes.forEach((r, i) => {
        const line = L.polyline(r.pts, { ...routeStyle(i === 0, r), bubblingMouseEvents: false })
          .addTo(map)
          .on("click", () => setSelected(i));
        line.bindTooltip(`${r.via || "Rute"} · ${formatRoute(r)}`, { sticky: true });
        layersRef.current.routes.push(line);
        points.push(...r.pts);
      });

      // ---- asal
      if (data.origin) {
        const latlng = [data.origin.lat, data.origin.lon];
        const accuracy = Number(data.origin.accuracy);

        L.circleMarker(latlng, { radius: 8, color: "#F472B6", fillColor: "#F472B6", fillOpacity: 0.9 })
          .addTo(map)
          .bindPopup(buildPopup("Lokasimu", [isNum(accuracy) ? `Akurasi ±${Math.round(accuracy)} m` : null]));

        if (isNum(accuracy) && accuracy > 0 && accuracy < 5000) {
          L.circle(latlng, { radius: accuracy, color: "#F472B6", weight: 1, fillOpacity: 0.08 }).addTo(map);
        }
        points.push(latlng);
      }

      // ---- tempat
      data.places.forEach((place) => {
        const km = Number(place.km);
        const marker = L.marker([place.lat, place.lon])
          .addTo(map)
          .bindPopup(buildPopup(place.name || "Tempat", [isNum(km) ? `${km} km dari kamu` : null], place.url));
        layersRef.current.markers.push(marker);
        points.push([place.lat, place.lon]);
      });

      // ---- titik perantara & tujuan
      if (data.via) {
        L.circleMarker([data.via.lat, data.via.lon], {
          radius: 7, color: "#FBBF24", fillColor: "#FBBF24", fillOpacity: 0.9,
        }).addTo(map).bindPopup(buildPopup("Titik perantara"));
        points.push([data.via.lat, data.via.lon]);
      }

      if (data.destination) {
        const latlng = [data.destination.lat, data.destination.lon];
        L.marker(latlng).addTo(map).bindPopup(buildPopup(data.destination.name || "Tujuan"));
        points.push(latlng);
      }

      // ---- klik peta -> pin + aksi
      map.on("click", (event) => {
        const { lat, lng } = event.latlng;
        const text = `${lat.toFixed(5)}, ${lng.toFixed(5)}`;

        if (pin) pin.remove();
        pin = L.circleMarker(event.latlng, {
          radius: 6, color: "#A78BFA", fillColor: "#A78BFA", fillOpacity: 0.9,
        }).addTo(map);

        const root = document.createElement("div");
        const title = document.createElement("strong");
        title.textContent = "Titik dipilih";
        root.appendChild(title);

        const coord = document.createElement("div");
        coord.textContent = text;
        root.appendChild(coord);

        const actions = document.createElement("div");
        actions.style.cssText = "display:flex;gap:8px;margin-top:6px;flex-wrap:wrap;";

        const copyBtn = document.createElement("button");
        copyBtn.type = "button";
        copyBtn.textContent = "Salin";
        copyBtn.style.cssText = "cursor:pointer;text-decoration:underline;";
        copyBtn.onclick = async () => {
          await copyText(text);
          copyBtn.textContent = "Tersalin ✓";
        };
        actions.appendChild(copyBtn);

        if (data.destination) {
          const askBtn = document.createElement("button");
          askBtn.type = "button";
          askBtn.textContent = "Rute lewat sini";
          askBtn.style.cssText = "cursor:pointer;text-decoration:underline;";
          askBtn.onclick = () => {
            const name = data.destination.name || "tujuan semula";
            window.dispatchEvent(
              new CustomEvent("aira:ask", {
                detail: { text: `Cari rute dari lokasiku ke ${name} yang lewat titik koordinat ${text}` },
              })
            );
            map.closePopup();
          };
          actions.appendChild(askBtn);
        }

        root.appendChild(actions);
        pin.bindPopup(root).openPopup();
      });

      layersRef.current.all = points.length > 0 ? L.latLngBounds(points) : null;

      if (layersRef.current.all) map.fitBounds(layersRef.current.all, { padding: [24, 24], maxZoom: 17 });
      else map.setView(DEFAULT_CENTER, 12);

      timer = setTimeout(() => map && map.invalidateSize(), 0);
    } catch (err) {
      console.error("MapBlock gagal merender peta:", err);
    }

    return () => {
      clearTimeout(timer);
      if (map) map.remove();
      mapRef.current = null;
    };
  }, [data]);

  // ------------------------------------------------ rute terpilih -> gaya & fokus
  useEffect(() => {
    const { routes } = layersRef.current;
    if (!data || routes.length === 0) return;

    routes.forEach((line, i) => {
      line.setStyle(routeStyle(i === selected, data.routes[i]));
      if (i === selected) line.bringToFront();
    });

    const map = mapRef.current;
    const target = routes[selected];
    if (map && target && selected > 0) map.fitBounds(target.getBounds(), { padding: [32, 32], maxZoom: 17 });
  }, [selected, data]);

  // ------------------------------------------------ layar penuh
  useEffect(() => {
    const timer = setTimeout(() => mapRef.current && mapRef.current.invalidateSize(), 60);

    function onKey(e) {
      if (e.key === "Escape") setFull(false);
    }

    if (full) window.addEventListener("keydown", onKey);
    return () => {
      clearTimeout(timer);
      window.removeEventListener("keydown", onKey);
    };
  }, [full]);

  function recenter() {
    const map = mapRef.current;
    const bounds = layersRef.current.all;
    if (map && bounds) map.fitBounds(bounds, { padding: [24, 24], maxZoom: 17 });
  }

  function focusPlace(index) {
    const marker = layersRef.current.markers[index];
    const map = mapRef.current;
    if (!marker || !map) return;
    map.flyTo(marker.getLatLng(), Math.max(map.getZoom(), 16), { duration: 0.6 });
    marker.openPopup();
  }

  async function copyDest() {
    if (!data?.destination) return;
    const ok = await copyText(`${data.destination.lat.toFixed(5)}, ${data.destination.lon.toFixed(5)}`);
    if (ok) {
      setCopied("dest");
      setTimeout(() => setCopied(""), 1500);
    }
  }

  if (!data) {
    return (
      <div className="my-3 rounded-xl2 border border-border overflow-hidden">
        <div className="flex items-center justify-between px-3 py-1.5 bg-white/5 border-b border-border">
          <span className="text-xs text-amber-300/80">Data peta tidak bisa dibaca (JSON rusak atau terpotong).</span>
          <button type="button" onClick={() => setShowRaw((v) => !v)} className="text-[11px] text-white/40 hover:text-white">
            {showRaw ? "Sembunyikan" : "Lihat data"}
          </button>
        </div>
        {showRaw && <pre className="overflow-x-auto p-3 text-[12px] bg-black/30 text-white/70">{code}</pre>}
      </div>
    );
  }

  const active = data.routes[selected];
  const wrapperClass = full
    ? "fixed inset-0 z-[110] flex flex-col bg-app"
    : "my-3 rounded-xl2 border border-border overflow-hidden";

  return (
    <div className={wrapperClass}>
      <div className="flex items-center justify-between gap-2 pl-3 pr-1.5 py-1 bg-white/5 border-b border-border">
        <span className="text-[10px] uppercase tracking-wide text-white/40 truncate">
          peta{active ? ` · ${active.via || "rute"} ${formatRoute(active)}` : ""}
        </span>
        <div className="flex items-center gap-0.5 shrink-0">
          {data.steps.length > 0 && (
            <button type="button" onClick={() => setShowSteps((v) => !v)} className={BTN}>
              {showSteps ? "Sembunyikan langkah" : "Langkah"}
            </button>
          )}
          {data.destination && (
            <button type="button" onClick={copyDest} className={BTN}>
              {copied === "dest" ? "Tersalin ✓" : "Salin tujuan"}
            </button>
          )}
          <button type="button" onClick={recenter} className={BTN}>Pusatkan</button>
          <button type="button" onClick={() => setFull((v) => !v)} className={BTN}>
            {full ? "Tutup" : "Layar penuh"}
          </button>
        </div>
      </div>

      {data.avoid && (
        <div
          className={`px-3 py-1.5 text-[11px] border-b border-border ${
            data.avoid.ok ? "text-emerald-300/90 bg-emerald-500/5" : "text-amber-300/90 bg-amber-500/5"
          }`}
        >
          {data.avoid.ok
            ? `Menghindari "${data.avoid.street}". Data OSM tidak tahu status perbaikan jalan, pastikan di lapangan.`
            : `Semua rute otomatis tetap melewati "${data.avoid.street}". Sebutkan jalan pengganti untuk rute lewat titik perantara.`}
        </div>
      )}

      {/* isolate: z-index internal Leaflet (400-1000) tidak boleh menimpa TopBar/Sidebar */}
      <div
        ref={hostRef}
        tabIndex={0}
        className="isolate w-full outline-none"
        style={{ height: full ? "100%" : 320, flex: full ? 1 : "none" }}
      />

      {data.routes.length > 1 && (
        <div className="flex flex-wrap gap-1.5 px-3 py-2 border-t border-border bg-white/[0.03]">
          {data.routes.map((r, i) => (
            <button
              key={i}
              type="button"
              onClick={() => setSelected(i)}
              className={`text-[11px] px-2.5 py-1 rounded-pill border transition ${
                i === selected
                  ? "border-sky-400/60 bg-sky-400/10 text-sky-200"
                  : "border-border text-white/50 hover:text-white"
              } ${r.blocked ? "line-through decoration-red-400/70" : ""}`}
              title={r.blocked ? "Rute ini melewati jalan yang dihindari" : undefined}
            >
              {i === 0 ? "Utama" : `Alternatif ${i}`}
              {r.via ? ` · ${r.via}` : ""} {formatRoute(r) && `· ${formatRoute(r)}`}
            </button>
          ))}
        </div>
      )}

      {showSteps && data.steps.length > 0 && selected === 0 && (
        <ol className="px-5 py-2 border-t border-border text-xs text-white/70 list-decimal space-y-0.5 max-h-40 overflow-y-auto">
          {data.steps.map((s, i) => (
            <li key={i}>
              {s.t}
              {isNum(s.m) && s.m > 0 ? <span className="text-white/30"> ({s.m} m)</span> : null}
            </li>
          ))}
        </ol>
      )}

      {data.places.length > 0 && (
        <ul className="border-t border-border divide-y divide-border max-h-44 overflow-y-auto">
          {data.places.map((p, i) => (
            <li key={`${p.name}-${i}`}>
              <button
                type="button"
                onClick={() => focusPlace(i)}
                className="w-full flex items-center justify-between gap-2 px-3 py-1.5 text-left text-xs text-white/70 hover:bg-white/5"
              >
                <span className="truncate">{i + 1}. {p.name || "Tempat"}</span>
                {isNum(Number(p.km)) && <span className="shrink-0 text-white/30">{p.km} km</span>}
              </button>
            </li>
          ))}
        </ul>
      )}

      {!full && (
        <p className="px-3 py-1 text-[10px] text-white/30 border-t border-border">
          Klik peta untuk menaruh pin · klik garis rute untuk memilihnya · pakai ikon lapisan untuk ganti gaya peta.
        </p>
      )}
    </div>
  );
}