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
  chat: (message, sessionId = "default") =>
    request("/chat", {
      method: "POST",
      body: JSON.stringify({ message, session_id: sessionId }),
    }),

  reset: (sessionId = "default") =>
    request("/reset", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId }),
    }),

  tokenUsage: (sessionId = "default") =>
    request(`/token-usage?session_id=${encodeURIComponent(sessionId)}`),

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
};
