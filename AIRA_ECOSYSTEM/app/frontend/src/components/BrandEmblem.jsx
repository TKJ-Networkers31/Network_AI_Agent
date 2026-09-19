// src/components/BrandEmblem.jsx
//
// Emblem core bunga sakura AIRA (dipakai di header Sidebar & Hero chat).
// - Path asset hanya ada di SATU tempat (EMBLEM_SRC).
// - Ukuran semua emblem dikali EMBLEM_SCALE (satu angka untuk seluruh app).
// - Kalau gambar gagal dimuat, fallback ke ikon bunga (lucide).

import { useState } from "react";
import { Flower2 } from "lucide-react";

export const EMBLEM_SRC = "/assets/brand/boot-emblem.png";

// Pengali ukuran global. 1 = ukuran awal. Naikkan kalau masih kecil
// (mis. 1.4), turunkan kalau kebesaran. Catatan: header sidebar setinggi
// 56px (h-14), jadi di atas ~1.4 emblem di sidebar mulai mepet border.
export const EMBLEM_SCALE = 1.3;

export default function BrandEmblem({ size = 32, glow = false, className = "" }) {
  const [failed, setFailed] = useState(false);

  const px = Math.round(size * EMBLEM_SCALE);
  const boxStyle = { width: px, height: px };

  if (failed) {
    return (
      <div
        className={`shrink-0 rounded-pill bg-sakura-gradient flex items-center justify-center ${className}`}
        style={boxStyle}
      >
        <Flower2 size={Math.round(px * 0.5)} strokeWidth={2} className="text-white" />
      </div>
    );
  }

  return (
    <img
      src={EMBLEM_SRC}
      alt="AIRA"
      draggable={false}
      onError={() => setFailed(true)}
      className={`shrink-0 object-contain select-none ${className}`}
      style={{
        ...boxStyle,
        ...(glow ? { filter: "drop-shadow(0 0 16px rgba(244,114,182,0.45))" } : {}),
      }}
    />
  );
}