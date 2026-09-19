import { memo, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import DOMPurify from "dompurify";
import CopyButton from "./CopyButton.jsx";
import { copyText } from "../utils/clipboard.js";
import { useToast } from "./Toast.jsx";

// PERUBAHAN (Chat Session: salin bagian penting output):
// - Blok kode (```...```) sekarang punya header dengan tombol "Salin".
// - Kode inline (`perintah`) bisa DIKLIK untuk menyalin isinya - cocok
//   untuk command penting yang di-highlight AI di tengah kalimat.
// - FIX react-markdown v9: prop `inline` pada komponen `code` sudah
//   DIHAPUS di v9, jadi cek `inline` selalu undefined dan kode inline ikut
//   dirender sebagai blok. Sekarang inline/blok dibedakan lewat ada-tidaknya
//   class `language-*` atau newline di isi kode. Pembungkus <pre> bawaan
//   dibuang lewat override `pre` supaya tidak ada <pre><div> bersarang.
//
// PERUBAHAN (Ilustrasi visual - SVG renderer + gambar):
// 1. SVG dirender lewat <img src="data:image/svg+xml,..."> (bukan
//    dangerouslySetInnerHTML). Di konteks <img> SVG terisolasi total:
//    script tidak jalan, <style> di dalam SVG tidak bocor ke CSS aplikasi
//    (sebelumnya bisa merusak tampilan halaman), dan tidak ada request
//    eksternal. DOMPurify tetap dipakai sebagai lapis pertama, lalu hasilnya
//    diserialisasi ulang sebagai XML valid (xmlns otomatis ditambahkan -
//    LLM sering lupa xmlns, dan tanpa itu <img> gagal memuat SVG).
// 2. viewBox dinormalisasi & ukuran responsif (lebar 100%, batas maksimum
//    dari viewBox) - SVG tanpa width/height tidak lagi tampil 300x150.
// 3. Latar kartu SVG selalu terang: LLM menulis diagram untuk latar putih
//    (teks hitam), di UI gelap jadi tak terbaca tanpa ini.
// 4. Deteksi SVG tidak lagi hanya dari ```svg - juga ```xml/```html/tanpa
//    bahasa yang isinya <svg>...</svg> utuh. SVG rusak/terpotong jatuh ke
//    blok kode biasa dengan catatan, bukan render kosong.
// 5. Aksi: perbesar (klik), lihat kode, unduh .svg, salin kode.
// 6. Markdown gambar ![alt](url) (hasil tool web_image_search) dirender
//    sebagai galeri kecil: lazy-load, klik untuk perbesar, fallback link
//    kalau gambar gagal dimuat (hotlink diblokir / URL kedaluwarsa).

const SVG_LANGS = new Set(["svg", "xml", "html"]);
const SVG_START_RE = /^\s*(?:<\?xml[^>]*\?>\s*)?(?:<!--[\s\S]*?-->\s*)*<svg[\s>]/i;
const SVG_END_RE = /<\/svg>\s*$/i;
const DEFAULT_VIEWBOX = "0 0 720 405";

function looksLikeSvg(raw) {
  return SVG_START_RE.test(raw) && SVG_END_RE.test(raw);
}

// Sanitasi -> normalisasi viewBox -> serialisasi XML valid -> data URI.
// Return null kalau bukan SVG yang bisa dipakai.
function buildSvg(code) {
  const clean = DOMPurify.sanitize(code, {
    USE_PROFILES: { svg: true, svgFilters: true },
    ADD_TAGS: ["style"], // aman: dirender di <img>, terisolasi
  });

  const host = document.createElement("div");
  host.innerHTML = clean;

  const svg = host.querySelector("svg");
  if (!svg) return null;

  if (!svg.getAttribute("viewBox")) {
    const w = parseFloat(svg.getAttribute("width"));
    const h = parseFloat(svg.getAttribute("height"));
    svg.setAttribute("viewBox", w > 0 && h > 0 ? `0 0 ${w} ${h}` : DEFAULT_VIEWBOX);
  }

  const viewBoxWidth = parseFloat(svg.getAttribute("viewBox").split(/[\s,]+/)[2]) || 720;

  // Ukuran diatur CSS (responsif), bukan atribut tetap dari LLM.
  svg.removeAttribute("width");
  svg.removeAttribute("height");

  const xml = new XMLSerializer().serializeToString(svg);

  return {
    xml,
    uri: `data:image/svg+xml;charset=utf-8,${encodeURIComponent(xml)}`,
    maxWidth: Math.min(Math.max(viewBoxWidth, 320), 880),
  };
}

function downloadSvg(xml) {
  const blob = new Blob([xml], { type: "image/svg+xml" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "aira-ilustrasi.svg";
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

const HEADER_BUTTON =
  "inline-flex items-center rounded-pill px-2 py-1 text-[11px] text-white/40 hover:text-white hover:bg-white/10 transition";

// Overlay layar penuh via portal (lolos dari overflow/transform leluhur).
function ZoomOverlay({ children, onClose }) {
  useEffect(() => {
    function onKey(e) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return createPortal(
    <div
      role="dialog"
      aria-modal="true"
      onClick={onClose}
      className="fixed inset-0 z-[120] flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 cursor-zoom-out"
    >
      {children}
    </div>,
    document.body
  );
}

function SvgBlock({ code }) {
  const built = useMemo(() => {
    try {
      return buildSvg(code);
    } catch {
      return null;
    }
  }, [code]);

  const [showCode, setShowCode] = useState(false);
  const [zoom, setZoom] = useState(false);
  const [broken, setBroken] = useState(false);

  if (!built || broken) {
    return (
      <BlockCode
        lang="svg"
        raw={code}
        note="SVG tidak valid - ditampilkan sebagai kode"
      />
    );
  }

  return (
    <div className="my-3 rounded-xl2 border border-border overflow-hidden">
      <div className="flex items-center justify-between pl-3 pr-1.5 py-1 bg-white/5 border-b border-border">
        <span className="text-[10px] uppercase tracking-wide text-white/40">ilustrasi</span>
        <div className="flex items-center gap-0.5">
          <button type="button" onClick={() => setShowCode((v) => !v)} className={HEADER_BUTTON}>
            {showCode ? "Sembunyikan kode" : "Kode"}
          </button>
          <button type="button" onClick={() => downloadSvg(built.xml)} className={HEADER_BUTTON}>
            Unduh
          </button>
          <CopyButton text={code} label="Salin" title="Salin kode SVG" />
        </div>
      </div>

      <div className="bg-[#F8FAFC] p-3 flex justify-center">
        <img
          src={built.uri}
          alt="Ilustrasi SVG"
          draggable={false}
          onError={() => setBroken(true)}
          onClick={() => setZoom(true)}
          className="w-full h-auto cursor-zoom-in select-none"
          style={{ maxWidth: built.maxWidth }}
        />
      </div>

      {showCode && (
        <pre className="overflow-x-auto p-3 text-[13px] leading-relaxed bg-black/30 border-t border-border">
          <code className="font-mono text-white/85">{code}</code>
        </pre>
      )}

      {zoom && (
        <ZoomOverlay onClose={() => setZoom(false)}>
          <img
            src={built.uri}
            alt="Ilustrasi SVG (diperbesar)"
            className="h-auto max-h-[88vh] bg-[#F8FAFC] rounded-xl2 p-3"
            style={{ width: "min(92vw, 1100px)" }}
          />
        </ZoomOverlay>
      )}
    </div>
  );
}

// Gambar dari Markdown ![alt](url) - terutama hasil tool web_image_search.
// Dirender dengan <span> (bukan <figure>/<div>) karena react-markdown
// membungkus gambar di dalam <p>.
function MarkdownImage({ src, alt }) {
  const [failed, setFailed] = useState(false);
  const [zoom, setZoom] = useState(false);

  if (!src) return null;

  if (failed) {
    return (
      <a
        href={src}
        target="_blank"
        rel="noreferrer"
        className="inline-flex items-center gap-1.5 mr-2 mb-2 px-2.5 py-1 rounded-pill bg-white/5 border border-border text-xs text-white/60 hover:text-white transition"
      >
        <span>🖼</span>
        <span className="truncate max-w-[16rem]">{alt || "Buka gambar"}</span>
      </a>
    );
  }

  return (
    <>
      <span className="inline-block align-top mr-2 mb-2 max-w-full">
        <img
          src={src}
          alt={alt || ""}
          loading="lazy"
          referrerPolicy="no-referrer"
          onError={() => setFailed(true)}
          onClick={(e) => {
            e.preventDefault();
            setZoom(true);
          }}
          className="block h-44 sm:h-52 w-auto min-w-[7rem] max-w-full rounded-xl2 border border-border object-cover bg-white/5 cursor-zoom-in"
        />
        {alt && (
          <span className="block w-0 min-w-full truncate text-[11px] text-white/40 mt-1">
            {alt}
          </span>
        )}
      </span>

      {zoom && (
        <ZoomOverlay onClose={() => setZoom(false)}>
          <img
            src={src}
            alt={alt || ""}
            referrerPolicy="no-referrer"
            className="max-w-[92vw] max-h-[88vh] w-auto h-auto rounded-xl2"
          />
        </ZoomOverlay>
      )}
    </>
  );
}

function InlineCode({ children }) {
  const [copied, setCopied] = useState(false);
  const timerRef = useRef(null);
  const { notify } = useToast();

  useEffect(() => () => clearTimeout(timerRef.current), []);

  async function handleCopy() {
    // Kalau user sedang menyeleksi teks (drag), jangan timpa clipboard-nya.
    if (window.getSelection?.()?.toString()) return;

    const ok = await copyText(String(children));

    if (!ok) {
      notify({ type: "error", message: "Gagal menyalin ke clipboard.", duration: 2500 });
      return;
    }

    setCopied(true);
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setCopied(false), 1200);
  }

  return (
    <code
      role="button"
      tabIndex={0}
      title="Klik untuk menyalin"
      onClick={handleCopy}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          handleCopy();
        }
      }}
      className={`rounded px-1.5 py-0.5 text-[0.85em] font-mono cursor-pointer transition break-words
        ${
          copied
            ? "bg-emerald-500/15 text-emerald-300"
            : "bg-white/10 text-accent-light hover:bg-accent/20"
        }`}
    >
      {children}
      {copied && <span className="ml-1">✓</span>}
    </code>
  );
}

function BlockCode({ lang, raw, note }) {
  return (
    <div className="my-3 rounded-xl2 border border-border overflow-hidden">
      <div className="flex items-center justify-between pl-3 pr-1.5 py-1 bg-white/5 border-b border-border">
        <span className="text-[10px] uppercase tracking-wide text-white/40">
          {lang || "kode"}
          {note && <span className="ml-2 normal-case tracking-normal text-amber-300/80">{note}</span>}
        </span>
        <CopyButton text={raw} label="Salin" title="Salin seluruh blok" />
      </div>
      <pre className="overflow-x-auto p-3 text-[13px] leading-relaxed bg-black/30">
        <code className="font-mono text-white/85">{raw}</code>
      </pre>
    </div>
  );
}

function CodeBlock({ className, children }) {
  const match = /language-(\w+)/.exec(className || "");
  const lang = match?.[1]?.toLowerCase();
  const text = String(children);

  // react-markdown v9: blok berpagar selalu berakhiran "\n" atau punya
  // class language-*; kode inline tidak punya keduanya.
  const isBlock = Boolean(lang) || text.includes("\n");

  if (!isBlock) {
    return <InlineCode>{children}</InlineCode>;
  }

  const raw = text.replace(/\n$/, "");

  // SVG: ```svg, atau ```xml/```html/tanpa bahasa yang isinya <svg>...</svg> utuh.
  const svgCandidate = !lang || SVG_LANGS.has(lang);

  if (svgCandidate && looksLikeSvg(raw)) {
    return <SvgBlock code={raw} />;
  }

  if (lang === "svg") {
    return <BlockCode lang="svg" raw={raw} note="SVG tidak lengkap - ditampilkan sebagai kode" />;
  }

  return <BlockCode lang={lang} raw={raw} />;
}

const components = {
  h1: ({ children }) => (
    <h1 className="text-lg font-bold text-white mt-4 mb-2 first:mt-0">{children}</h1>
  ),
  h2: ({ children }) => (
    <h2 className="text-base font-bold text-white mt-4 mb-2 first:mt-0">{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 className="text-sm font-semibold text-white/90 mt-3 mb-1.5 first:mt-0">{children}</h3>
  ),
  p: ({ children }) => (
    <p className="text-sm leading-relaxed text-white/90 mb-2.5 last:mb-0">{children}</p>
  ),
  strong: ({ children }) => <strong className="font-semibold text-white">{children}</strong>,
  em: ({ children }) => <em className="italic text-white/80">{children}</em>,
  a: ({ children, href }) => (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="text-accent-light underline decoration-accent-light/30 hover:decoration-accent-light"
    >
      {children}
    </a>
  ),
  img: MarkdownImage,
  ul: ({ children }) => (
    <ul className="list-disc pl-5 space-y-1 text-sm text-white/90 mb-2.5">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="list-decimal pl-5 space-y-1 text-sm text-white/90 mb-2.5">{children}</ol>
  ),
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  // Garis pemisah antar topik (---) di markdown
  hr: () => <hr className="my-4 border-t border-border" />,
  blockquote: ({ children }) => (
    <blockquote className="border-l-2 border-accent/50 pl-3 my-2.5 text-sm text-white/60 italic">
      {children}
    </blockquote>
  ),
  table: ({ children }) => (
    <div className="my-3 overflow-x-auto rounded-xl2 border border-border">
      <table className="w-full text-sm border-collapse">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-white/5">{children}</thead>,
  tbody: ({ children }) => <tbody>{children}</tbody>,
  tr: ({ children }) => (
    <tr className="border-b border-border last:border-b-0">{children}</tr>
  ),
  th: ({ children }) => (
    <th className="text-left font-semibold text-white/80 px-3 py-2 whitespace-nowrap">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="px-3 py-2 text-white/80 align-top">{children}</td>
  ),
  // Buang <pre> bawaan react-markdown - BlockCode/SvgBlock sudah punya wadah sendiri.
  pre: ({ children }) => <>{children}</>,
  code: CodeBlock,
};

function Markdown({ content }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
      {content || ""}
    </ReactMarkdown>
  );
}

export default memo(Markdown);