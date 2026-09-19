// src/components/MobileNav.jsx
//
// PERUBAHAN (UI Layout): bar bawah tidak lagi berisi 9 item yang di-scroll.
// Hanya 4 tab utama + tombol "Menu" yang membuka drawer sidebar (berisi
// semua menu terklasifikasi). Tombol "Menu" menyala kalau halaman aktif
// bukan salah satu dari 4 tab utama.
// Tinggi bar (h-14) HARUS sama dengan padding bawah <main> di App.jsx.

import { Menu } from "lucide-react";
import { ALL_NAV_ITEMS } from "./navConfig.js";

const PRIMARY_IDS = ["chat", "workspace", "devices", "akane"];

const PRIMARY_ITEMS = PRIMARY_IDS.map((id) => ALL_NAV_ITEMS.find((item) => item.id === id)).filter(
  Boolean
);

function TabButton({ icon: Icon, label, isActive, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={isActive ? "page" : undefined}
      className={`flex flex-col items-center justify-center gap-0.5 text-[10px] font-medium transition
        ${isActive ? "text-sakura" : "text-text-secondary"}`}
    >
      <Icon size={20} strokeWidth={isActive ? 2.3 : 1.9} />
      <span>{label}</span>
    </button>
  );
}

export default function MobileNav({ active, onChange, onOpenMenu }) {
  const moreActive = !PRIMARY_IDS.includes(active);

  return (
    <nav className="md:hidden fixed bottom-0 inset-x-0 z-40 bg-surface/95 backdrop-blur-xl border-t border-border pb-[env(safe-area-inset-bottom)]">
      <div className="grid grid-cols-5 h-14">
        {PRIMARY_ITEMS.map((item) => (
          <TabButton
            key={item.id}
            icon={item.icon}
            label={item.label}
            isActive={active === item.id}
            onClick={() => onChange(item.id)}
          />
        ))}

        <TabButton icon={Menu} label="Menu" isActive={moreActive} onClick={onOpenMenu} />
      </div>
    </nav>
  );
}