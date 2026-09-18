// app/frontend/src/components/Hero.jsx — NEW component.
// Empty-state centerpiece for ChatPage, replacing the old
// "greeting rendered as a MessageBubble" approach. Purely additive:
// no new backend calls. `greeting` still comes from
// utils/greeting.js::buildGreeting(persona) exactly as before.
//
// quickPrompts are canned prompt starters that call the EXISTING
// onSend(text) handler already passed down from ChatPage — not a new
// feature, just pre-filled text for the same composer action.

const DEFAULT_PROMPTS = [
  "Cek resource semua device",
  "Apa yang ada di Workspace-ku?",
  "Ping ke google.com",
];

export default function Hero({ greeting, onQuickPrompt, prompts = DEFAULT_PROMPTS }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center text-center px-4 py-10 min-h-[50vh]">
      <div className="relative w-24 h-24 mb-6">
        <span className="absolute inset-0 rounded-pill bg-core-glow blur-xl opacity-70" aria-hidden="true" />
        <div className="relative w-24 h-24 rounded-pill bg-sakura-gradient shadow-sakura-glow flex items-center justify-center text-3xl">
          🌸
        </div>
      </div>

      <h2 className="text-hero font-semibold text-text-primary max-w-lg">{greeting}</h2>
      <p className="text-text-secondary text-body mt-2 max-w-md">
        Ketik pertanyaanmu, gunakan <span className="font-mono text-sakura">/</span> untuk tool
        langsung, atau tekan mic untuk sesi suara.
      </p>

      {prompts?.length > 0 && (
        <div className="flex flex-wrap items-center justify-center gap-2 mt-6">
          {prompts.map((p) => (
            <button
              key={p}
              onClick={() => onQuickPrompt?.(p)}
              className="text-caption px-3.5 py-2 rounded-pill bg-white/[0.05] border border-border text-text-secondary hover:text-text-primary hover:border-sakura/30 transition"
            >
              {p}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
