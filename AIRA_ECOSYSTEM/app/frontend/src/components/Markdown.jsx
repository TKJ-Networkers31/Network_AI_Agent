import { memo, useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import DOMPurify from "dompurify";

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

function CodeBlock({ inline, className, children, ...props }) {
  const match = /language-(\w+)/.exec(className || "");
  const lang = match?.[1];
  const raw = String(children).replace(/\n$/, "");

  if (!inline && lang === "svg") {
    return <SvgBlock code={raw} />;
  }

  if (inline) {
    return (
      <code
        className="bg-white/10 text-accent-light rounded px-1.5 py-0.5 text-[0.85em] font-mono"
        {...props}
      >
        {children}
      </code>
    );
  }

  return (
    <div className="my-3 rounded-xl2 border border-border overflow-hidden">
      {lang && (
        <div className="px-3 py-1.5 text-[10px] uppercase tracking-wide text-white/40 bg-white/5 border-b border-border">
          {lang}
        </div>
      )}
      <pre className="overflow-x-auto p-3 text-[13px] leading-relaxed bg-black/30">
        <code className="font-mono text-white/85">{raw}</code>
      </pre>
    </div>
  );
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