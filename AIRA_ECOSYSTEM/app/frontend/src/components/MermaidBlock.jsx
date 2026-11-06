import { useState } from "react";
import { GitBranch, Copy, Check } from "lucide-react";
import { copyText } from "../utils/clipboard.js";
import { useToast } from "./Toast.jsx";

export default function MermaidBlock({ code }) {
  const { showToast } = useToast();
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    const ok = await copyText(code);
    if (ok) {
      setCopied(true);
      showToast("Diagram Mermaid berhasil disalin", "success");
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="my-3 rounded-xl border border-white/10 bg-[#0c1220] p-3 shadow-lg">
      <div className="flex items-center justify-between pb-2 border-b border-white/5">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-cyan-400">
          <GitBranch className="h-3.5 w-3.5" />
          <span>Diagram Mermaid (Architecture / Flow)</span>
        </div>
        <button
          type="button"
          onClick={handleCopy}
          className="inline-flex items-center gap-1 text-[11px] text-white/60 hover:text-white transition"
        >
          {copied ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
          <span>{copied ? "Tersalin" : "Salin Diagram"}</span>
        </button>
      </div>

      <div className="mt-2.5 rounded-lg bg-black/50 p-3 font-mono text-[11px] text-white/80 overflow-x-auto whitespace-pre leading-relaxed border border-white/5">
        <code>{code.trim()}</code>
      </div>
    </div>
  );
}
