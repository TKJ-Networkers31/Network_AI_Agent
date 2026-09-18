import { memo, useEffect, useMemo, useRef, useState } from "react";
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

// Blok kode ```svg ...``` dirender langsung jadi gambar, bukan teks
// mentah - cocok kalau AIRA butuh menjelaskan sesuatu dengan ilustrasi
// (mis. diagram topologi jaringan sederhana). Disanitasi via DOMPurify
// sebelum masuk ke dangerouslySetInnerHTML supaya tidak ada celah XSS
// walau isinya datang dari output model.
function SvgBlock({ code }) {
  const clean = useMemo(
    () =>
      DOMPurify.sanitize(code, {
        USE_PROFILES: { svg: true, svgFilters: true },
      }),
    [code]
  );

  return (
    <div
      className="my-3 flex justify-center bg-white/5 border border-border rounded-xl2 p-4 overflow-x-auto"
      dangerouslySetInnerHTML={{ __html: clean }}
    />
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

function BlockCode({ lang, raw }) {
  return (
    <div className="my-3 rounded-xl2 border border-border overflow-hidden">
      <div className="flex items-center justify-between pl-3 pr-1.5 py-1 bg-white/5 border-b border-border">
        <span className="text-[10px] uppercase tracking-wide text-white/40">{lang || "kode"}</span>
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
  const lang = match?.[1];
  const text = String(children);

  // react-markdown v9: blok berpagar selalu berakhiran "\n" atau punya
  // class language-*; kode inline tidak punya keduanya.
  const isBlock = Boolean(lang) || text.includes("\n");

  if (!isBlock) {
    return <InlineCode>{children}</InlineCode>;
  }

  const raw = text.replace(/\n$/, "");

  if (lang === "svg") {
    return <SvgBlock code={raw} />;
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
  // Buang <pre> bawaan react-markdown - BlockCode sudah punya <pre> sendiri.
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