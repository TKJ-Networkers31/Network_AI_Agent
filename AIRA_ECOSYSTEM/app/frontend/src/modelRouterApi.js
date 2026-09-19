// API klien untuk Model Router (Sprint 1). Dipisah dari api.js supaya api.js
// tidak disentuh; boleh digabung ke api.js kapan saja (isinya murni fetch).

const BASE = "/api/models";

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

const enc = encodeURIComponent;

export const modelRouterApi = {
  list: (params = {}) => {
    const qs = new URLSearchParams(
      Object.fromEntries(Object.entries(params).filter(([, v]) => v))
    ).toString();
    return request(qs ? `?${qs}` : "");
  },
  get: (id) => request(`/${enc(id)}`),
  create: (payload) => request("", { method: "POST", body: JSON.stringify(payload) }),
  update: (id, payload) => request(`/${enc(id)}`, { method: "PUT", body: JSON.stringify(payload) }),
  remove: (id) => request(`/${enc(id)}`, { method: "DELETE" }),
  testConnection: (id) => request(`/${enc(id)}/test-connection`, { method: "POST" }),

  routing: () => request("/routing"),
  setDefault: (taskLabel, defaultModelId) =>
    request(`/routing/${enc(taskLabel)}`, {
      method: "PUT",
      body: JSON.stringify({ default_model_id: defaultModelId }),
    }),
  setPolicy: (patch) => request("/policy", { method: "PUT", body: JSON.stringify(patch) }),
  previewRoute: (prompt) =>
    request("/route-preview", { method: "POST", body: JSON.stringify({ prompt }) }),
};