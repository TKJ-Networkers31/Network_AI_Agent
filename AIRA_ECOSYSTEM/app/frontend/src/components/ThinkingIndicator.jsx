// AIRA_ECOSYSTEM/app/frontend/src/components/ThinkingIndicator.jsx
import { useEffect, useState } from "react";

const PHASES = [
  "Menganalisis permintaan...",
  "Menyusun rencana...",
  "Memproses...",
];

export default function ThinkingIndicator() {
  const [phaseIndex, setPhaseIndex] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setPhaseIndex((i) => (i + 1) % PHASES.length);
    }, 1800);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="flex items-center gap-2 text-sm text-white/50">
      <span className="flex items-center gap-1">
        <span className="thinking-dot" style={{ animationDelay: "0s" }} />
        <span className="thinking-dot" style={{ animationDelay: "0.15s" }} />
        <span className="thinking-dot" style={{ animationDelay: "0.3s" }} />
      </span>
      <span>{PHASES[phaseIndex]}</span>
    </div>
  );
}