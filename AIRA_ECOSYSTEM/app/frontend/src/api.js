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

  providers: () => request("/providers"),

  selectProvider: (key) =>
    request("/providers/select", {
      method: "POST",
      body: JSON.stringify({ key }),
    }),

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
};
