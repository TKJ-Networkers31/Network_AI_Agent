// src/services/settingsApi.js
//
// Klien API untuk Global Settings Engine (Sprint 2.6, Worker 1). Dipisah
// dari api.js — sama seperti modelRouterApi.js dan services/location.js —
// supaya api.js tidak perlu disentuh sama sekali.

const BASE = "/api/settings";
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

export const settingsApi = {
  getAll: () => request(""),
  get: (key) => request(`/${enc(key)}`),
  update: (key, value) =>
    request(`/${enc(key)}`, { method: "PUT", body: JSON.stringify({ value }) }),
};
