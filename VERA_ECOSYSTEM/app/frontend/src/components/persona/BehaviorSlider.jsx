import { useEffect, useState } from "react";

export default function BehaviorSlider({ label, value, lowLabel, highLabel, onChange, onCommit }) {
  const [local, setLocal] = useState(value);

  useEffect(() => {
    setLocal(value);
  }, [value]);

  function handleInput(e) {
    const v = Number(e.target.value);
    setLocal(v);
    onChange?.(v);
  }

  function handleCommit() {
    onCommit?.(local);
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="text-sm font-medium text-white/80">{label}</span>
        <span className="text-xs text-accent-light font-mono">{local}</span>
      </div>

      <input
        type="range"
        min={0}
        max={100}
        value={local}
        onChange={handleInput}
        onMouseUp={handleCommit}
        onTouchEnd={handleCommit}
        className="w-full accent-accent"
      />

      <div className="flex items-center justify-between text-[10px] text-white/30 mt-1">
        <span>{lowLabel}</span>
        <span>{highLabel}</span>
      </div>
    </div>
  );
}