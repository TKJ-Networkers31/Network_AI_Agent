import { useEffect, useState } from "react";
import { settingsApi } from "../services/settingsApi.js";
import { createSingleFlight } from "../utils/singleFlight.js";
import { GREETING_SETTING_KEYS, settingsSnapshotFromApi } from "../utils/cockpitAdapter.js";

/**
 * useGlobalSettings() — snapshot Global Settings (W1) untuk layer greeting.
 *
 * - load sekali, cache di level modul (dipakai bersama TopBar & ChatPage)
 * - single-flight: banyak pemanggil bersamaan = satu request
 * - TIDAK ada polling; cache diperbarui lewat applyGlobalSettingsUpdate()
 *   (dipanggil GlobalSettingsPanel setelah menyimpan) atau saat aplikasi dimuat ulang
 *
 * Nilai kembalian:
 *   null -> belum selesai dimuat
 *   {}   -> gagal dimuat (pemanggil tetap jalan dari persona/default, tidak dicache)
 *   {..} -> snapshot: display_name, nickname, assistant_name, timezone,
 *           language, theme, greeting_style
 */

const EMPTY = Object.freeze({});

let cache = null;
const listeners = new Set();

const fetchSnapshot = createSingleFlight(async () =>
  settingsSnapshotFromApi(await settingsApi.getAll())
);

async function ensureLoaded() {
  if (cache) return cache;

  try {
    const snapshot = await fetchSnapshot();
    cache = snapshot;
    return snapshot;
  } catch {
    return EMPTY;
  }
}

/** Dipanggil setelah sebuah setting berhasil disimpan; hanya menyentuh key yang dikenal. */
export function applyGlobalSettingsUpdate(key, value) {
  if (!cache || !GREETING_SETTING_KEYS.includes(key) || typeof value !== "string") return;

  cache = Object.freeze({ ...cache, [key]: value });
  listeners.forEach((listener) => listener(cache));
}

export function useGlobalSettings() {
  const [snapshot, setSnapshot] = useState(cache);

  useEffect(() => {
    let active = true;

    const listener = (next) => {
      if (active) setSnapshot(next);
    };

    listeners.add(listener);

    if (cache) setSnapshot(cache);
    else ensureLoaded().then(listener);

    return () => {
      active = false;
      listeners.delete(listener);
    };
  }, []);

  return snapshot;
}