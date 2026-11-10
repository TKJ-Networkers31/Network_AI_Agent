import React, { useState, useRef, useEffect, useMemo, useCallback } from "react";
import DOMPurify from "dompurify";
import {
  ZoomIn,
  ZoomOut,
  RotateCcw,
  Maximize2,
  Minimize2,
  Download,
  Copy,
  Check,
  Code,
  Eye,
  Info,
  X,
  FileCode,
  Layers,
} from "lucide-react";
import { copyText } from "../utils/clipboard.js";
import { useToast } from "./Toast.jsx";
import { api } from "../api.js";

/**
 * Sanitizes and prepares SVG for safe inline interactive mounting.
 * Strips all script tags, inline event handlers, and external resource exploits.
 */
export function sanitizeSvgForInteractiveDom(rawSvg) {
  if (!rawSvg || typeof rawSvg !== "string") return null;

  // Strict DOMPurify configuration for SVG
  const sanitized = DOMPurify.sanitize(rawSvg, {
    USE_PROFILES: { svg: true, svgFilters: true },
    ADD_TAGS: ["style"],
    FORBID_TAGS: ["script", "iframe", "object", "embed", "foreignObject"],
    FORBID_ATTR: [
      "onload",
      "onclick",
      "onerror",
      "onmouseover",
      "onmouseout",
      "onmousedown",
      "onmouseup",
      "onfocus",
      "onblur",
      "href:javascript",
      "xlink:href",
    ],
  });

  if (!sanitized) return null;

  // Parse to extract viewBox, width, height, and scoped style
  if (typeof DOMParser !== "undefined") {
    try {
      const parser = new DOMParser();
      const doc = parser.parseFromString(sanitized, "image/svg+xml");
      const svg = doc.querySelector("svg");
      if (!svg) return null;

      // Ensure proper viewBox
      if (!svg.getAttribute("viewBox")) {
        const w = parseFloat(svg.getAttribute("width")) || 800;
        const h = parseFloat(svg.getAttribute("height")) || 500;
        svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
      }

      // Ensure width/height responsive styling
      svg.setAttribute("width", "100%");
      svg.setAttribute("height", "100%");

      const viewBox = svg.getAttribute("viewBox");
      const innerHtml = svg.innerHTML;

      return {
        viewBox,
        innerHtml,
        fullXml: new XMLSerializer().serializeToString(svg),
      };
    } catch {
      // Fallback regex extraction
    }
  }

  // Regex fallback
  const viewBoxMatch = sanitized.match(/viewBox=["']([^"']+)["']/i);
  const viewBox = viewBoxMatch ? viewBoxMatch[1] : "0 0 800 500";
  const innerHtmlMatch = sanitized.match(/<svg[^>]*>([\s\S]*?)<\/svg>/i);
  const innerHtml = innerHtmlMatch ? innerHtmlMatch[1] : sanitized;

  return {
    viewBox,
    innerHtml,
    fullXml: sanitized,
  };
}

/**
 * Enterprise Interactive SVG Preview Component
 * Replaces static <img> rendering with a rich, pan/zoom-capable, element-inspectable SVG canvas.
 */
export default function InteractiveSvgPreview({
  code = "",
  title = "Ilustrasi SVG",
  className = "",
}) {
  const { notify } = useToast();
  const [activeTab, setActiveTab] = useState("preview"); // "preview" | "code"
  const [isCopied, setIsCopied] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);

  // Pan & Zoom state
  const [scale, setScale] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const dragStartRef = useRef({ x: 0, y: 0 });
  const viewportRef = useRef(null);

  // Hover & Tooltip state
  const [hoveredInfo, setHoveredInfo] = useState(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });

  // Selected element inspection state
  const [selectedElement, setSelectedElement] = useState(null);

  // Process & sanitize SVG
  const parsedSvg = useMemo(() => {
    return sanitizeSvgForInteractiveDom(code);
  }, [code]);

  // Reset viewport when code changes
  useEffect(() => {
    setScale(1);
    setPan({ x: 0, y: 0 });
    setSelectedElement(null);
    setHoveredInfo(null);
  }, [code]);

  // Pan handlers
  const handleMouseDown = useCallback((e) => {
    // Ignore interactive control clicks
    if (e.target.closest("button") || e.target.closest("[data-no-pan]")) return;
    setIsDragging(true);
    dragStartRef.current = { x: e.clientX - pan.x, y: e.clientY - pan.y };
  }, [pan]);

  const handleMouseMove = useCallback((e) => {
    if (isDragging) {
      setPan({
        x: e.clientX - dragStartRef.current.x,
        y: e.clientY - dragStartRef.current.y,
      });
      return;
    }

    // Interactive element detection for tooltips
    if (!viewportRef.current) return;
    const target = e.target;
    if (target && target.ownerSVGElement) {
      // Find closest named grouping or shape
      const interactiveGroup = target.closest("g[id], [data-label], [id], circle, rect, path");
      if (interactiveGroup && interactiveGroup !== target.ownerSVGElement) {
        const id = interactiveGroup.getAttribute("id") || "";
        const dataLabel = interactiveGroup.getAttribute("data-label") || "";
        const titleEl = interactiveGroup.querySelector("title");
        const descEl = interactiveGroup.querySelector("desc");
        const titleText = titleEl ? titleEl.textContent : dataLabel || id;
        const descText = descEl ? descEl.textContent : "";

        if (titleText || id) {
          const rect = viewportRef.current.getBoundingClientRect();
          setTooltipPos({
            x: e.clientX - rect.left,
            y: e.clientY - rect.top - 12,
          });
          setHoveredInfo({
            title: titleText || id,
            desc: descText,
            id: id,
            tagName: interactiveGroup.tagName.toLowerCase(),
          });
          return;
        }
      }
    }
    setHoveredInfo(null);
  }, [isDragging]);

  const handleMouseUp = useCallback(() => {
    setIsDragging(false);
  }, []);

  // Element click handler (Event delegation via React)
  const handleClick = useCallback((e) => {
    if (!viewportRef.current) return;
    const target = e.target;
    if (target && target.ownerSVGElement) {
      const interactiveGroup = target.closest("g[id], [data-label], [id], circle, rect, path");
      if (interactiveGroup && interactiveGroup !== target.ownerSVGElement) {
        const id = interactiveGroup.getAttribute("id") || "";
        const dataLabel = interactiveGroup.getAttribute("data-label") || "";
        const titleEl = interactiveGroup.querySelector("title");
        const titleText = titleEl ? titleEl.textContent : dataLabel || id || interactiveGroup.tagName;

        setSelectedElement({
          title: titleText,
          id: id || "Anonymous",
          tagName: interactiveGroup.tagName.toLowerCase(),
          className: interactiveGroup.getAttribute("class") || "",
        });
        return;
      }
    }
  }, []);

  // Zoom controls
  const handleZoomIn = () => setScale((s) => Math.min(s * 1.25, 4.0));
  const handleZoomOut = () => setScale((s) => Math.max(s / 1.25, 0.4));
  const handleResetZoom = () => {
    setScale(1);
    setPan({ x: 0, y: 0 });
    setSelectedElement(null);
  };

  // Wheel zoom
  const handleWheel = (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey) {
      e.preventDefault();
      const delta = e.deltaY < 0 ? 1.15 : 0.85;
      setScale((s) => Math.min(Math.max(s * delta, 0.4), 4.0));
    }
  };

  // Actions
  const handleCopyCode = async () => {
    await copyText(code);
    setIsCopied(true);
    notify({ type: "success", message: "Kode SVG berhasil disalin", duration: 2500 });
    setTimeout(() => setIsCopied(false), 2000);
  };

  const handleDownloadSvg = () => {
    if (!parsedSvg) return;
    const blob = new Blob([parsedSvg.fullXml], { type: "image/svg+xml;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `vera-diagram-${Date.now()}.svg`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    notify({ type: "success", message: "File SVG berhasil diunduh", duration: 2500 });
  };

  const handleSaveToWorkspace = async () => {
    if (!parsedSvg) return;
    const filename = `Images/vera-diagram-${Date.now()}.svg`;
    try {
      await api.workspace.write(filename, parsedSvg.fullXml);
      notify({ type: "success", message: `Disimpan ke Workspace: ${filename}`, duration: 3500 });
    } catch (err) {
      notify({ type: "error", message: `Gagal menyimpan: ${err.message || err}` });
    }
  };

  if (!parsedSvg) {
    return (
      <div className="my-3 rounded-2xl border border-white/10 bg-slate-950/80 p-4 font-mono text-xs text-slate-400">
        <div className="flex items-center gap-2 text-amber-400 mb-2">
          <Info size={14} />
          <span className="font-semibold">Kode SVG Tidak Lengkap / Rusak</span>
        </div>
        <pre className="overflow-x-auto p-2 bg-black/40 rounded text-slate-300">{code}</pre>
      </div>
    );
  }

  const containerContent = (
    <div
      className={`relative rounded-2xl border border-slate-800 bg-slate-950/95 overflow-hidden shadow-2xl backdrop-blur-md select-none transition-all ${
        isFullscreen ? "fixed inset-4 z-[999] flex flex-col" : "my-3.5"
      } ${className}`}
      role="region"
      aria-label="SVG Interactive Preview"
    >
      {/* Header Bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 bg-slate-900/80 border-b border-slate-800 shrink-0">
        {/* Left: Mode Tabs & Badge */}
        <div className="flex items-center gap-2">
          {/* Mode Switcher */}
          <div className="flex items-center p-0.5 rounded-xl bg-slate-950 border border-slate-800">
            <button
              type="button"
              onClick={() => setActiveTab("preview")}
              className={`flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold transition ${
                activeTab === "preview"
                  ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              <Eye size={12} />
              <span>SVG Preview</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("code")}
              className={`flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold transition ${
                activeTab === "code"
                  ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              <Code size={12} />
              <span>SVG Code</span>
            </button>
          </div>

          {/* Interactive Badge */}
          {activeTab === "preview" && (
            <span className="hidden sm:inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-[10px] font-mono font-medium text-emerald-400">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 motion-safe:animate-ping" />
              Interactive Canvas
            </span>
          )}
        </div>

        {/* Right: Controls & Actions */}
        <div className="flex items-center gap-1">
          {activeTab === "preview" && (
            <>
              {/* Pan/Zoom Controls */}
              <div className="flex items-center gap-0.5 mr-1 border-r border-slate-800 pr-1.5">
                <button
                  type="button"
                  onClick={handleZoomIn}
                  className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
                  title="Perbesar (Zoom In)"
                  aria-label="Zoom in"
                >
                  <ZoomIn size={14} />
                </button>
                <button
                  type="button"
                  onClick={handleZoomOut}
                  className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
                  title="Perkecil (Zoom Out)"
                  aria-label="Zoom out"
                >
                  <ZoomOut size={14} />
                </button>
                <button
                  type="button"
                  onClick={handleResetZoom}
                  className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition text-[11px] font-mono"
                  title="Reset Tampilan (100%)"
                  aria-label="Reset zoom"
                >
                  <RotateCcw size={12} />
                </button>
                <span className="text-[10px] font-mono text-slate-400 px-1">
                  {Math.round(scale * 100)}%
                </span>
              </div>
            </>
          )}

          {/* Download & Save buttons */}
          <button
            type="button"
            onClick={handleDownloadSvg}
            className="flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium text-slate-300 hover:text-white hover:bg-slate-800 transition"
            title="Unduh File .SVG"
          >
            <Download size={13} className="text-cyan-400" />
            <span className="hidden md:inline">Unduh</span>
          </button>

          <button
            type="button"
            onClick={handleSaveToWorkspace}
            className="hidden sm:flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium text-slate-300 hover:text-white hover:bg-slate-800 transition"
            title="Simpan ke Workspace"
          >
            <Layers size={13} className="text-purple-400" />
            <span>Workspace</span>
          </button>

          <button
            type="button"
            onClick={handleCopyCode}
            className="flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium text-slate-300 hover:text-white hover:bg-slate-800 transition"
            title="Salin Kode SVG"
          >
            {isCopied ? <Check size={13} className="text-emerald-400" /> : <Copy size={13} />}
            <span className="hidden md:inline">{isCopied ? "Tersalin" : "Salin"}</span>
          </button>

          {/* Fullscreen Toggle */}
          <button
            type="button"
            onClick={() => setIsFullscreen((v) => !v)}
            className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition ml-1"
            title={isFullscreen ? "Keluar Fullscreen" : "Perbesar Penuh (Fullscreen)"}
            aria-label="Toggle fullscreen"
          >
            {isFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          </button>
        </div>
      </div>

      {/* Main Body: Interactive Canvas or Source Code */}
      {activeTab === "preview" ? (
        <div
          ref={viewportRef}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          onClick={handleClick}
          onWheel={handleWheel}
          className={`relative overflow-hidden flex items-center justify-center bg-[#030712] ${
            isDragging ? "cursor-grabbing" : "cursor-grab"
          } ${isFullscreen ? "flex-1" : "min-h-[300px] max-h-[520px]"}`}
          style={{
            backgroundImage: "radial-gradient(circle at 1px 1px, rgba(56,189,248,0.08) 1px, transparent 0)",
            backgroundSize: "24px 24px",
          }}
        >
          {/* Transformable Canvas Group */}
          <div
            className="transition-transform duration-75 origin-center will-change-transform w-full h-full flex items-center justify-center p-4 pointer-events-auto"
            style={{
              transform: `translate(${pan.x}px, ${pan.y}px) scale(${scale})`,
            }}
          >
            {/* Real Clean Inline SVG with Event Delegation */}
            <svg
              viewBox={parsedSvg.viewBox}
              className="max-w-full max-h-[460px] object-contain transition-all drop-shadow-md"
              dangerouslySetInnerHTML={{ __html: parsedSvg.innerHtml }}
              style={{
                pointerEvents: "all",
              }}
            />
          </div>

          {/* Hover Tooltip Overlay */}
          {hoveredInfo && !isDragging && (
            <div
              className="absolute pointer-events-none z-30 transform -translate-x-1/2 -translate-y-full px-2.5 py-1.5 rounded-xl bg-slate-950/95 border border-cyan-500/40 shadow-xl backdrop-blur-md text-left transition-all"
              style={{ left: tooltipPos.x, top: tooltipPos.y }}
            >
              <div className="text-xs font-bold text-white flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-cyan-400" />
                <span>{hoveredInfo.title}</span>
              </div>
              {hoveredInfo.desc && (
                <div className="text-[10px] text-slate-300 mt-0.5">{hoveredInfo.desc}</div>
              )}
              {hoveredInfo.id && hoveredInfo.id !== hoveredInfo.title && (
                <div className="text-[9px] font-mono text-cyan-300/80 mt-0.5">#{hoveredInfo.id}</div>
              )}
            </div>
          )}

          {/* Selected Node Details Drawer Pill */}
          {selectedElement && (
            <div className="absolute bottom-3 left-3 right-3 sm:left-auto sm:right-3 sm:w-80 p-3 rounded-xl bg-slate-950/95 border border-cyan-500/50 shadow-2xl backdrop-blur-md z-20 text-xs text-slate-200 animate-in fade-in slide-in-from-bottom-2">
              <div className="flex items-center justify-between pb-1.5 border-b border-slate-800">
                <div className="flex items-center gap-1.5 font-bold text-white">
                  <span className="w-2 h-2 rounded-full bg-cyan-400" />
                  <span className="truncate">{selectedElement.title}</span>
                </div>
                <button
                  onClick={() => setSelectedElement(null)}
                  className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
                >
                  <X size={12} />
                </button>
              </div>
              <div className="mt-2 space-y-1 text-[11px] font-mono">
                <div className="flex justify-between">
                  <span className="text-slate-400">Element Tag:</span>
                  <span className="text-cyan-300">&lt;{selectedElement.tagName}&gt;</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Node ID:</span>
                  <span className="text-slate-200">{selectedElement.id}</span>
                </div>
                {selectedElement.className && (
                  <div className="flex justify-between">
                    <span className="text-slate-400">Classes:</span>
                    <span className="text-slate-300 truncate max-w-[140px]">{selectedElement.className}</span>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Bottom Hint */}
          <div className="absolute bottom-2 left-3 text-[10px] font-mono text-slate-400/80 pointer-events-none select-none">
            Drag untuk geser • Scroll untuk perbesar • Klik elemen untuk inspeksi
          </div>
        </div>
      ) : (
        /* Source Code Tab */
        <div className="relative bg-black/60 border-t border-slate-800 overflow-x-auto p-4 text-xs font-mono">
          <pre className="text-slate-200 leading-relaxed">
            <code>{code}</code>
          </pre>
        </div>
      )}
    </div>
  );

  return containerContent;
}
