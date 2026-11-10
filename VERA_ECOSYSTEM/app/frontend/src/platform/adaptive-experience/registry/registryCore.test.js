import test from "node:test";
import assert from "node:assert/strict";
import {
  registerVaeComponent,
  unregisterVaeComponent,
  hasVaeComponent,
  getVaeComponent,
  getVaeComponentEntry,
  listRegisteredVaeComponents,
  clearVaeRegistry,
} from "./registryCore.js";

test("registryCore: register and lookup component", () => {
  clearVaeRegistry();
  const dummyComponent = () => "dummy";

  registerVaeComponent("metric-card", dummyComponent, { isLazy: false });
  assert.equal(hasVaeComponent("metric-card"), true);
  assert.equal(hasVaeComponent("METRIC-CARD"), true); // Case-insensitive
  assert.equal(getVaeComponent("metric-card"), dummyComponent);

  const entry = getVaeComponentEntry("metric-card");
  assert.equal(entry.isLazy, false);
});

test("registryCore: fallback when component not registered", () => {
  clearVaeRegistry();
  const fallback = () => "fallback";
  assert.equal(getVaeComponent("unregistered-type", fallback), fallback);
  assert.equal(hasVaeComponent("unregistered-type"), false);
});

test("registryCore: rejects invalid arguments", () => {
  clearVaeRegistry();
  assert.throws(() => registerVaeComponent("", () => {}), /requires a valid string type/);
  assert.throws(() => registerVaeComponent("test", null), /requires a valid component/);
});

test("registryCore: unregister and list", () => {
  clearVaeRegistry();
  registerVaeComponent("type-a", () => "a");
  registerVaeComponent("type-b", () => "b");
  assert.deepEqual(listRegisteredVaeComponents().sort(), ["type-a", "type-b"]);

  unregisterVaeComponent("type-a");
  assert.equal(hasVaeComponent("type-a"), false);
  assert.equal(hasVaeComponent("type-b"), true);
});
