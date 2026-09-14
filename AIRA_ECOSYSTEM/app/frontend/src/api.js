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

async function rawRequest(path, options = {}) {
  const res = await fetch(path, {
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
    active: () => request("/sessions/active"),
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

  // FIX (P0 blank-screen bug): this block was previously nested INSIDE
  // `models` above, so `api.connections` was `undefined`. Every caller
  // (ConnectionIndicator.jsx, ConnectionPanel.jsx, AkaneWorkspace.jsx)
  // does `api.connections.list()` / `.open()` / `.close()` / `.execute()`,
  // which expects this to be a TOP-LEVEL key of `api`. Moved here as a
  // sibling of `models`, `sessions`, `logs`, etc.
  connections: {
    list: () => request("/connections"),
    get: (sessionId) => request(`/connections/${encodeURIComponent(sessionId)}`),
    open: (payload) =>
      request("/connections/open", { method: "POST", body: JSON.stringify(payload) }),
    close: (sessionId) =>
      request("/connections/close", {
        method: "POST",
        body: JSON.stringify({ session_id: sessionId }),
      }),
    execute: (sessionId, command) =>
      request("/connections/execute", {
        method: "POST",
        body: JSON.stringify({ session_id: sessionId, command }),
      }),
  },

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
   host: {
    info: () => rawRequest("/host/info"),
  },

  workspace: {
    tree: (path = "", maxDepth = 6) =>
      rawRequest(`/files/tree?path=${encodeURIComponent(path)}&max_depth=${maxDepth}`),
    read: (path) => rawRequest(`/files/read?path=${encodeURIComponent(path)}`),
    write: (path, content, encoding = "utf-8") =>
      rawRequest("/files/write", {
        method: "POST",
        body: JSON.stringify({ path, content, encoding }),
      }),
    mkdir: (path) =>
      rawRequest("/files/mkdir", { method: "POST", body: JSON.stringify({ path }) }),
    move: (source, destination) =>
      rawRequest("/files/move", {
        method: "POST",
        body: JSON.stringify({ source, destination }),
      }),
    copy: (source, destination) =>
      rawRequest("/files/copy", {
        method: "POST",
        body: JSON.stringify({ source, destination }),
      }),
    rename: (source, destination) =>
      rawRequest("/files/rename", {
        method: "POST",
        body: JSON.stringify({ source, destination }),
      }),
    delete: (path) =>
      rawRequest("/files/delete", { method: "DELETE", body: JSON.stringify({ path }) }),
    restore: (trashId) =>
      rawRequest("/files/restore", {
        method: "POST",
        body: JSON.stringify({ trash_id: trashId }),
      }),
    trashList: () => rawRequest("/files/trash"),
    trashEmpty: () => rawRequest("/files/trash/empty", { method: "POST" }),
    permissions: () => rawRequest("/files/permissions"),
  },
};