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

// Kandidat basis URL untuk endpoint non-/api (files, host). Yang terbukti jalan di-cache.
let rawBase = null;

function rawCandidates() {
  const list = [BASE, ""]; // "/api/..." lalu "/..."
  if (typeof window !== "undefined" && window.location.port === "5173") {
    const origin = `${window.location.protocol}//${window.location.hostname}:8000`;
    list.push(origin, `${origin}${BASE}`); // dev: langsung ke backend
  }
  return list;
}

async function rawRequest(path, options = {}) {
  const bases = rawBase === null ? rawCandidates() : [rawBase];
  let lastError = null;

  for (const base of bases) {
    let res;
    try {
      res = await fetch(`${base}${path}`, {
        headers: { "Content-Type": "application/json" },
        ...options,
      });
    } catch (err) {
      lastError = err; // CORS / koneksi gagal -> coba kandidat berikutnya
      continue;
    }

    const type = res.headers.get("content-type") || "";

    // Bukan JSON (HTML SPA fallback) -> route tidak ada di basis ini.
    if (!type.includes("json")) {
      lastError = new Error(`Endpoint ${base}${path} tidak ditemukan (balasan bukan JSON).`);
      continue;
    }

    const body = await res.json().catch(() => ({}));

    // 404 bawaan FastAPI untuk route yang tidak ada: detail persis "Not Found".
    if (res.status === 404 && body && body.detail === "Not Found") {
      lastError = new Error(`Route ${base}${path} tidak ada di backend.`);
      continue;
    }

    rawBase = base;

    if (!res.ok) {
      throw new Error(
        typeof body.detail === "string" ? body.detail : `Request gagal (${res.status})`
      );
    }

    return body;
  }

  throw lastError || new Error("Backend tidak terjangkau.");
}

export const api = {
  // FIX (Optimalisasi DIO): parameter ke-3 opsional 'dioSubmission' -
  // {schema_id, action_id, values, cancelled} - dikirim sebagai
  // dio_submission ke backend saat user submit form/pilihan interaktif.
  chat: (message, sessionId = null, dioSubmission = null) =>
    request("/chat", {
      method: "POST",
      body: JSON.stringify({
        message,
        session_id: sessionId,
        dio_submission: dioSubmission,
      }),
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

  // SPRINT 2.7 (W8 - Dynamic Capability UI): backend adalah satu-satunya
  // sumber kebenaran soal kapabilitas apa yang tersedia di tiap area UI
  // (hero, chat_input, capability_dock, message_actions, file_actions).
  // Frontend hanya mengirim `area` + sinyal konteks (attachment, selection,
  // artifact, location, conversation, file_path, dst) dan merender apa pun
  // yang dikembalikan - lihat hooks/useCapabilities.js.
  capabilities: {
    list: (params = {}) => {
      const qs = new URLSearchParams(
        Object.fromEntries(
          Object.entries(params).filter(
            ([, v]) => v !== undefined && v !== null && v !== "" && v !== false
          )
        )
      ).toString();
      return request(`/capabilities${qs ? `?${qs}` : ""}`);
    },
  },

  // === SPRINT 2.7.1 P0 FIX ===
  // Ketiga blok di bawah ini sebelumnya TIDAK ADA di api.js sama sekali,
  // padahal endpoint backend-nya (api/routers/selection.py,
  // api/routers/attachments.py, api/routers/artifacts.py) sudah ada/baru
  // dibuat - jadi UI tidak pernah punya cara memanggilnya (root cause flow
  // A/C/D di audit Sprint 2.5-2.8).
  selection: {
    create: (payload) =>
      request("/selection", { method: "POST", body: JSON.stringify(payload) }),
    action: (selectionId, action, userQuestion = "") =>
      request(`/selection/${encodeURIComponent(selectionId)}/actions`, {
        method: "POST",
        body: JSON.stringify({ action, user_question: userQuestion }),
      }),
  },

  attachments: {
    upload: (sessionId, file, messageId = null) => {
      const form = new FormData();
      form.append("session_id", sessionId);
      if (messageId) form.append("message_id", messageId);
      form.append("file", file);
      return fetch(`${BASE}/attachments`, { method: "POST", body: form }).then(async (res) => {
        if (!res.ok) {
          const detail = await res.json().catch(() => ({}));
          throw new Error(detail.detail || `Upload gagal (${res.status})`);
        }
        return res.json();
      });
    },
    list: (sessionId) => request(`/attachments?session_id=${encodeURIComponent(sessionId)}`),
    remove: (id) => request(`/attachments/${encodeURIComponent(id)}`, { method: "DELETE" }),
  },

  artifacts: {
    create: (payload) =>
      request("/artifacts", { method: "POST", body: JSON.stringify(payload) }),
    list: (sessionId) => request(`/artifacts?session_id=${encodeURIComponent(sessionId)}`),
    downloadUrl: (id) => `${BASE}/artifacts/${encodeURIComponent(id)}/download`,
  },
  // === akhir blok SPRINT 2.7.1 P0 FIX ===

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
