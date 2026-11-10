// src/modelRouterApi.js
// Authoritative API client for VERA Model Registry, Discovery, Routing & Telemetry.

import { getAuthHeaders } from "./api.js";

const BASE = "/api/models";

async function request(path, options = {}) {
  const authHeaders = getAuthHeaders();
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders,
      ...(options.headers || {}),
    },
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : `Request gagal (${res.status})`);
  }

  return res.json();
}

async function providerRequest(path, options = {}) {
  const authHeaders = getAuthHeaders();
  const res = await fetch(`/api/providers${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders,
      ...(options.headers || {}),
    },
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : `Provider request gagal (${res.status})`);
  }

  return res.json();
}

const enc = encodeURIComponent;

export const modelRouterApi = {
  // Model catalog queries
  list: (params = {}) => {
    const qs = new URLSearchParams(
      Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ""))
    ).toString();
    return request(qs ? `?${qs}` : "");
  },
  get: (id) => request(`/${enc(id)}`),
  getActive: (label = "general") => request(`/active?label=${enc(label)}`),
  getClassifications: () => request("/classifications"),
  getCapabilities: () => request("/capabilities"),
  getBenchmarks: () => request("/benchmarks"),
  getSyncStatus: () => request("/sync-status"),

  // Administrative mutations
  create: (payload) => request("", { method: "POST", body: JSON.stringify(payload) }),
  update: (id, payload) => request(`/${enc(id)}`, { method: "PUT", body: JSON.stringify(payload) }),
  updateStatus: (id, enabled) => request(`/${enc(id)}/status`, { method: "PUT", body: JSON.stringify({ enabled }) }),
  updatePriority: (id, priority) => request(`/${enc(id)}/priority`, { method: "PUT", body: JSON.stringify({ priority }) }),
  remove: (id) => request(`/${enc(id)}`, { method: "DELETE" }),
  testConnection: (id) => request(`/${enc(id)}/test-connection`, { method: "POST" }),
  healthCheck: (id) => request(`/${enc(id)}/health-check`, { method: "POST" }),
  syncRemote: (provider = "nvidia", apiKey = null) =>
    request("/sync", {
      method: "POST",
      body: JSON.stringify({ provider, api_key: apiKey }),
    }),

  // Routing & Policy
  routing: () => request("/routing"),
  setDefault: (taskLabel, defaultModelId) =>
    request(`/routing/${enc(taskLabel)}`, {
      method: "PUT",
      body: JSON.stringify({ default_model_id: defaultModelId }),
    }),
  setPolicy: (patch) => request("/policy", { method: "PUT", body: JSON.stringify(patch) }),
  previewRoute: (prompt) =>
    request("/route-preview", { method: "POST", body: JSON.stringify({ prompt }) }),

  // Provider Telemetry & Management
  getProviders: () => providerRequest(""),
  getProviderHealth: () => providerRequest("/health"),
  checkProviderHealth: (provider) => providerRequest(`/${enc(provider)}/health-check`, { method: "POST" }),
  resetProviderCircuit: (provider) => providerRequest(`/${enc(provider)}/reset-circuit`, { method: "POST" }),
};
