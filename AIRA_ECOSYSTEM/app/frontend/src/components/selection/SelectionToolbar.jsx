// src/components/selection/SelectionToolbar.jsx
//
// Floating toolbar aksi untuk sebuah SelectionContext (Sprint 2.7 / W4).
// Murni presentasi: menerima `selection` + `onAction(actionId, selection)`.
// Tidak memanggil API sendiri - itu tanggung jawab pemanggil (ChatPage/
// MessageBubble), yang bisa membangun ContextActionRequest lewat
// POST /api/selection lalu /api/selection/{id}/actions, ATAU membangun
// instruksinya langsung di klien untuk dikirim sebagai pesan biasa.

const ACTIONS = [
  { id: "explain", label: "Jelaskan" },
  { id: "simplify", label: "Sederhanakan" },
  { id: "expand", label: "Perluas" },
  { id: "rewrite", label: "Tulis ulang" },
  { id: "translate", label: "Terjemahkan" },
  { id: "continue", label: "Lanjutkan" },
  { id: "create_document", label: "Jadikan dokumen" },
  { id: "ask", label: "Tanya AIRA" },
];

export default function SelectionToolbar({ selection, onAction, onClose }) {
  if (!selection || !selection.selected_text) return null;

  return (
    <div
      role="toolbar"
      aria-label="Aksi seleksi teks"
      className="inline-flex items-center gap-1 bg-panel border border-border rounded-pill px-1.5 py-1 shadow-xl"
    >
      {ACTIONS.map((a) => (
        <button
          key={a.id}
          type="button"
          onClick={() => onAction?.(a.id, selection)}
          className="text-xs px-2.5 py-1 rounded-pill text-white/70 hover:text-white hover:bg-white/10 transition whitespace-nowrap"
        >
          {a.label}
        </button>
      ))}
      {onClose && (
        <button
          type="button"
          onClick={onClose}
          aria-label="Tutup"
          className="text-xs px-2 py-1 text-white/40 hover:text-white"
        >
          ✕
        </button>
      )}
    </div>
  );
}