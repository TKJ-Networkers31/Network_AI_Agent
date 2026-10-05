// Peta Leaflet dari blok ```map ... ``` di jawaban AIRA.
// Bentuk JSON: { origin?, places?: [{name,lat,lon,km,url}], destination?, route?: [[lat,lon],...] }
// Isi popup dibuat lewat DOM (bukan string HTML) supaya aman dari XSS.

import { useEffect, useMemo, useRef } from "react";
import L, { OSM_TILES, OSM_ATTRIBUTION, DEFAULT_CENTER } from "../utils/leaflet.js";

const isNum = (v) => typeof v === "number" && Number.isFinite(v);

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

  const data = useMemo(() => {
    try {
      const parsed = JSON.parse(code);
      return parsed && typeof parsed === "object" ? parsed : null;
    } catch {
      return null;
    }
  }, [code]);

  useEffect(() => {
    if (!data || !hostRef.current) return undefined;

    const map = L.map(hostRef.current, { scrollWheelZoom: false });
    L.tileLayer(OSM_TILES, { maxZoom: 19, attribution: OSM_ATTRIBUTION }).addTo(map);

    const points = [];

    if (isNum(data.origin?.lat) && isNum(data.origin?.lon)) {
      const latlng = [data.origin.lat, data.origin.lon];
      const accuracy = data.origin.accuracy;

      L.circleMarker(latlng, { radius: 8, color: "#F472B6", fillColor: "#F472B6", fillOpacity: 0.9 })
        .addTo(map)
        .bindPopup(buildPopup("Lokasimu", [isNum(accuracy) ? `Akurasi ±${Math.round(accuracy)} m` : null]));

      if (isNum(accuracy) && accuracy < 5000) {
        L.circle(latlng, { radius: accuracy, color: "#F472B6", weight: 1, fillOpacity: 0.08 }).addTo(map);
      }

      points.push(latlng);
    }

    (Array.isArray(data.places) ? data.places : []).forEach((place) => {
      if (!isNum(place?.lat) || !isNum(place?.lon)) return;

      L.marker([place.lat, place.lon])
        .addTo(map)
        .bindPopup(buildPopup(place.name || "Tempat", [isNum(place.km) ? `${place.km} km dari kamu` : null], place.url));

      points.push([place.lat, place.lon]);
    });

    if (isNum(data.destination?.lat) && isNum(data.destination?.lon)) {
      const latlng = [data.destination.lat, data.destination.lon];
      L.marker(latlng).addTo(map).bindPopup(buildPopup("Tujuan"));
      points.push(latlng);
    }

    if (Array.isArray(data.route) && data.route.length > 1) {
      const line = data.route.filter((p) => Array.isArray(p) && isNum(p[0]) && isNum(p[1]));
      L.polyline(line, { color: "#60A5FA", weight: 5 }).addTo(map);
      points.push(...line);
    }

    if (points.length > 0) {
      map.fitBounds(L.latLngBounds(points), { padding: [24, 24], maxZoom: 17 });
    } else {
      map.setView(DEFAULT_CENTER, 12);
    }

    // Container baru dipasang: paksa Leaflet menghitung ulang ukuran.
    const timer = setTimeout(() => map.invalidateSize(), 0);

    return () => {
      clearTimeout(timer);
      map.remove();
    };
  }, [data]);

  if (!data) {
    return (
      <div className="my-3 rounded-xl2 border border-border px-3 py-2 text-xs text-amber-300/80">
        Data peta tidak valid.
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