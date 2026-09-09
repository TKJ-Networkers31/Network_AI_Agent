export default function VoiceControls({
  supported,
  listening,
  speaking,
  speakEnabled,
  onToggleListen,
  onToggleSpeak,
}) {
  return (
    <div className="flex items-center gap-1.5 shrink-0">
      <button
        type="button"
        onClick={onToggleListen}
        disabled={!supported}
        title={
          supported
            ? listening
              ? "Berhenti mendengarkan"
              : "Bicara ke agent"
            : "Browser ini tidak mendukung pengenalan suara"
        }
        aria-pressed={listening}
        className={`relative w-10 h-10 flex items-center justify-center rounded-full border transition
          ${
            listening
              ? "bg-red-500/15 border-red-400/50 text-red-300"
              : "bg-white/5 border-border text-white/60 hover:text-white hover:border-accent/40"
          }
          disabled:opacity-30 disabled:cursor-not-allowed`}
      >
        {listening && (
          <span className="mic-pulse absolute inset-0 rounded-full bg-red-400/40" />
        )}
        <svg
          viewBox="0 0 24 24"
          fill="none"
          className="relative w-4.5 h-4.5"
          style={{ width: 18, height: 18 }}
        >
          <path
            d="M12 15a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3Z"
            stroke="currentColor"
            strokeWidth="1.6"
          />
          <path
            d="M19 11a7 7 0 0 1-14 0M12 18v3"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
          />
        </svg>
      </button>

      <button
        type="button"
        onClick={onToggleSpeak}
        title={speakEnabled ? "Matikan mode bicara" : "Bacakan jawaban agent"}
        aria-pressed={speakEnabled}
        className={`relative w-10 h-10 flex items-center justify-center rounded-full border transition
          ${
            speakEnabled
              ? "bg-accent/15 border-accent/50 text-accent-light"
              : "bg-white/5 border-border text-white/60 hover:text-white hover:border-accent/40"
          }`}
      >
        {speaking && (
          <span className="mic-pulse absolute inset-0 rounded-full bg-accent/40" />
        )}
        <svg
          viewBox="0 0 24 24"
          fill="none"
          className="relative"
          style={{ width: 18, height: 18 }}
        >
          <path
            d="M4 9v6h4l5 4V5L8 9H4Z"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinejoin="round"
          />
          {speakEnabled && (
            <path
              d="M17 8.5a5 5 0 0 1 0 7M19.5 6a8.5 8.5 0 0 1 0 12"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
            />
          )}
          {!speakEnabled && (
            <path
              d="m17.5 8.5 4 4m0-4-4 4"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
            />
          )}
        </svg>
      </button>
    </div>
  );
}
