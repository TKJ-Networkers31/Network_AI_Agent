// src/services/location.js
//
// Klien API lokasi + helper GPS browser. Dipisah dari api.js (sama seperti
// modelRouterApi.js) supaya api.js tidak disentuh.
//
// CATATAN: navigator.geolocation HANYA jalan di secure context (https atau
// localhost). Kalau AIRA dibuka lewat http://192.168.x.x, GPS tidak tersedia -
// server tetap menebak lokasi akses dari jaringan/IP klien.

const BASE = "/api/location";
const GPS_PREF_KEY = "aira_gps_enabled";
const enc = encodeURIComponent;

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : `Request gagal (${res.status})`);
  }

  return res.json();
}

export const locationApi = {
  snapshot: (sessionId) => request(`?session_id=${enc(sessionId)}`),
  reportAccess: (payload) => request("", { method: "POST", body: JSON.stringify(payload) }),
  clearGps: (sessionId) => request(`/access?session_id=${enc(sessionId)}`, { method: "DELETE" }),
  host: () => request("/host"),
  setHost: (payload) => request("/host", { method: "PUT", body: JSON.stringify(payload) }),
  detectHost: () => request("/host/detect", { method: "POST" }),
};

export function canUseGps() {
  return (
    typeof navigator !== "undefined" &&
    "geolocation" in navigator &&
    typeof window !== "undefined" &&
    window.isSecureContext
  );
}

export function getGpsEnabled() {
  try {
    return localStorage.getItem(GPS_PREF_KEY) === "1";
  } catch {
    return false;
  }
}

export function setGpsEnabled(enabled) {
  try {
    localStorage.setItem(GPS_PREF_KEY, enabled ? "1" : "0");
  } catch {
    // abaikan
  }
}

const GPS_ERRORS = {
  1: "Izin lokasi ditolak. Izinkan lokasi untuk situs ini di pengaturan browser.",
  2: "Posisi tidak tersedia saat ini.",
  3: "Waktu mengambil posisi habis. Coba lagi.",
};

export function getBrowserPosition({ maxAgeMs = 5 * 60 * 1000, timeoutMs = 10000 } = {}) {
  return new Promise((resolve, reject) => {
    if (!canUseGps()) {
      reject(new Error("GPS browser butuh https:// atau localhost."));
      return;
    }

    navigator.geolocation.getCurrentPosition(
      ({ coords, timestamp }) =>
        resolve({
          latitude: coords.latitude,
          longitude: coords.longitude,
          accuracy: coords.accuracy,
          altitude: coords.altitude,
          heading: coords.heading,
          speed: coords.speed,
          timestamp: timestamp / 1000,
        }),
      (err) => reject(new Error(GPS_ERRORS[err.code] || "Gagal mengambil lokasi.")),
      { enableHighAccuracy: true, timeout: timeoutMs, maximumAge: maxAgeMs }
    );
  });
}