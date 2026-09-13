const BASE = "/api";

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || `Request gagal (${res.status})`);
  }

  return res.json();
}

export const api = {
  // session_id: null -> backend otomatis membuat sesi baru
  chat: (message, sessionId = null) =>
    request("/chat", {
      method: "POST",
      body: JSON.stringify({ message, session_id: sessionId }),
    }),

  resetSession: (sessionId) =>
    request("/reset", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId }),
    }),

  tokenUsage: () => request("/token-usage"),

  // Manajemen model (list/select/default/fallback) sekarang HANYA lewat
  // namespace `models` di bawah - dipakai ModelsPage. Endpoint lama
  // /providers dan /providers/select sudah dihapus dari sini supaya
  // tidak ada 2 cara berbeda untuk melakukan hal yang sama.
  credits: () => request("/providers/credits"),

  facts: () => request("/memory/facts"),

  addFact: (key, value) =>
    request("/memory/facts", {
      method: "POST",
      body: JSON.stringify({ key, value }),
    }),

  deleteFact: (key) =>
    request(`/memory/facts/${encodeURIComponent(key)}`, {
      method: "DELETE",
    }),

  events: (limit = 20) => request(`/memory/events?limit=${limit}`),

  devices: () => request("/devices"),

  tools: () => request("/tools"),

  sessions: {
    list: () => request("/sessions"),

    create: () => request("/sessions", { method: "POST" }),

    messages: (id) => request(`/sessions/${encodeURIComponent(id)}/messages`),

    rename: (id, title) =>
      request(`/sessions/${encodeURIComponent(id)}`, {
        method: "PATCH",
        body: JSON.stringify({ title }),
      }),

    remove: (id) =>
      request(`/sessions/${encodeURIComponent(id)}`, {
        method: "DELETE",
      }),
  },

  logs: {
    list: (params = {}) => {
      const qs = new URLSearchParams(
        Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ""))
      ).toString();
      return request(`/logs${qs ? `?${qs}` : ""}`);
    },
    categories: () => request("/logs/categories"),
    stats: (sinceMinutes) =>
      request(`/logs/stats${sinceMinutes ? `?since_minutes=${sinceMinutes}` : ""}`),
    clear: (category) =>
      request(`/logs${category ? `?category=${encodeURIComponent(category)}` : ""}`, {
        method: "DELETE",
      }),
  },

  // Model Management System (REI Workspace) - satu-satunya tempat untuk
  // list/create/update/delete/set-default/set-fallback/enable/test-connection.
  models: {
    list: () => request("/models"),

    get: (nickname) => request(`/models/${encodeURIComponent(nickname)}`),

    create: (payload) =>
      request("/models", {
        method: "POST",
        body: JSON.stringify(payload),
      }),

    update: (nickname, payload) =>
      request(`/models/${encodeURIComponent(nickname)}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      }),

    remove: (nickname) =>
      request(`/models/${encodeURIComponent(nickname)}`, {
        method: "DELETE",
      }),

    setDefault: (nickname) =>
      request(`/models/${encodeURIComponent(nickname)}/set-default`, {
        method: "POST",
      }),

    setFallback: (nickname, isFallback) =>
      request(`/models/${encodeURIComponent(nickname)}/set-fallback`, {
        method: "POST",
        body: JSON.stringify({ is_fallback: isFallback }),
      }),

    setEnabled: (nickname, enabled) =>
      request(`/models/${encodeURIComponent(nickname)}/enable`, {
        method: "POST",
        body: JSON.stringify({ enabled }),
      }),

    testConnection: (nickname) =>
      request(`/models/${encodeURIComponent(nickname)}/test-connection`, {
        method: "POST",
      }),
  },
};