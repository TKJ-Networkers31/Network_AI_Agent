export default function VoiceOverlay({ interimText, onCancel }) {
  return (
    <div className="fixed inset-0 z-[90] flex flex-col items-center justify-center bg-app/90 backdrop-blur-sm px-6">
      <div className="relative w-40 h-40 flex items-center justify-center mb-8">
        <span className="orb-ring absolute inset-0 rounded-full border-2 border-accent-light/50" />
        <span
          className="orb-ring absolute inset-0 rounded-full border-2 border-accent-light/50"
          style={{ animationDelay: "0.6s" }}
        />
        <span
          className="orb-ring absolute inset-0 rounded-full border-2 border-accent-light/50"
          style={{ animationDelay: "1.2s" }}
        />

        <div className="relative w-24 h-24 rounded-full bg-accent-gradient shadow-2xl shadow-accent/40 flex items-center justify-center gap-1.5">
          {[0, 1, 2, 3, 4].map((i) => (
            <span
              key={i}
              className="eq-bar w-1.5 rounded-full bg-white/90"
              style={{
                height: 22,
                animationDelay: `${i * 0.12}s`,
                animationDuration: `${0.7 + (i % 3) * 0.15}s`,
              }}
            />
          ))}
        </div>
      </div>

      <p className="text-white font-medium mb-2">Mendengarkan...</p>
      <p className="text-white/40 text-sm max-w-xs text-center min-h-[1.5rem]">
        {interimText || "Silakan bicara — agent membalas otomatis setelah kamu selesai."}
      </p>

      <button
        onClick={onCancel}
        className="mt-8 px-5 py-2.5 rounded-full border border-border text-white/60 hover:text-white hover:border-red-400/40 text-sm transition"
      >
        Batalkan
      </button>
    </div>
  );
}
