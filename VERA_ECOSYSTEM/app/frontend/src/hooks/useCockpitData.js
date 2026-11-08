import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api.js";
import { useChatRuntime } from "../context/ChatRuntimeContext.jsx";
import { createSingleFlight } from "../utils/singleFlight.js";
import {
  CONNECTIONS_CHANGED_EVENT,
  activityFromRuntime,
  connectionsFromApi,
  countActiveConnections,
  getWorkspaceTools,
  runtimeFromChatRuntime,
} from "../utils/cockpitAdapter.js";

/**
 * useCockpitData() — satu-satunya jembatan antara state AIRA dan
 * <WorkspaceCockpit>. Cockpit sendiri hanya menerima props.
 *
 * Koneksi (TANPA polling, TANPA menyentuh WS bridge / ConnectionManager / Event Bus):
 *   - snapshot awal: api.connections.list() SEKALI saat mount
 *   - refresh hanya saat:
 *       1. event "aira:connections-changed"
 *       2. visibilitychange (tab kembali terlihat)
 *       3. FALLBACK: proses chat selesai (loading true -> false)
 *   - refresh bersamaan dilebur (single-flight); gagal = pertahankan data terakhir
 *
 * Runtime dibaca dari useChatRuntime() yang sudah ada (tidak ada runtime baru).
 */
export function useCockpitData() {
  const { loading, streaming, liveTools } = useChatRuntime();

  const [apiConnections, setApiConnections] = useState([]);
  const mountedRef = useRef(true);
  const flightRef = useRef(null);

  if (flightRef.current === null) {
    flightRef.current = createSingleFlight(async () => {
      const res = await api.connections.list();
      return Array.isArray(res && res.connections) ? res.connections : [];
    });
  }

  const refresh = useCallback(async () => {
    try {
      const list = await flightRef.current();
      if (mountedRef.current) setApiConnections(list);
    } catch {
      // gagal sesaat: tampilan tetap memakai snapshot terakhir
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    refresh();

    const onChanged = () => refresh();
    const onVisibility = () => {
      if (document.visibilityState === "visible") refresh();
    };

    window.addEventListener(CONNECTIONS_CHANGED_EVENT, onChanged);
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      mountedRef.current = false;
      window.removeEventListener(CONNECTIONS_CHANGED_EVENT, onChanged);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [refresh]);

  // Fallback: sebuah giliran chat baru saja selesai (tool bisa membuka/menutup koneksi).
  const wasLoadingRef = useRef(loading);

  useEffect(() => {
    if (wasLoadingRef.current && !loading) refresh();
    wasLoadingRef.current = loading;
  }, [loading, refresh]);

  const connections = useMemo(() => connectionsFromApi(apiConnections), [apiConnections]);
  const activeConnectionCount = useMemo(() => countActiveConnections(connections), [connections]);
  const activity = useMemo(
    () => activityFromRuntime({ connections, liveTools }),
    [connections, liveTools]
  );
  const runtime = useMemo(() => runtimeFromChatRuntime({ loading, streaming }), [loading, streaming]);
  const tools = useMemo(() => getWorkspaceTools(), []);

  return { connections, activeConnectionCount, activity, runtime, tools, refresh };
}