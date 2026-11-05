// src/inventoryApi.js
// Klien API Inventory (device + credential) dengan token autentikasi RBAC.

import { getAuthHeaders } from "./api.js";

const BASE = "/api";
const enc = encodeURIComponent;

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
    let message = `Request gagal (${res.status})`;

    if (typeof body.detail === "string") message = body.detail;
    else if (Array.isArray(body.detail)) {
      message = body.detail.map((d) => `${(d.loc || []).slice(-1)[0]}: ${d.msg}`).join("; ");
    }

    throw new Error(message);
  }

  return res.json();
}

const json = (method, payload) => ({ method, body: JSON.stringify(payload) });

export const inventoryApi = {
  devices: {
    list: () => request("/devices"),
    create: (payload) => request("/devices", json("POST", payload)),
    update: (name, payload) => request(`/devices/${enc(name)}`, json("PUT", payload)),
    remove: (name) => request(`/devices/${enc(name)}`, { method: "DELETE" }),
    link: (name, credentialName) =>
      request(`/devices/${enc(name)}/credentials`, json("POST", { credential_name: credentialName })),
    unlink: (name, credentialName) =>
      request(`/devices/${enc(name)}/credentials/${enc(credentialName)}`, { method: "DELETE" }),
    test: (name) => request(`/devices/${enc(name)}/test`, { method: "POST" }),
  },
  credentials: {
    list: () => request("/credentials"),
    create: (payload) => request("/credentials", json("POST", payload)),
    update: (name, payload) => request(`/credentials/${enc(name)}`, json("PUT", payload)),
    remove: (name) => request(`/credentials/${enc(name)}`, { method: "DELETE" }),
  },
};
