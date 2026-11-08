import ToolButton from "./ToolButton.jsx";
import { normalizeTool } from "./cockpitContracts.js";

/**
 * Tool Dock berbasis data - satu baris, scroll horizontal, tinggi tetap.
 * Ikon di-resolve lewat shared/iconRegistry.js (bukan folder cockpit).
 * Props: tools · activeId · onSelect(tool) · iconRegistry (registry lokal opsional)
 */
export default function ToolDock({ tools = [], activeId = null, onSelect, iconRegistry }) {
  const list = (Array.isArray(tools) ? tools : []).map((t, i) => normalizeTool(t, i));

  if (list.length === 0) return null;

  return (
    <div
      className="px-3 sm:px-5 lg:px-6 pb-2 flex items-center gap-1.5 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      role="toolbar"
      aria-label="Tools"
    >
      {list.map((t) => (
        <ToolButton
          key={t.id}
          tool={t}
          active={t.id === activeId}
          iconRegistry={iconRegistry}
          onSelect={onSelect}
        />
      ))}
    </div>
  );
}
