/**
 * src/platform/adaptive-experience/registry/registryCore.js
 *
 * Core pure-JS VAE Component Registry.
 *
 * Implements strict type mapping, validation, and safe fallback.
 * Decoupled from JSX so it can be verified with Node.js native tests.
 */

const REGISTRY = new Map();

export function registerVaeComponent(type, component, { isLazy = false, meta = {} } = {}) {
  if (!type || typeof type !== "string") {
    throw new Error("VAE Component registration requires a valid string type");
  }
  if (!component) {
    throw new Error("VAE Component registration requires a valid component");
  }
  REGISTRY.set(type.trim().toLowerCase(), { component, isLazy, meta });
}

export function unregisterVaeComponent(type) {
  if (!type || typeof type !== "string") return false;
  return REGISTRY.delete(type.trim().toLowerCase());
}

export function hasVaeComponent(type) {
  if (!type || typeof type !== "string") return false;
  return REGISTRY.has(type.trim().toLowerCase());
}

export function getVaeComponentEntry(type) {
  if (!type || typeof type !== "string") return null;
  return REGISTRY.get(type.trim().toLowerCase()) || null;
}

export function getVaeComponent(type, fallback = null) {
  const entry = getVaeComponentEntry(type);
  return entry ? entry.component : fallback;
}

export function listRegisteredVaeComponents() {
  return Array.from(REGISTRY.keys());
}

export function clearVaeRegistry() {
  REGISTRY.clear();
}
