// src/components/capabilities/CapabilityHeroRow.jsx
//
// SPRINT 2.7 - W8 (Dynamic Capability UI)
//
// Baris chip kapabilitas area "hero" - dirender di bawah DynamicHero/Hero
// saat percakapan masih kosong. Tidak menyentuh Hero.jsx/DynamicHero.jsx
// sama sekali (keduanya tetap seperti Sprint 2.6); ini komponen baru yang
// ditaruh sebagai sibling di ChatPage.

import { useCapabilityContext } from "../../context/CapabilityContext.jsx";
import CapabilityButton from "./CapabilityButton.jsx";

export default function CapabilityHeroRow({ onInvoke }) {
  const { forArea } = useCapabilityContext();
  const capabilities = forArea("hero");

  if (capabilities.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center justify-center gap-2 mt-3">
      {capabilities.map((cap) => (
        <CapabilityButton key={cap.id} capability={cap} variant="pill" onInvoke={onInvoke} />
      ))}
    </div>
  );
}
