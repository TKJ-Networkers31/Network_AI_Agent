// Melapor ke server "dari mana AIRA sedang diakses" setiap sesi aktif berganti.
// Tanpa GPS -> server menebak dari IP/jaringan klien. Dengan GPS (kalau user
// mengaktifkannya di Settings dan browser mengizinkan) -> lokasi presisi.
// Best effort: kegagalan apa pun diabaikan, tidak pernah mengganggu chat.

import { useEffect } from "react";
import { useSessionsContext } from "../../context/SessionsContext.jsx";
import {
  locationApi,
  canUseGps,
  getGpsEnabled,
  getBrowserPosition,
} from "../../services/location.js";

export default function AccessLocationReporter() {
  const { activeId } = useSessionsContext();

  useEffect(() => {
    if (!activeId) return undefined;

    let cancelled = false;

    async function report() {
      let coords = {};

      if (getGpsEnabled() && canUseGps()) {
        try {
          coords = await getBrowserPosition();
        } catch {
          // izin ditolak / timeout -> jatuh ke lokasi berbasis jaringan
        }
      }

      if (cancelled) return;

      try {
        await locationApi.reportAccess({ session_id: activeId, ...coords });
      } catch {
        // best effort
      }
    }

    report();

    return () => {
      cancelled = true;
    };
  }, [activeId]);

  return null;
}