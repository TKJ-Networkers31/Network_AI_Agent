// src/components/capabilities/CapabilityInputSlot.jsx
//
// SPRINT 2.7 - W8 (Dynamic Capability UI)
//
// Baris ikon kapabilitas area "chat_input", dirender di dalam form
// ChatInput.jsx (di samping voiceControls). Tidak menyentuh logic kirim
// pesan / slash menu / Enter-to-send yang sudah ada - murni tambahan visual
// yang menerima `onInvoke` dari ChatPage.

import { useCapabilityContext } from "../../context/CapabilityContext.jsx";
import CapabilityButton from "./CapabilityButton.jsx";

export default function CapabilityInputSlot({ onInvoke }) {
  const { forArea } = useCapabilityContext();
  const capabilities = forArea("chat_input");

  if (capabilities.length === 0) return null;

  return (
    <div className="flex items-center gap-0.5 shrink-0">
      {capabilities.map((cap) => (
        <CapabilityButton key={cap.id} capability={cap} variant="icon" onInvoke={onInvoke} />
      ))}
    </div>
  );
}
