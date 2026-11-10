import React, { useState } from "react";
import { X, ExternalLink, Download, Maximize2, Minimize2, Sparkles, Eye } from "lucide-react";

/**
 * ArtifactViewerModal
 * Standalone modal for viewing interactive HTML/visualization artifacts in a sandboxed iframe.
 */
export default function ArtifactViewerModal({
  isOpen,
  onClose,
  artifactUrl,
  artifactTitle = "Interactive Visualization Artifact",
  downloadUrl,
}) {
  const [isFullscreen, setIsFullscreen] = useState(false);

  if (!isOpen || !artifactUrl) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-in fade-in duration-200"
      onClick={onClose}
    >
      <div
        className={`bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl flex flex-col overflow-hidden transition-all duration-300 ${
          isFullscreen ? "w-full h-full rounded-none" : "w-11/12 max-w-6xl h-[85vh]"
        }`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-950/80">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-400">
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-semibold text-white tracking-wide flex items-center gap-2">
                {artifactTitle}
                <span className="text-xs px-2 py-0.5 rounded-full bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 font-mono">
                  Interactive HTML Artifact
                </span>
              </h3>
              <p className="text-xs text-slate-400 mt-0.5">
                VERA Standalone Dynamic Canvas • Click nodes, drag & drop, zoom/pan, export SVG/PNG
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Open in New Tab */}
            <a
              href={artifactUrl}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-300 bg-slate-800/80 hover:bg-slate-700 hover:text-white border border-slate-700/60 transition-colors"
              title="Open full artifact in new tab"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              <span>Tab Baru</span>
            </a>

            {/* Direct Download */}
            {downloadUrl && (
              <a
                href={downloadUrl}
                download
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-300 bg-slate-800/80 hover:bg-slate-700 hover:text-white border border-slate-700/60 transition-colors"
                title="Download HTML file"
              >
                <Download className="w-3.5 h-3.5" />
                <span>Unduh</span>
              </a>
            )}

            {/* Fullscreen Toggle */}
            <button
              onClick={() => setIsFullscreen(!isFullscreen)}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
              title={isFullscreen ? "Exit Fullscreen" : "Fullscreen"}
            >
              {isFullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
            </button>

            {/* Close Button */}
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-red-400 hover:bg-slate-800 transition-colors ml-1"
              title="Close modal"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Modal Iframe Content */}
        <div className="flex-1 bg-slate-950 relative">
          <iframe
            src={artifactUrl}
            title={artifactTitle}
            className="w-full h-full border-none"
            sandbox="allow-scripts allow-same-origin allow-downloads"
          />
        </div>
      </div>
    </div>
  );
}
