// Peta Leaflet dari blok ```map ... ``` di jawaban AIRA.
// Bentuk JSON: { origin?, places?: [{name,lat,lon,km,url}], destination?, route?: [[lat,lon],...] }
// Parser toleran: kutip pintar, koma menggantung, teks di luar { }, alias latitude/longitude.
// Popup dibuat lewat DOM (bukan string HTML) supaya aman dari XSS.

import { useEffect, useMemo, useRef, useState } from "react";
import L, { OSM_TILES, OSM_ATTRIBUTION, DEFAULT_CENTER } from "../utils/leaflet.js";

const isNum = (v) => typeof v === "number" && Number.isFinite(v);

function parseMapJson(raw) {
  const attempts = [];
  const text = String(raw ?? "").trim();
  attempts.push(text);

  const first = text.indexOf("{");
  const last = text.lastIndexOf("}");
  const sliced = first !== -1 && last > first ? text.slice(first, last + 1) : text;

  attempts.push(
    sliced
      .replace(/[\u201C\u201D]/g, '"')
      .replace(/[\u2018\u2019]/g, "'")
      .replace(/,\s*([}\]])/g, "$1")
  );

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

function normalize(data) {
  if (!data) return null;

  const origin = toPoint(data.origin);
  const destination = toPoint(data.destination);
  const places = (Array.isArray(data.places) ? data.places : []).map(toPoint).filter(Boolean);
  const route = (Array.isArray(data.route) ? data.route : [])
    .map((p) => (Array.isArray(p) ? [Number(p[0]), Number(p[1])] : null))
    .filter((p) => p && isNum(p[0]) && isNum(p[1]));

  if (!origin && !destination && places.length === 0 && route.length < 2) return null;

  return { origin, destination, places, route };
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

export default function MapBlock({ code }) {
  const hostRef = useRef(null);
  const [showRaw, setShowRaw] = useState(false);

  const data = useMemo(() => normalize(parseMapJson(code)), [code]);

  useEffect(() => {
    if (!data || !hostRef.current) return undefined;

    let map;
    let timer;

    try {
      map = L.map(hostRef.current, { scrollWheelZoom: false });
      L.tileLayer(OSM_TILES, { maxZoom: 19, attribution: OSM_ATTRIBUTION }).addTo(map);

      const points = [];

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

      data.places.forEach((place) => {
        const km = Number(place.km);

        L.marker([place.lat, place.lon])
          .addTo(map)
          .bindPopup(buildPopup(place.name || "Tempat", [isNum(km) ? `${km} km dari kamu` : null], place.url));

        points.push([place.lat, place.lon]);
      });

      if (data.destination) {
        const latlng = [data.destination.lat, data.destination.lon];
        L.marker(latlng).addTo(map).bindPopup(buildPopup("Tujuan"));
        points.push(latlng);
      }

      if (data.route.length > 1) {
        L.polyline(data.route, { color: "#60A5FA", weight: 5 }).addTo(map);
        points.push(...data.route);
      }

      if (points.length > 0) {
        map.fitBounds(L.latLngBounds(points), { padding: [24, 24], maxZoom: 17 });
      } else {
        map.setView(DEFAULT_CENTER, 12);
      }

      timer = setTimeout(() => map && map.invalidateSize(), 0);
    } catch (err) {
      console.error("MapBlock gagal merender peta:", err);
    }

    return () => {
      clearTimeout(timer);
      if (map) map.remove();
    };
  }, [data]);

  if (!data) {
    return (
      <div className="my-3 rounded-xl2 border border-border overflow-hidden">
        <div className="flex items-center justify-between px-3 py-1.5 bg-white/5 border-b border-border">
          <span className="text-xs text-amber-300/80">
            Data peta tidak bisa dibaca (JSON rusak atau terpotong).
          </span>
          <button
            type="button"
            onClick={() => setShowRaw((v) => !v)}
            className="text-[11px] text-white/40 hover:text-white"
          >
            {showRaw ? "Sembunyikan" : "Lihat data"}
          </button>
        </div>
        {showRaw && (
          <pre className="overflow-x-auto p-3 text-[12px] bg-black/30 text-white/70">{code}</pre>
        )}
      </div>
    );
  }

  return (
    <div className="my-3 rounded-xl2 border border-border overflow-hidden">
      <div className="px-3 py-1 bg-white/5 border-b border-border text-[10px] uppercase tracking-wide text-white/40">
        peta
      </div>
      {/* isolate: z-index internal Leaflet (400-1000) tidak boleh menimpa TopBar/Sidebar */}
      <div ref={hostRef} className="isolate w-full" style={{ height: 288 }} />
    </div>
  );
}