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

  models: {
    list: () => request("/models"),
    get: (nickname) => request(`/models/${encodeURIComponent(nickname)}`),
    create: (payload) =>
      request("/models", { method: "POST", body: JSON.stringify(payload) }),
    update: (nickname, payload) =>
      request(`/models/${encodeURIComponent(nickname)}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      }),
    remove: (nickname) =>
      request(`/models/${encodeURIComponent(nickname)}`, { method: "DELETE" }),
    setDefault: (nickname) =>
      request(`/models/${encodeURIComponent(nickname)}/set-default`, { method: "POST" }),
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
      request(`/models/${encodeURIComponent(nickname)}/test-connection`, { method: "POST" }),
  },

  // Dynamic Persona Engine (Phase 1.3) - identity, behavior slider, preset,
  // dan live preview system prompt. TIDAK pernah memanggil LLM.
  persona: {
    get: () => request("/persona"),

    updateProfile: (payload) =>
      request("/persona/profile", {
        method: "PUT",
        body: JSON.stringify(payload),
      }),

    updateBehavior: (payload) =>
      request("/persona/behavior", {
        method: "PUT",
        body: JSON.stringify(payload),
      }),

    presets: () => request("/persona/presets"),

    getPreset: (presetId) =>
      request(`/persona/presets/${encodeURIComponent(presetId)}`),

    applyPreset: (presetId) =>
      request("/persona/presets/apply", {
        method: "POST",
        body: JSON.stringify({ preset_id: presetId }),
      }),

    clonePreset: (presetId, newName) =>
      request("/persona/presets/clone", {
        method: "POST",
        body: JSON.stringify({ preset_id: presetId, new_name: newName }),
      }),

    preview: (extraContext = "") =>
      request("/persona/preview", {
        method: "POST",
        body: JSON.stringify({ extra_context: extraContext }),
      }),
  },
};