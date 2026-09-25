// AIRA_ECOSYSTEM/app/frontend/src/components/MessageBubble.jsx
//
// FIX (Optimalisasi DIO - root cause "form tidak pernah tampil"):
// Sekarang menerima prop `interactionSchema` (Universal Interaction
// Schema dari backend) + `interactionResolved` (sudah di-submit atau
// belum) + `onSubmitInteraction`. Kalau schema ada dan belum resolved,
// <Renderer> DIO dirender di atas/sebagai pengganti bubble teks kosong.
//
// PERUBAHAN (Chat Session): aksi per pesan.
// - Pesan user      : Salin, Edit (edit di tempat, lalu "Kirim ulang").
// - Pesan assistant : Salin, Buat ulang (hanya di jawaban terakhir).
// Tombol aksi muncul saat hover (desktop) dan selalu terlihat di layar
// sentuh. Edit/Buat ulang dinonaktifkan selama ada proses berjalan (`busy`).
//
// PERUBAHAN (Sprint 2.5 - Thinking/Loading UX): prop `streaming` - pesan yang
// sedang diisi potongan jawaban. Aksi (salin/buat ulang) disembunyikan sampai
// pesan final menggantikannya di posisi yang sama (bubble tidak remount, jadi
// animasi reveal tidak diputar ulang). Bagian lain tidak berubah.
//
// SPRINT 2.7 (W8 - Dynamic Capability UI):
// - Baris aksi (Salin/Edit/Buat ulang) sekarang juga merender kapabilitas
//   dinamis area "message_actions" lewat <MessageCapabilityActions>, HANYA
//   saat `showActions` sudah true (pesan tidak sedang streaming & bukan
//   pesan lokal) - supaya tidak ada fetch capability untuk tiap pesan yang
//   sedang jalan. Konteksnya reaktif terhadap seleksi teks pesan ini
//   (`selection` dari useSelectionContext yang sudah ada).
// - Prop baru `onCapabilityInvoke` (opsional), diteruskan apa adanya ke
//   MessageCapabilityActions. Tidak ada perubahan pada logic Copy/Edit/
//   Regenerate/DIO yang sudah ada.
import { useEffect, useRef, useState } from "react";
import ToolStep from "./ToolStep.jsx";
import Markdown from "./Markdown.jsx";
import Renderer from "./dio/Renderer.jsx";
import CopyButton from "./CopyButton.jsx";
import { useSelectionContext } from "../hooks/useSelectionContext.js";
import SelectionToolbar from "./selection/SelectionToolbar.jsx";
import MessageCapabilityActions from "./capabilities/MessageCapabilityActions.jsx";

function ProcessSteps({ steps }) {
  const [open, setOpen] = useState(false);

  if (!steps || steps.length === 0) return null;

  const toolCallCount = steps.filter((s) => s.type === "tool_call").length;
  const allOk = steps.every((s) => s.type !== "tool_call" || s.success);

  const summary =
    toolCallCount > 0
      ? `${toolCallCount} tool${toolCallCount > 1 ? "s" : ""} digunakan`
      : "Proses selesai";

  return (
    <div className="mb-2">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 text-xs text-white/50 hover:text-white/80 transition px-1 py-1"
      >
        <span
          className={`inline-block w-1.5 h-1.5 rounded-full ${
            allOk ? "bg-emerald-400" : "bg-amber-400"
          }`}
        />
        <span>{summary}</span>
        <svg
          viewBox="0 0 24 24"
          fill="none"
          className={`transition-transform ${open ? "rotate-180" : ""}`}
          style={{ width: 12, height: 12 }}
        >
          <path
            d="m6 9 6 6 6-6"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>

      {open && (
        <div className="mt-1.5 space-y-1.5">
          {steps.map((step, i) => (
            <ToolStep key={i} step={step} />
          ))}
        </div>
      )}
    </div>
  );
}

function ActionButton({ title, onClick, disabled, children }) {
  return (
    <button
      type="button"
      title={title}
      aria-label={title}
      onClick={onClick}
      disabled={disabled}
      className="w-7 h-7 inline-flex items-center justify-center rounded-pill text-white/40 hover:text-white hover:bg-white/10 transition disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:bg-transparent disabled:hover:text-white/40"
    >
      {children}
    </button>
  );
}

function EditIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" style={{ width: 14, height: 14 }}>
      <path
        d="M4 20h4L19 9a2.1 2.1 0 0 0-3-3L5 17v3Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="m14 7 3 3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function RegenerateIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" style={{ width: 14, height: 14 }}>
      <path
        d="M20 11a8 8 0 1 0-2.3 5.7"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <path
        d="M20 5v6h-6"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function EditBox({ initial, hasFollowing, onCancel, onSubmit }) {
  const [value, setValue] = useState(initial);
  const areaRef = useRef(null);

  useEffect(() => {
    const el = areaRef.current;
    if (!el) return;
    el.focus();
    el.setSelectionRange(el.value.length, el.value.length);
  }, []);

  useEffect(() => {
    const el = areaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 240)}px`;
  }, [value]);

  function submit() {
    const trimmed = value.trim();
    if (!trimmed) return;
    onSubmit(trimmed);
  }

  return (
    <div className="rounded-xl2 border border-sakura/40 bg-surface/80 p-3 space-y-2.5">
      <textarea
        ref={areaRef}
        value={value}
        rows={1}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            submit();
          }
          if (e.key === "Escape") onCancel();
        }}
        className="w-full bg-transparent resize-none outline-none text-sm text-text-primary leading-relaxed"
      />

      {hasFollowing && (
        <p className="text-[11px] text-amber-300/80">
          Balasan setelah pesan ini akan diganti dengan jawaban baru.
        </p>
      )}

      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="text-xs px-3 py-1.5 rounded-pill bg-white/5 text-text-secondary hover:text-text-primary transition"
        >
          Batal
        </button>
        <button
          type="button"
          onClick={submit}
          disabled={!value.trim()}
          className="text-xs px-3.5 py-1.5 rounded-pill bg-sakura-gradient text-white font-medium disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Kirim ulang
        </button>
      </div>
    </div>
  );
}

// Pesan yang dibuat otomatis dari submit form DIO - mengedit teksnya tidak
// masuk akal (data form-nya tidak ikut terkirim), jadi tombol Edit disembunyikan.
function isDioSubmissionText(text) {
  return /^(📝|❌)/.test(text || "");
}

export default function MessageBubble({
  role,
  content,
  steps,
  isNew,
  local,
  streaming,
  interactionSchema,
  interactionResolved,
  onSubmitInteraction,
  busy,
  canRegenerate,
  onRegenerate,
  hasFollowing,
  onEdit,
  messageId = null,
  conversationId = null,
  sessionId = null,
  onSelectionAction,
  onCapabilityInvoke,
}) {
  const isUser = role === "user";
  const hasInteraction = !isUser && Boolean(interactionSchema);
  const [editing, setEditing] = useState(false);

  const contentRef = useRef(null);
  const { selection, clear: clearSelection } = useSelectionContext(contentRef, {
    messageId, conversationId, sessionId,
  });

  function handleSelectionAction(actionId, sel) {
    onSelectionAction?.(actionId, sel);
    clearSelection();
  }

  const canEdit = isUser && Boolean(content) && !isDioSubmissionText(content) && Boolean(onEdit);
  const showAssistantActions = !isUser && !local && !streaming && Boolean(content);
  const showActions = !editing && (isUser ? Boolean(content) : showAssistantActions);

  const widthClass = isUser
    ? editing
      ? "w-full"
      : ""
    : "w-full";

  return (
    <div className={`group flex ${isUser ? "justify-end" : "justify-start"} ${isNew ? "reveal-fade" : ""}`}>
      <div className={`max-w-[88%] sm:max-w-[75%] ${widthClass}`}>
        {!isUser && <ProcessSteps steps={steps} />}

        {hasInteraction && !interactionResolved && (
          <div className="mb-2">
            <Renderer schema={interactionSchema} onSubmitAction={onSubmitInteraction} />
          </div>
        )}

        {hasInteraction && interactionResolved && (
          <div className="mb-2 flex items-center gap-2 text-xs text-white/40 italic px-1">
            <span>✓</span>
            <span>Form sudah dikirim.</span>
          </div>
        )}

        {isUser && editing ? (
          <EditBox
            initial={content}
            hasFollowing={hasFollowing}
            onCancel={() => setEditing(false)}
            onSubmit={(text) => {
              setEditing(false);
              onEdit?.(text);
            }}
          />
        ) : (
          content && (
            <div
              ref={contentRef}
              className={`rounded-xl2 px-4 py-3 text-sm leading-relaxed break-words
                ${
                  isUser
                    ? "bg-accent-gradient text-white whitespace-pre-wrap"
                    : local
                    ? "bg-white/[0.03] border border-border text-white/60"
                    : "bg-card border border-border text-white/90"
                }`}
            >
              {isUser ? content : <Markdown content={content} />}
            </div>
          )
        )}

        {selection && (
          <div
            data-selection-toolbar
            onMouseDown={(e) => e.preventDefault()}
            className="mt-1.5"
          >
            <SelectionToolbar
              selection={selection}
              onAction={handleSelectionAction}
              onClose={clearSelection}
            />
          </div>
        )}

        {showActions && (
          <div
            className={`mt-1 flex items-center gap-0.5 ${isUser ? "justify-end" : "justify-start"}
              md:opacity-0 md:group-hover:opacity-100 focus-within:opacity-100 transition-opacity`}
          >
            <CopyButton text={content} title={isUser ? "Salin prompt" : "Salin jawaban"} />

            {canEdit && (
              <ActionButton
                title={busy ? "Tunggu proses selesai" : "Edit prompt"}
                disabled={busy}
                onClick={() => setEditing(true)}
              >
                <EditIcon />
              </ActionButton>
            )}

            {!isUser && canRegenerate && (
              <ActionButton
                title={busy ? "Tunggu proses selesai" : "Buat ulang jawaban"}
                disabled={busy}
                onClick={() => onRegenerate?.()}
              >
                <RegenerateIcon />
              </ActionButton>
            )}

            <MessageCapabilityActions
              messageId={messageId}
              conversationId={conversationId}
              sessionId={sessionId}
              role={role}
              hasSelection={Boolean(selection)}
              onInvoke={onCapabilityInvoke}
            />
          </div>
        )}
      </div>
    </div>
  );
}