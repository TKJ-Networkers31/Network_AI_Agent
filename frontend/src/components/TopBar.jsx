import { useEffect, useState } from "react";

function greeting(hour) {
  if (hour < 5) return "Good night!";
  if (hour < 11) return "Good morning!";
  if (hour < 15) return "Good afternoon!";
  if (hour < 19) return "Good evening!";
  return "Good night!";
}

export default function TopBar({ title, subtitle }) {
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000 * 15);
    return () => clearInterval(timer);
  }, []);

  const hh = String(now.getHours()).padStart(2, "0");
  const mm = String(now.getMinutes()).padStart(2, "0");

  return (
    <div className="rounded-xl2 bg-hero-gradient border border-border p-6 mb-6 flex items-center justify-between overflow-hidden relative">
      <div>
        <h1 className="text-2xl font-bold text-white">{title}</h1>
        {subtitle && (
          <p className="text-white/50 text-sm mt-1">{subtitle}</p>
        )}
      </div>
      <div className="text-right">
        <div className="text-4xl font-extrabold tracking-tight text-white">
          {hh}:{mm}
        </div>
        <div className="text-white/50 text-sm mt-1">
          {greeting(now.getHours())}
        </div>
      </div>
    </div>
  );
}
