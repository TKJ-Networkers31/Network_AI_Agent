// src/components/capabilities/MessageCapabilityActions.jsx
//
// SPRINT 2.7 - W8 (Dynamic Capability UI)
//
// Kapabilitas area "message_actions" - berbeda dari Hero/Chat Input/Dock,
// area ini lingkupnya PER PESAN (bisa berubah tiap pesan tergantung apakah
// pesan itu sedang punya seleksi teks aktif), jadi sengaja tidak lewat
// CapabilityContext global. Komponen ini fetch sendiri lewat
// useCapabilities() dengan konteks lokal (message_id, has_selection, dst)
// dan hanya dipasang saat MessageBubble sudah memutuskan aksi pesan itu
// boleh tampil (`showActions`), supaya tidak ada fetch untuk tiap pesan
// yang sedang di-stream atau tidak sedang di-hover.

import { useCapabilities } from "../../hooks/useCapabilities.js";
import CapabilityButton from "./CapabilityButton.jsx";

export default function MessageCapabilityActions({
  messageId,
  conversationId,
  sessionId,
  role,
  hasSelection,
  onInvoke,
}) {
  const { capabilities } = useCapabilities("message_actions", {
    message_id: messageId ?? undefined,
    conversation_id: conversationId ?? undefined,
    session_id: sessionId ?? undefined,
    role,
    has_selection: hasSelection,
  });

  if (capabilities.length === 0) return null;

  return (
    <>
      {capabilities.map((cap) => (
        <CapabilityButton key={cap.id} capability={cap} variant="icon" onInvoke={onInvoke} />
      ))}
    </>
  );
}
