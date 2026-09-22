/**
 * utils/streamParser.js — IncrementalResponseParser (Sprint 2.5 / Worker 3).
 *
 * Mengubah teks jawaban yang tumbuh chunk demi chunk (`stream_delta.text`)
 * menjadi struktur yang aman dirender SECARA BERTAHAP oleh renderer Markdown
 * yang SUDAH ADA (components/Markdown.jsx). Parser ini TIDAK merender apa pun
 * dan TIDAK menggantikan pipeline SVG / graph / gambar / DIO - ia hanya
 * memutuskan KAPAN sebuah potongan teks boleh diserahkan ke renderer itu.
 *
 *   text (append-only)  ->  parser (buffer + state antar chunk)  ->  snapshot
 *
 *   snapshot = {
 *     blocks:   [{ index, kind, lang, source }]  // SUDAH final, tidak akan berubah lagi
 *     tail:     { index, source } | null         // bagian yang masih tumbuh (aman dirender)
 *     pending:  { kind, lines } | null           // blok yang DITAHAN sampai lengkap
 *     complete: boolean                          // finish() sudah dipanggil
 *   }
 *
 * Jaminan:
 *   1. Deterministik & tidak bergantung pada batas chunk: teks yang sama, dipotong
 *      di mana pun (di tengah kata, kalimat, paragraf, sintaks Markdown, code fence,
 *      payload SVG/gambar), menghasilkan snapshot akhir yang SAMA setelah finish().
 *   2. Keputusan struktural hanya diambil dari BARIS LENGKAP. Baris yang belum
 *      selesai (partial) ikut tampil sebagai teks progresif di `tail`, kecuali
 *      kalau ia terlihat seperti awal sintaks yang belum bisa ditafsirkan
 *      (pagar kode ```, "![alt](url" yang belum tertutup) - itu disembunyikan.
 *   3. Blok yang sudah masuk `blocks` tidak pernah berubah (aman di-memoize).
 *   4. Blok SVG dan graph (JSON nodes/edges) DITAHAN (`pending`) sampai pagar
 *      penutupnya tiba, sehingga renderer tidak pernah melihat SVG/graph
 *      terpotong. Kode biasa tetap tampil progresif.
 *   5. Pemisahan blok hanya di batas yang aman (baris kosong yang diikuti awal
 *      paragraf baru). Daftar berurutan, blockquote, definisi referensi, dan
 *      isi berindentasi TIDAK dipisah, supaya penomoran/pengelompokan sama
 *      dengan render satu-dokumen.
 *
 * DIO: kontrak backend TIDAK mengirim blok DIO di dalam teks stream
 * (`interaction_schema` hanya datang pada event `response`), jadi parser ini
 * tidak mengenal sintaks DIO. Form DIO tetap dirender oleh <Renderer> yang ada
 * lewat MessageBubble begitu `response` tiba.
 *
 * Modul ini MURNI (tanpa React/DOM/fetch) sehingga bisa diuji dengan `node --test`.
 */

export const BLOCK_KIND = Object.freeze({
  TEXT: "text",
  CODE: "code",
  SVG: "svg",
  GRAPH: "graph",
});

const FENCE_LINE_RE = /^(\s*)(`{3,}|~{3,})(.*)$/;
const FENCE_CLOSE_RE = /^\s*(`{3,}|~{3,})\s*$/;
const FENCE_PARTIAL_RE = /^\s*[`~]+\s*$/;
const LIST_MARKER_RE = /^\s*(?:[-*+]|\d{1,9}[.)])(?:\s|$)/;
const QUOTE_RE = /^\s{0,3}>/;
const REF_DEF_RE = /^\s{0,3}\[\^?[^\]]+\]:/;
const SVG_START_RE = /^(?:<\?xml|<svg[\s>])/i;
const GRAPH_KEYS_RE = /"nodes"\s*:|"edges"\s*:/;
const SAFE_NEW_BLOCK_START_RE = /^[^\s\-*+>[\d~]/;

// Segmen "[...](...)" yang lebih panjang dari ini dianggap teks biasa, bukan
// tautan/gambar yang sedang ditulis (mencegah teks panjang ikut tersembunyi).
const MAX_HOLD_SEGMENT = 400;

// ============================================================
// HELPER BARIS (murni)
// ============================================================

function indentOf(line) {
  let width = 0;

  for (const ch of line) {
    if (ch === " ") width += 1;
    else if (ch === "\t") width += 4;
    else break;
  }

  return width;
}

function blockKindOf(line) {
  if (LIST_MARKER_RE.test(line)) return "list";
  if (QUOTE_RE.test(line)) return "quote";
  return "other";
}

/** null kalau bukan pembuka pagar kode. */
function parseFenceOpen(line) {
  const match = FENCE_LINE_RE.exec(line);

  if (!match) return null;

  const marker = match[2];
  const rest = match[3];

  // ```kode``` dalam satu baris = kode inline, bukan pagar.
  if (marker[0] === "`" && rest.includes("`")) return null;

  return {
    char: marker[0],
    len: marker.length,
    indent: indentOf(match[1]),
    lang: (rest.trim().split(/\s+/)[0] || "").toLowerCase(),
  };
}

function isFenceClose(line, fence) {
  const match = FENCE_CLOSE_RE.exec(line);

  return Boolean(match) && match[1][0] === fence.char && match[1].length >= fence.len;
}

/** Bolehkah baris kosong + `line` memulai blok BARU tanpa mengubah arti Markdown? */
function canSplit(curKind, line) {
  if (indentOf(line) >= 2) return false;
  if (curKind === "list" && LIST_MARKER_RE.test(line)) return false;
  if (curKind === "quote" && QUOTE_RE.test(line)) return false;
  if (REF_DEF_RE.test(line)) return false;

  return true;
}

/** Untuk baris yang BELUM lengkap: hanya yakin memisah kalau karakter pertamanya aman. */
function definitelySplits(partial) {
  return SAFE_NEW_BLOCK_START_RE.test(partial);
}

function isSvgStartPrefix(first) {
  return first.length > 0 && first.length < 5 && ("<svg".startsWith(first) || "<?xml".startsWith(first));
}

/**
 * Jenis isi pagar kode berdasarkan bahasa + baris isi yang sudah diterima.
 * SVG/GRAPH = jenis yang DITAHAN sampai lengkap; CODE = tampil progresif.
 */
export function detectFenceKind(lang, bodyLines) {
  const first = (bodyLines.find((line) => line.trim() !== "") ?? "").trim();

  if (lang === "svg") return BLOCK_KIND.SVG;

  if ((lang === "" || lang === "xml" || lang === "html") && (SVG_START_RE.test(first) || isSvgStartPrefix(first))) {
    return BLOCK_KIND.SVG;
  }

  if (lang === "graph") return BLOCK_KIND.GRAPH;

  if ((lang === "" || lang === "json") && first.startsWith("{") && GRAPH_KEYS_RE.test(bodyLines.join("\n"))) {
    return BLOCK_KIND.GRAPH;
  }

  return BLOCK_KIND.CODE;
}

function isHeldKind(kind) {
  return kind === BLOCK_KIND.SVG || kind === BLOCK_KIND.GRAPH;
}

/**
 * Buang tautan/gambar Markdown yang BELUM tertutup di ujung teks, mis.
 * "![router](https://exa" atau "[dok](http://x". Yang sudah lengkap
 * ("![router](https://exa.com/r.jpg)") dibiarkan - langsung tampil.
 */
export function stripIncompleteInline(text) {
  const open = text.lastIndexOf("[");

  if (open === -1) return text;

  const start = open > 0 && text[open - 1] === "!" ? open - 1 : open;
  const segment = text.slice(open);

  if (segment.length > MAX_HOLD_SEGMENT || segment.includes("\n")) return text;

  const close = segment.indexOf("]");

  if (close === -1) return text.slice(0, start);

  const rest = segment.slice(close + 1);

  if (rest === "") return text.slice(0, start); // "[teks]" menunggu "("
  if (rest[0] !== "(") return text;             // kurung siku biasa

  let depth = 0;

  for (const ch of rest) {
    if (ch === "(") {
      depth += 1;
    } else if (ch === ")") {
      depth -= 1;
      if (depth === 0) return text;             // tertutup: lengkap
    }
  }

  return text.slice(0, start);
}

/** Baris partial yang tampak seperti awal pagar kode: sembunyikan, dan kenali SVG/graph lebih awal. */
function holdPartial(partial) {
  const match = /^(\s*)(`{3,}|~{3,})\s*(\S*)/.exec(partial);

  if (match) {
    const rest = partial.slice(match[1].length + match[2].length);

    if (!(match[2][0] === "`" && rest.includes("`"))) {
      const lang = match[3].toLowerCase();
      const kind = lang === "svg" ? BLOCK_KIND.SVG : lang === "graph" ? BLOCK_KIND.GRAPH : null;

      return { hidden: true, pending: kind ? { kind, lines: 0 } : null };
    }
  }

  if (/^\s{0,3}(`{1,2}|~{1,2})$/.test(partial)) return { hidden: true, pending: null };

  return { hidden: false, pending: null };
}

// ============================================================
// PARSER
// ============================================================

export class IncrementalResponseParser {

  constructor() {
    this.reset();
  }

  reset() {
    this._consumed = "";
    this._partial = "";
    this._blocks = [];
    this._cur = null;     // { lines, blank, kind } - blok teks yang sedang terbuka
    this._fence = null;   // { char, len, lang, nested, lines } - pagar kode yang sedang terbuka
    this._finished = false;
  }

  /** Seluruh teks yang sudah diterima (dipakai untuk memeriksa apakah input masih append-only). */
  get consumed() {
    return this._consumed;
  }

  get finished() {
    return this._finished;
  }

  /**
   * Sinkronkan dengan teks LENGKAP terbaru. Kalau teks hanya bertambah di
   * ujung, hanya bagian barunya yang diproses (incremental). Kalau berubah
   * di tempat lain (reset buffer karena retry/fallback, atau jawaban final
   * berbeda), parser dimulai ulang dari nol - hasil selalu benar.
   */
  sync(text, { final = false } = {}) {
    const next = typeof text === "string" ? text : "";
    const appendOnly = this._finished ? next === this._consumed : next.startsWith(this._consumed);

    if (!appendOnly) this.reset();

    if (!this._finished && next.length > this._consumed.length) {
      this.push(next.slice(this._consumed.length));
    }

    if (final && !this._finished) this.finish();

    return this.snapshot();
  }

  push(chunk) {
    if (this._finished || typeof chunk !== "string" || chunk === "") return;

    this._consumed += chunk;

    const parts = (this._partial + chunk).split("\n");

    this._partial = parts.pop();

    for (const line of parts) {
      this._line(line.endsWith("\r") ? line.slice(0, -1) : line);
    }
  }

  /** Akhir jawaban: baris terakhir dibaca apa adanya, pagar yang tak tertutup ditutup apa adanya. */
  finish() {
    if (this._finished) return;

    if (this._partial !== "") {
      const line = this._partial.replace(/\r$/, "");

      this._partial = "";
      this._line(line);
    }

    if (this._fence) this._closeFence(false);

    this._commitCur();
    this._finished = true;
  }

  // ------------------------------------------------------------ baris lengkap

  _line(line) {
    if (this._fence) {
      this._fenceLine(line);
      return;
    }

    const open = parseFenceOpen(line);

    if (open) {
      const nested = Boolean(this._cur) && this._cur.kind === "list" && open.indent >= 2;

      if (nested || open.indent <= 3) {
        this._openFence(open, line, nested);
        return;
      }
    }

    this._textLine(line);
  }

  _textLine(line) {
    const cur = this._cur;

    if (line.trim() === "") {
      if (cur) cur.blank += 1;
      return;
    }

    if (!cur) {
      this._cur = { lines: [line], blank: 0, kind: blockKindOf(line) };
      return;
    }

    if (cur.blank > 0) {
      if (canSplit(cur.kind, line)) {
        this._commitCur();
        this._cur = { lines: [line], blank: 0, kind: blockKindOf(line) };
        return;
      }

      for (let i = 0; i < cur.blank; i += 1) cur.lines.push("");
      cur.blank = 0;
    }

    cur.lines.push(line);
  }

  _openFence(open, line, nested) {
    if (nested) {
      // pagar di dalam butir daftar: tetap satu blok dengan daftarnya
      for (let i = 0; i < this._cur.blank; i += 1) this._cur.lines.push("");
      this._cur.blank = 0;
    } else {
      this._commitCur();
    }

    this._fence = { char: open.char, len: open.len, lang: open.lang, nested, lines: [line] };
  }

  _fenceLine(line) {
    const fence = this._fence;

    fence.lines.push(line);

    if (isFenceClose(line, fence)) this._closeFence(true);
  }

  _closeFence(closed) {
    const fence = this._fence;

    this._fence = null;

    if (fence.nested) {
      this._cur.lines.push(...fence.lines);
      return;
    }

    const body = fence.lines.slice(1, closed ? -1 : undefined);

    this._blocks.push({
      index: this._blocks.length,
      kind: detectFenceKind(fence.lang, body),
      lang: fence.lang,
      source: fence.lines.join("\n"),
    });
  }

  _commitCur() {
    if (!this._cur) return;

    this._blocks.push({
      index: this._blocks.length,
      kind: BLOCK_KIND.TEXT,
      lang: "",
      source: this._cur.lines.join("\n"),
    });

    this._cur = null;
  }

  // ------------------------------------------------------------ snapshot

  snapshot() {
    if (this._finished) {
      return { blocks: this._blocks.slice(), tail: null, pending: null, complete: true };
    }

    const partial = this._partial.replace(/\r$/, "");
    const fence = this._fence;
    const cur = this._cur;

    let blocks = this._blocks;
    let tailLines = null;
    let pending = null;
    let sanitize = true;

    if (fence) {
      const body = fence.lines.slice(1);
      const kind = detectFenceKind(fence.lang, partial === "" ? body : [...body, partial]);

      if (isHeldKind(kind)) {
        // SVG / graph: tahan sampai pagar penutup tiba.
        pending = { kind, lines: body.length };
        tailLines = fence.nested ? [...cur.lines] : null;
      } else {
        const shown = [...fence.lines];

        if (partial !== "" && !FENCE_PARTIAL_RE.test(partial)) shown.push(partial);

        tailLines = fence.nested ? [...cur.lines, ...shown] : shown;
        sanitize = false; // isi kode: jangan sentuh tanda kurung siku
      }
    } else {
      let lines = cur ? [...cur.lines] : [];

      if (partial !== "") {
        const hold = holdPartial(partial);

        if (hold.hidden) {
          pending = hold.pending;
        } else if (cur && cur.blank > 0) {
          if (definitelySplits(partial)) {
            // paragraf baru sudah pasti: blok sebelumnya boleh dianggap final sekarang
            blocks = [...blocks, {
              index: blocks.length, kind: BLOCK_KIND.TEXT, lang: "", source: cur.lines.join("\n"),
            }];
            lines = [partial];
          } else {
            for (let i = 0; i < cur.blank; i += 1) lines.push("");
            lines.push(partial);
          }
        } else {
          lines.push(partial);
        }
      }

      tailLines = lines;
    }

    let tail = null;

    if (tailLines && tailLines.length > 0) {
      let source = tailLines.join("\n");

      if (sanitize) source = stripIncompleteInline(source);

      if (source.trim() !== "") tail = { index: blocks.length, source };
    }

    return {
      blocks: blocks === this._blocks ? blocks.slice() : blocks,
      tail,
      pending,
      complete: false,
    };
  }
}

/** Satu kali jalan (mis. respons non-streaming): teks lengkap -> snapshot final. */
export function parseComplete(text) {
  return new IncrementalResponseParser().sync(text, { final: true });
}
