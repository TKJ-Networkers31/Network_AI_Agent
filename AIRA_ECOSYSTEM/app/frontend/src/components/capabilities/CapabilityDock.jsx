// src/components/capabilities/CapabilityDock.jsx
//
// SPRINT 2.7 - W8 (Dynamic Capability UI)
//
// Dock horizontal untuk kapabilitas area "capability_dock" - strip terpisah
// dari ComposerCockpit (yang tidak disentuh sama sekali di paket ini, sesuai
// batasan "Do not redesign Workspace"). Dirender sebagai sibling di
// ChatPage, tepat di atas ComposerCockpit.
//
// Reaktif terhadap attachment/artifact/location/conversation lewat
// CapabilityContext (lihat context/CapabilityContext.jsx) - dock ini sendiri
// tidak tahu sinyal mana yang berubah, hanya membaca ulang hasil forArea()
// setiap kali context-nya berubah.
//
// Kosong -> dock disembunyikan total (tidak ada strip kosong yang mengambil
// ruang). Loading pertama kali (belum pernah dapat data) -> skeleton pill
// redup. Setelah ada data, refetch berikutnya tidak menampilkan skeleton
// lagi supaya tidak "berkedip" tiap kali konteks berubah.

import { useCapabilityContext } from "../../context/CapabilityContext.jsx";
import CapabilityButton from "./CapabilityButton.jsx";

export default function CapabilityDock({ onInvoke }) {
  const { forArea, loading } = useCapabilityContext();
  const capabilities = forArea("capability_dock");

  if (capabilities.length === 0) {
    if (!loading) return null;
    return (
      <div className="flex items-center gap-1.5 px-1 py-1.5 overflow-x-auto">
        {[0, 1, 2].map((i) => (
          <span key={i} className="h-7 w-16 rounded-pill bg-white/5 animate-pulse shrink-0" />
        ))}
      </div>
    );
  }

  return (
    <div className="flex items-center gap-1.5 px-1 py-1.5 overflow-x-auto">
      {capabilities.map((cap) => (
        <CapabilityButton key={cap.id} capability={cap} variant="pill" onInvoke={onInvoke} />
      ))}
    </div>
  );
}
