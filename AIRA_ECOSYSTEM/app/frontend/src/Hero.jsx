// app/frontend/src/Hero.jsx
const DEFAULT_PROMPTS = [
  { label: "Cek resource device", icon: "📊" },
  { label: "Apa isi Workspace-ku?", icon: "📁" },
  { label: "Ping ke google.com", icon: "🌐" },
];

const QUICK_START_CARDS = [
  {
    icon: "🔌",
    badge: "Connect",
    title: "AKANE Connection",
    desc: "Sambung ke device via SSH persisten, satu login banyak perintah.",
    prompt: "Sambungkan ke device R1",
  },
  {
    icon: "📡",
    badge: "Monitor",
    title: "Network Monitoring",
    desc: "Cek CPU, memory, traffic interface lewat SNMP real-time.",
    prompt: "Cek resource dan traffic interface R1",
  },
  {
    icon: "🧠",
    badge: "Research",
    title: "Web Research",
    desc: "Cari & rangkum info terkini langsung dari percakapan.",
    prompt: "Cari info terbaru soal RouterOS 7",
  },
];

export default function Hero({ greeting, onQuickPrompt, prompts = DEFAULT_PROMPTS }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center text-center px-4 py-10 min-h-[50vh]">
      <div className="relative w-24 h-24 mb-6">
        <span
          className="absolute inset-0 rounded-pill bg-core-glow blur-xl opacity-70"
          aria-hidden="true"
        />
        <div className="relative w-24 h-24 rounded-pill bg-sakura-gradient shadow-sakura-glow flex items-center justify-center text-3xl">
          🌸
        </div>
      </div>

      <h2 className="text-hero font-semibold text-text-primary max-w-lg">
        {greeting}
      </h2>
      <p className="text-text-secondary text-body mt-2 max-w-md">
        Ketik pertanyaanmu, gunakan <span className="font-mono text-sakura">/</span> untuk
        tool langsung, atau tekan mic untuk sesi suara.
      </p>

      {prompts?.length > 0 && (
        <div className="flex flex-wrap items-center justify-center gap-2 mt-6">
          {prompts.map((p) => (
            <button
              key={p.label}
              onClick={() => onQuickPrompt?.(p.label)}
              className="flex items-center gap-1.5 text-caption px-3.5 py-2 rounded-pill bg-white/[0.05] border border-border text-text-secondary hover:text-text-primary hover:border-sakura/30 transition"
            >
              <span>{p.icon}</span>
              {p.label}
            </button>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-8 w-full max-w-3xl">
        {QUICK_START_CARDS.map((c) => (
          <button
            key={c.title}
            onClick={() => onQuickPrompt?.(c.prompt)}
            className="text-left bg-white/[0.04] hover:bg-white/[0.07] border border-border rounded-card p-4 transition group"
          >
            <div className="flex items-center justify-between mb-2">
              <span className="text-xl">{c.icon}</span>
              <span className="text-[10px] uppercase tracking-wide text-sakura/80 bg-sakura/10 px-2 py-0.5 rounded-pill">
                {c.badge}
              </span>
            </div>
            <div className="text-sm font-semibold text-text-primary group-hover:text-sakura transition">
              {c.title}
            </div>
            <p className="text-caption text-text-secondary mt-1 leading-relaxed">
              {c.desc}
            </p>
          </button>
        ))}
      </div>
    </div>
  );
}