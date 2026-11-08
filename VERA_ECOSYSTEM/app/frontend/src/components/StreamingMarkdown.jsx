// src/components/StreamingMarkdown.jsx
import { memo, useRef } from "react";
import Markdown from "./Markdown.jsx";
import { IncrementalResponseParser } from "../utils/streamParser.js";

const Block = memo(function Block({ source }) {
  return (
    <div className="mb-2.5 last:mb-0">
      <Markdown content={source} />
    </div>
  );
});

const PENDING_LABEL = {
  svg: "Menyiapkan ilustrasi…",
  graph: "Menyiapkan diagram…",
};

export default function StreamingMarkdown({ content, streaming }) {
  const parserRef = useRef(null);
  if (parserRef.current === null) parserRef.current = new IncrementalResponseParser();

  // sync() idempoten untuk teks yang sama (aman untuk StrictMode / re-render).
  const snap = parserRef.current.sync(content || "", { final: !streaming });

  return (
    <div>
      {snap.blocks.map((b) => (
        <Block key={`b-${b.index}`} source={b.source} />
      ))}

      {/* key tail = index blok berikutnya, jadi saat di-commit tidak remount */}
      {snap.tail && <Block key={`b-${snap.tail.index}`} source={snap.tail.source} />}

      {snap.pending && (
        <div className="text-xs text-white/40 italic animate-pulse">
          {PENDING_LABEL[snap.pending.kind] || "Menyiapkan…"}
        </div>
      )}
    </div>
  );
}