// src/context/CapabilityContext.jsx
//
// SPRINT 2.7 - W8 (Dynamic Capability UI)
//
// Menyimpan sinyal konteks percakapan yang dipakai untuk menentukan
// kapabilitas apa yang backend kirim untuk tiga area yang scope-nya
// "percakapan aktif" (bukan per-pesan/per-file): Hero, Chat Input, dan
// Capability Dock. Area "message_actions" (per-pesan) dan "file_actions"
// (per-file) sengaja TIDAK lewat context ini - keduanya fetch sendiri
// lewat useCapabilities() dengan konteks lokal masing-masing (lihat
// MessageCapabilityActions.jsx dan FileCapabilityActions.jsx), supaya
// selection/file_path tidak perlu naik jadi state global.
//
// Provider ini HANYA membawa sinyal + hasil fetch - tidak tahu apa arti
// tiap kapabilitas, tidak menjalankan aksi apa pun (itu tugas
// utils/capabilityInvoke.js yang dipanggil dari komponen pemakai).

import { createContext, useCallback, useContext, useMemo, useState } from "react";
import { useCapabilities } from "../hooks/useCapabilities.js";

const CapabilityCtx = createContext(null);

export function CapabilityProvider({ conversationId, children }) {
  const [hasAttachment, setHasAttachment] = useState(false);
  const [hasArtifact, setHasArtifact] = useState(false);
  const [hasLocation, setHasLocation] = useState(false);

  const context = useMemo(
    () => ({
      conversation_id: conversationId || undefined,
      has_attachment: hasAttachment,
      has_artifact: hasArtifact,
      has_location: hasLocation,
    }),
    [conversationId, hasAttachment, hasArtifact, hasLocation]
  );

  // Satu fetch untuk ketiga area "conversation" - filter per-area di sisi
  // klien lewat forArea(), bukan tiga request terpisah untuk sinyal yang sama.
  const { capabilities, loading, error } = useCapabilities("conversation", context);

  const forArea = useCallback(
    (area) => capabilities.filter((c) => c.area === area),
    [capabilities]
  );

  const value = useMemo(
    () => ({
      capabilities,
      loading,
      error,
      forArea,
      hasAttachment,
      hasArtifact,
      hasLocation,
      setHasAttachment,
      setHasArtifact,
      setHasLocation,
    }),
    [capabilities, loading, error, forArea, hasAttachment, hasArtifact, hasLocation]
  );

  return <CapabilityCtx.Provider value={value}>{children}</CapabilityCtx.Provider>;
}

export function useCapabilityContext() {
  const ctx = useContext(CapabilityCtx);
  if (!ctx) {
    throw new Error("useCapabilityContext harus dipakai di dalam <CapabilityProvider>.");
  }
  return ctx;
}
