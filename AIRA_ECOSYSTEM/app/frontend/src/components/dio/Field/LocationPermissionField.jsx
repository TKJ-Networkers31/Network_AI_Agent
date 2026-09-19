import { useState } from "react";

// Kode error navigator.geolocation: 1=PERMISSION_DENIED, 2=POSITION_UNAVAILABLE, 3=TIMEOUT
const GEO_ERROR_MESSAGES = {
  1: "Izin lokasi ditolak oleh browser.",
  2: "Posisi tidak tersedia saat ini.",
  3: "Waktu mengambil lokasi habis, coba lagi.",
};

/**
 * LocationPermissionField — satu-satunya field yang mengurus alur izin
 * GPS browser SENDIRI (tidak lewat ActionBar generik). Begitu browser
 * merespons, langsung memanggil onAction("grant_location"/"deny_location",
 * extraValues) - extraValues berisi koordinat mentah dari
 * navigator.geolocation, dikirim apa adanya ke backend untuk divalidasi
 * (frontend TIDAK memvalidasi/menerjemahkan koordinat - itu tanggung
 * jawab backend, sesuai aturan "business logic tidak boleh di app/").
 */
export default function LocationPermissionField({ field, onAction }) {
  const [status, setStatus] = useState("idle"); // idle | loading | error
  const [errorMsg, setErrorMsg] = useState("");

  function handleAllow() {
    if (typeof navigator === "undefined" || !("geolocation" in navigator)) {
      setStatus("error");
      setErrorMsg("Browser ini tidak mendukung geolokasi.");
      return;
    }

    setStatus("loading");
    setErrorMsg("");

    navigator.geolocation.getCurrentPosition(
      (position) => {
        const { latitude, longitude, accuracy } = position.coords;
        setStatus("idle");
        onAction?.("grant_location", { latitude, longitude, accuracy });
      },
      (err) => {
        setStatus("error");
        setErrorMsg(GEO_ERROR_MESSAGES[err.code] || "Gagal mengambil lokasi.");
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
    );
  }

  function handleDeny() {
    onAction?.("deny_location", {});
  }

  return (
    <div className="space-y-2.5">
      {field.helper_text && (
        <p className="text-xs text-white/60 leading-relaxed">{field.helper_text}</p>
      )}

      {status === "error" && (
        <p className="text-[11px] text-[#EF4444]">{errorMsg}</p>
      )}

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={handleAllow}
          disabled={status === "loading"}
          className="text-sm font-medium px-4 py-2 rounded-2xl bg-[#2563EB] hover:bg-[#2563EB]/90 text-white transition disabled:opacity-50"
        >
          {status === "loading" ? "Meminta izin..." : "Izinkan Lokasi"}
        </button>
        <button
          type="button"
          onClick={handleDeny}
          disabled={status === "loading"}
          className="text-sm font-medium px-4 py-2 rounded-2xl bg-transparent hover:bg-white/5 text-white/60 hover:text-white transition disabled:opacity-50"
        >
          Lanjut tanpa lokasi
        </button>
      </div>
    </div>
  );
}