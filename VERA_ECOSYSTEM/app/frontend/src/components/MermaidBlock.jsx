import { useMemo, useState } from "react";
import { GitBranch, Copy, Check, Code2, Eye } from "lucide-react";
import { copyText } from "../utils/clipboard.js";
import { useToast } from "./Toast.jsx";
import { generateMermaidSvg } from "../platform/adaptive-experience/renderer/mermaidParser.js";

export default function MermaidBlock({ code }) {
  const { showToast } = useToast();
  const [copied, setCopied] = useState(false);
  const [viewMode, setViewMode] = useState("diagram"); // 'diagram' | 'code'

  const parsedResult = useMemo(() => {
    try {
      return generateMermaidSvg(code);
    } catch {
      return { success: false };
    }
  }, [code]);

  const handleCopy = async () => {
    const ok = await copyText(code);
    if (ok) {
      setCopied(true);
      showToast("Diagram Mermaid berhasil disalin", "success");
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const isVisualAvailable = parsedResult.success && parsedResult.nodeCount > 0;

  return (
    <div className="my-3 rounded-xl border border-white/10 bg-[#04060c] p-3 shadow-lg">
      <div className="flex items-center justify-between pb-2 border-b border-white/5">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-cyan-400">
          <GitBranch className="h-3.5 w-3.5" />
          <span>VERA Flow Architecture</span>
          {isVisualAvailable && (
            <span className="text-[10px] font-normal text-white/40">
              ({parsedResult.nodeCount} nodes, {parsedResult.edgeCount} edges)
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {isVisualAvailable && (
            <button
              type="button"
              onClick={() => setViewMode(viewMode === "diagram" ? "code" : "diagram")}
              className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] bg-white/5 text-white/70 hover:text-white hover:bg-white/10 transition"
            >
              {viewMode === "diagram" ? (
                <>
                  <Code2 className="h-3 w-3" />
                  <span>Lihat Syntax</span>
                </>
              ) : (
                <>
                  <Eye className="h-3 w-3" />
                  <span>Lihat Diagram</span>
                </>
              )}
            </button>
          )}

          <button
            type="button"
            onClick={handleCopy}
            className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] text-white/60 hover:text-white hover:bg-white/5 transition"
          >
            {copied ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
            <span>{copied ? "Tersalin" : "Salin"}</span>
          </button>
        </div>
      </div>

      {isVisualAvailable && viewMode === "diagram" ? (
        <div className="mt-2.5 overflow-x-auto rounded-lg bg-[#050B14] p-4 flex justify-center border border-white/5">
          <div
            className="w-full max-w-full flex justify-center"
            dangerouslySetInnerHTML={{ __html: parsedResult.svg }}
          />
        </div>
      ) : (
        <div className="mt-2.5 rounded-lg bg-black/50 p-3 font-mono text-[11px] text-white/80 overflow-x-auto whitespace-pre leading-relaxed border border-white/5">
          <code>{code.trim()}</code>
        </div>
      )}
    </div>
  );
}
