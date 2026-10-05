// Pin lokasi manual di peta Leaflet. Cadangan paling andal untuk laptop
// (tanpa GPS): klik peta / geser pin, lalu simpan sebagai lokasi akses sesi.
// Memakai endpoint yang sudah ada (POST /api/location), tanpa perubahan backend.

import { useEffect, useRef, useState } from "react";
import L, { OSM_TILES, OSM_ATTRIBUTION, DEFAULT_CENTER } from "../../utils/leaflet.js";
import { locationApi } from "../../services/location.js";
import { useSessionsContext } from "../../context/SessionsContext.jsx";
import { useToast } from "../Toast.jsx";

const PIN_ACCURACY_METERS = 30;

export default function LocationPinPicker({ initial, onSaved }) {
  const hostRef = useRef(null);
  const markerRef = useRef(null);
  const [point, setPoint] = useState(null);
  const [saving, setSaving] = useState(false);

  const { activeId } = useSessionsContext();
  const { notify } = useToast();

  useEffect(() => {
    const hasInitial = initial?.latitude != null && initial?.longitude != null;
    const center = hasInitial ? [initial.latitude, initial.longitude] : DEFAULT_CENTER;

    const map = L.map(hostRef.current).setView(center, hasInitial ? 15 : 12);
    L.tileLayer(OSM_TILES, { maxZoom: 19, attribution: OSM_ATTRIBUTION }).addTo(map);

    map.on("click", (event) => {
      if (markerRef.current) {
        markerRef.current.setLatLng(event.latlng);
      } else {
        markerRef.current = L.marker(event.latlng, { draggable: true })
          .addTo(map)
          .on("dragend", (e) => {
            const p = e.target.getLatLng();
            setPoint({ lat: p.lat, lon: p.lng });
          });
      }

      setPoint({ lat: event.latlng.lat, lon: event.latlng.lng });
    });

    const timer = setTimeout(() => map.invalidateSize(), 0);

    return () => {
      clearTimeout(timer);
      map.remove();
      markerRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function save() {
    if (!point || !activeId) return;

    setSaving(true);

    try {
      await locationApi.reportAccess({
        session_id: activeId,
        latitude: point.lat,
        longitude: point.lon,
        accuracy: PIN_ACCURACY_METERS,
      });
      notify({ type: "success", message: "Lokasi diatur dari peta.", duration: 2500 });
      onSaved?.();
    } catch (err) {
      notify({ type: "error", message: err.message });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-2">
      <div ref={hostRef} className="isolate w-full rounded-lg overflow-hidden" style={{ height: 256 }} />

      <p className="text-[11px] text-white/40">
        {point
          ? `Titik terpilih: ${point.lat.toFixed(5)}, ${point.lon.toFixed(5)}`
          : "Klik peta untuk menaruh pin (bisa digeser), lalu simpan."}
      </p>

      <button
        type="button"
        onClick={save}
        disabled={!point || !activeId || saving}
        className="text-xs px-3 py-1.5 rounded-lg bg-accent-gradient text-white font-semibold disabled:opacity-40 disabled:cursor-not-allowed"
      >
        {saving ? "Menyimpan..." : "Pakai titik ini"}
      </button>

      {!activeId && (
        <p className="text-[11px] text-amber-300/80">Buka atau mulai sebuah chat dulu supaya lokasi bisa disimpan.</p>
      )}
    </div>
  );
}