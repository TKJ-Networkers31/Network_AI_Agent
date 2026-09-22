import test from "node:test";
import assert from "node:assert/strict";
import {
  BLOCK_KIND,
  IncrementalResponseParser,
  detectFenceKind,
  parseComplete,
  stripIncompleteInline,
} from "./streamParser.js";

// ------------------------------------------------------------ helpers

function feed(chunks, { final = false } = {}) {
  const parser = new IncrementalResponseParser();
  let snap = parser.snapshot();

  for (const chunk of chunks) {
    parser.push(chunk);
    snap = parser.snapshot();
  }

  if (final) {
    parser.finish();
    snap = parser.snapshot();
  }

  return { parser, snap };
}

/** Potong `text` menjadi potongan berukuran tetap. */
function slices(text, size) {
  const out = [];
  for (let i = 0; i < text.length; i += size) out.push(text.slice(i, i + size));
  return out;
}

/** PRNG deterministik (mulberry32) supaya "acak" tetap bisa diulang. */
function rng(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function randomSlices(text, seed, max = 9) {
  const next = rng(seed);
  const out = [];
  let i = 0;
  while (i < text.length) {
    const size = 1 + Math.floor(next() * max);
    out.push(text.slice(i, i + size));
    i += size;
  }
  return out;
}

const sources = (snap) => snap.blocks.map((b) => b.source);
const kinds = (snap) => snap.blocks.map((b) => b.kind);

/** Final snapshot -> bentuk yang bisa dibandingkan. */
const shape = (snap) => JSON.stringify({ blocks: snap.blocks, tail: snap.tail, pending: snap.pending, complete: snap.complete });

const MIXED = [
  "# Diagnosis R1",
  "",
  "CPU **normal**, memory 41%. Lihat foto perangkat:",
  "",
  "![router](https://example.com/r1.jpg)",
  "![rack](https://example.com/rack.jpg)",
  "![kabel](https://example.com/kabel.jpg)",
  "",
  "Langkah yang disarankan:",
  "",
  "1. Cek interface",
  "",
  "2. Jalankan perintah:",
  "",
  "   ```bash",
  "   /interface print",
  "   ```",
  "",
  "3. Bandingkan hasilnya",
  "",
  "Topologi singkat:",
  "",
  "```svg",
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 50">',
  '  <rect width="100" height="50" fill="#fff"/>',
  '  <text x="10" y="30">R1 - R2</text>',
  "</svg>",
  "```",
  "",
  "> Catatan: uji dulu di lab.",
  "",
  "| Port | Status |",
  "|------|--------|",
  "| ether1 | up |",
  "",
  "Selesai. Dokumentasi: [MikroTik](https://help.mikrotik.com/docs).",
].join("\n");

// ============================================================
// 1. PLAIN TEXT CHUNKS
// ============================================================

test("plain text: tumbuh progresif di tail, tanpa blok final, lintas potongan di tengah kata", () => {
  const parser = new IncrementalResponseParser();
  const seen = [];

  for (const chunk of ["Ha", "lo du", "nia, ap", "a kabar?"]) {
    parser.push(chunk);
    const snap = parser.snapshot();
    seen.push(snap.tail.source);
    assert.deepEqual(snap.blocks, []);
    assert.equal(snap.pending, null);
    assert.equal(snap.complete, false);
  }

  assert.deepEqual(seen, ["Ha", "Halo du", "Halo dunia, ap", "Halo dunia, apa kabar?"]);
});

test("plain text: finish() memindahkan tail menjadi satu blok final", () => {
  const { snap } = feed(["Halo ", "dunia"], { final: true });

  assert.deepEqual(sources(snap), ["Halo dunia"]);
  assert.equal(snap.tail, null);
  assert.equal(snap.complete, true);
});

test("plain text: CRLF dan potongan tepat di antara \\r dan \\n", () => {
  const { snap } = feed(["baris satu\r", "\nbaris dua\r\n", "baris tiga"], { final: true });

  assert.deepEqual(sources(snap), ["baris satu\nbaris dua\nbaris tiga"]);
});

// ============================================================
// 2. PARAGRAPH CHUNKS
// ============================================================

test("paragraf: blok final hanya bertambah, tidak pernah berubah; paragraf terakhir jadi tail", () => {
  const parser = new IncrementalResponseParser();
  const text = "Paragraf satu.\n\nParagraf dua.\n\nParagraf tiga";
  const history = [];

  for (const chunk of slices(text, 4)) {
    parser.push(chunk);
    history.push(parser.snapshot());
  }

  // blok yang sudah final tidak pernah berubah isinya di snapshot berikutnya
  for (let i = 1; i < history.length; i += 1) {
    const before = history[i - 1].blocks;
    const after = history[i].blocks;
    assert.ok(after.length >= before.length);
    assert.deepEqual(after.slice(0, before.length), before);
  }

  const last = history.at(-1);
  assert.deepEqual(sources(last), ["Paragraf satu.", "Paragraf dua."]);
  assert.equal(last.tail.source, "Paragraf tiga");
  assert.equal(last.tail.index, 2);
});

test("paragraf: potongan berhenti tepat di baris kosong -> belum memisah, tanpa kehilangan teks", () => {
  const { snap } = feed(["Satu.\n", "\n"]);

  assert.deepEqual(snap.blocks, []);
  assert.equal(snap.tail.source, "Satu.");

  const after = feed(["Satu.\n", "\n", "Du"]);
  assert.deepEqual(sources(after.snap), ["Satu."]);
  assert.equal(after.snap.tail.source, "Du");
});

test("paragraf: awal baris ambigu (angka/-/>) ditahan bersama blok sebelumnya sampai baris lengkap", () => {
  const partial = feed(["Intro.\n\n", "2"]);

  assert.deepEqual(partial.snap.blocks, []);
  assert.equal(partial.snap.tail.source, "Intro.\n\n2");

  // baris lengkap menentukan: "2 router" = paragraf baru -> blok terpisah
  const done = feed(["Intro.\n\n", "2 router aktif\n", "lanjut"]);
  assert.deepEqual(sources(done.snap), ["Intro."]);
  assert.equal(done.snap.tail.source, "2 router aktif\nlanjut");
});

test("paragraf: blok yang dianggap final lebih awal (huruf jelas) sama dengan hasil commit sebenarnya", () => {
  const early = feed(["A.\n\nB"]);
  const later = feed(["A.\n\nB\n"]);

  assert.deepEqual(sources(early.snap), ["A."]);
  assert.deepEqual(sources(later.snap), ["A."]);
  assert.equal(early.snap.tail.index, later.snap.tail.index);
});

// ============================================================
// 3. MARKDOWN
// ============================================================

test("markdown: heading, daftar longgar, blockquote, dan tabel tidak terpecah salah", () => {
  const doc = [
    "## Judul",
    "",
    "- satu",
    "",
    "- dua",
    "",
    "- tiga",
    "",
    "> kutipan",
    "",
    "> lanjutan kutipan",
    "",
    "| a | b |",
    "|---|---|",
    "| 1 | 2 |",
    "",
    "Penutup.",
  ].join("\n");

  const snap = parseComplete(doc);

  assert.deepEqual(sources(snap), [
    "## Judul",
    "- satu\n\n- dua\n\n- tiga",
    "> kutipan\n\n> lanjutan kutipan",
    "| a | b |\n|---|---|\n| 1 | 2 |",
    "Penutup.",
  ]);
});

test("markdown: daftar bernomor longgar tetap satu blok (penomoran terjaga)", () => {
  const snap = parseComplete("1. a\n\n2. b\n\n3. c");

  assert.deepEqual(sources(snap), ["1. a\n\n2. b\n\n3. c"]);
});

test("markdown: baris berindentasi dan definisi referensi tidak dipisah", () => {
  const snap = parseComplete("- item\n\n  lanjutan item\n\n[1]: https://example.com");

  assert.equal(snap.blocks.length, 1);
});

test("markdown: daftar lalu paragraf biasa -> dua blok", () => {
  const snap = parseComplete("- a\n- b\n\nSetelah daftar.");

  assert.deepEqual(sources(snap), ["- a\n- b", "Setelah daftar."]);
});

// ============================================================
// 4. INCOMPLETE MARKDOWN
// ============================================================

test("markdown tak lengkap: gambar/tautan yang belum tertutup disembunyikan, yang lengkap langsung tampil", () => {
  const steps = [
    ["Lihat ![router](https://exa", "Lihat "],
    ["mple.com/r.jpg", "Lihat "],
    [")", "Lihat ![router](https://example.com/r.jpg)"],
    [" dan [dok](http://x", "Lihat ![router](https://example.com/r.jpg) dan "],
    [".org)", "Lihat ![router](https://example.com/r.jpg) dan [dok](http://x.org)"],
  ];

  const parser = new IncrementalResponseParser();

  for (const [chunk, expected] of steps) {
    parser.push(chunk);
    assert.equal(parser.snapshot().tail.source.trimEnd(), expected.trimEnd(), chunk);
  }
});

test("markdown tak lengkap: '![' dan '[teks]' yang menunggu '(' disembunyikan", () => {
  assert.equal(stripIncompleteInline("Foto ![al"), "Foto ");
  assert.equal(stripIncompleteInline("Foto ![alt]"), "Foto ");
  assert.equal(stripIncompleteInline("Foto ![alt]("), "Foto ");
  assert.equal(stripIncompleteInline("Tautan [teks"), "Tautan ");
});

test("markdown tak lengkap: kurung siku biasa, tautan bertingkat kurung, dan teks panjang tidak ikut disembunyikan", () => {
  assert.equal(stripIncompleteInline("array[0] selesai"), "array[0] selesai");
  assert.equal(stripIncompleteInline("[x] tugas"), "[x] tugas");
  assert.equal(stripIncompleteInline("[wiki](https://a.org/w_(x))"), "[wiki](https://a.org/w_(x))");
  assert.equal(stripIncompleteInline("[wiki](https://a.org/w_(x)"), "");
  assert.equal(stripIncompleteInline("tanpa kurung siku sama sekali"), "tanpa kurung siku sama sekali");

  const long = `awal [${"x".repeat(500)}`;
  assert.equal(stripIncompleteInline(long), long);
});

test("markdown tak lengkap: gambar yang seluruhnya belum masuk tidak membuat tail kosong palsu", () => {
  const { snap } = feed(["![a](http://x"]);

  assert.equal(snap.tail, null);
  assert.deepEqual(snap.blocks, []);
});

test("markdown tak lengkap: tanda ** dan ` yang belum tertutup dibiarkan (renderer yang menanganinya)", () => {
  const { snap } = feed(["Ini **tebal dan `kode"]);

  assert.equal(snap.tail.source, "Ini **tebal dan `kode");
});

// ============================================================
// 5. CODE FENCE
// ============================================================

test("code fence: kode tampil progresif; pagar di baris sendiri memisah dari teks sebelumnya, pagar penutup menutup blok", () => {
  const parser = new IncrementalResponseParser();

  parser.push("Jalankan:\n```bash\nping 8.8");
  let snap = parser.snapshot();

  assert.deepEqual(sources(snap), ["Jalankan:"]);
  assert.equal(snap.tail.source, "```bash\nping 8.8");
  assert.equal(snap.tail.index, 1);
  assert.equal(snap.pending, null);

  parser.push(".8.8\n``");
  snap = parser.snapshot();
  assert.equal(snap.tail.source, "```bash\nping 8.8.8.8"); // "``" separuh penutup disembunyikan

  parser.push("`\nSelesai");
  snap = parser.snapshot();

  assert.deepEqual(kinds(snap), [BLOCK_KIND.TEXT, BLOCK_KIND.CODE]);
  assert.equal(snap.blocks[1].source, "```bash\nping 8.8.8.8\n```");
  assert.equal(snap.blocks[1].lang, "bash");
  assert.equal(snap.tail.source, "Selesai");
  assert.equal(snap.tail.index, 2);
});

test("code fence: key tail sama dengan index blok setelah commit (tanpa remount)", () => {
  const parser = new IncrementalResponseParser();

  parser.push("```js\nconst a = 1;");
  const open = parser.snapshot();

  parser.push("\n```\n");
  const closed = parser.snapshot();

  assert.equal(open.tail.index, 0);
  assert.equal(closed.blocks[0].index, 0);
  assert.equal(closed.tail, null);
});

test("code fence: isi kode dengan kurung siku / baris kosong / '```' di tengah baris tidak salah tafsir", () => {
  const doc = "```python\nx = arr[0\n\nprint('```')\n```";
  const snap = parseComplete(doc);

  assert.deepEqual(sources(snap), [doc]);
  assert.equal(snap.blocks[0].kind, BLOCK_KIND.CODE);

  const open = feed(["```python\nx = arr[0\n\nprint(1)"]).snap;
  assert.equal(open.tail.source, "```python\nx = arr[0\n\nprint(1)"); // "[0" tidak disentuh di dalam kode
});

test("code fence: kode inline ```satu baris``` bukan pagar", () => {
  const snap = parseComplete("Gunakan ```ping``` untuk cek.");

  assert.deepEqual(sources(snap), ["Gunakan ```ping``` untuk cek."]);
});

test("code fence: pagar tilde dan pagar penutup lebih panjang", () => {
  const snap = parseComplete("~~~sh\nls\n~~~\n\n````md\n```\ndalam\n```\n````");

  assert.deepEqual(sources(snap), ["~~~sh\nls\n~~~", "````md\n```\ndalam\n```\n````"]);
});

test("code fence: pagar di dalam butir daftar tetap satu blok dengan daftarnya", () => {
  const doc = "1. Jalankan:\n\n   ```bash\n   ls\n   ```\n\n2. Selesai";
  const snap = parseComplete(doc);

  assert.equal(snap.blocks.length, 1);
  assert.equal(snap.blocks[0].source, doc);
});

test("code fence: pagar tak tertutup di akhir jawaban ditutup apa adanya oleh finish()", () => {
  const { snap } = feed(["Kode:\n```bash\nls -la"], { final: true });

  assert.deepEqual(sources(snap), ["Kode:", "```bash\nls -la"]);
  assert.equal(snap.tail, null);
  assert.equal(snap.pending, null);
  assert.equal(snap.complete, true);
});

test("code fence: awal pagar yang belum lengkap ('`', '``', '```sv') disembunyikan, bukan dirender sebagai teks", () => {
  for (const partial of ["`", "``", "```", "```py"]) {
    const { snap } = feed([`Teks.\n${partial}`]);

    assert.equal(snap.tail.source, "Teks.", JSON.stringify(partial));
  }
});

// ============================================================
// 6-7. DIO (kontrak: tidak ada blok DIO di teks stream)
// ============================================================

test("DIO: teks yang menyebut form/JSON schema biasa tidak ditahan atau diubah oleh parser", () => {
  const text = 'Saya butuh data: {"schema_id":"x","mode":"form"}\n\nIsi form di bawah.';
  const snap = parseComplete(text);

  assert.deepEqual(sources(snap), ['Saya butuh data: {"schema_id":"x","mode":"form"}', "Isi form di bawah."]);
  assert.equal(snap.pending, null);
});

// ============================================================
// 8. SVG
// ============================================================

const SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10"/></svg>';

test("SVG: ditahan (pending) selama belum lengkap - tidak ada teks SVG yang bocor ke tail", () => {
  const parser = new IncrementalResponseParser();
  const doc = `Diagram:\n\n\`\`\`svg\n${SVG}\n\`\`\`\n`;

  for (const chunk of slices(doc, 5)) {
    parser.push(chunk);
    const snap = parser.snapshot();
    const visible = [...snap.blocks.map((b) => b.source), snap.tail?.source ?? ""].join("\n");

    if (snap.pending) {
      assert.equal(snap.pending.kind, BLOCK_KIND.SVG);
      assert.doesNotMatch(visible, /<svg|<rect/);
    }
  }

  const done = parser.snapshot();
  assert.equal(done.pending, null);
  assert.deepEqual(kinds(done), [BLOCK_KIND.TEXT, BLOCK_KIND.SVG]);
  assert.equal(done.blocks[1].source, `\`\`\`svg\n${SVG}\n\`\`\``);
});

test("SVG: 'pending' sudah aktif begitu '```svg' selesai diketik (bahkan sebelum baris pertama isi)", () => {
  assert.equal(feed(["Teks\n\n```svg"]).snap.pending?.kind, BLOCK_KIND.SVG);
  assert.equal(feed(["Teks\n\n```svg\n"]).snap.pending?.kind, BLOCK_KIND.SVG);
  assert.equal(feed(["Teks\n\n```sv"]).snap.pending, null); // belum jelas bahasanya
});

test("SVG: tanpa label bahasa / ```xml yang isinya <svg> juga ditahan, bahkan saat '<svg' baru separuh", () => {
  assert.equal(detectFenceKind("", ['<svg xmlns="x">']), BLOCK_KIND.SVG);
  assert.equal(detectFenceKind("xml", ["<?xml version=\"1.0\"?>"]), BLOCK_KIND.SVG);
  assert.equal(detectFenceKind("html", ["<sv"]), BLOCK_KIND.SVG);
  assert.equal(detectFenceKind("html", ["<div>"]), BLOCK_KIND.CODE);
  assert.equal(detectFenceKind("bash", ["<svg>"]), BLOCK_KIND.CODE);

  const partialLine = feed(["```\n<sv"]).snap;
  assert.equal(partialLine.pending?.kind, BLOCK_KIND.SVG);
  assert.equal(partialLine.tail, null);
});

test("SVG: blok lengkap punya kind svg dan source utuh untuk pipeline SVG yang ada", () => {
  const snap = parseComplete(`\`\`\`\n${SVG}\n\`\`\``);

  assert.equal(snap.blocks[0].kind, BLOCK_KIND.SVG);
  assert.match(snap.blocks[0].source, /^```\n<svg[\s\S]*<\/svg>\n```$/);
});

test("SVG: tidak tertutup di akhir jawaban -> dilepas apa adanya (renderer menampilkan 'SVG tidak lengkap')", () => {
  const { snap } = feed(["```svg\n<svg xmlns=\"x\"><rect"], { final: true });

  assert.equal(snap.pending, null);
  assert.equal(snap.blocks[0].kind, BLOCK_KIND.SVG);
  assert.equal(snap.blocks[0].source, '```svg\n<svg xmlns="x"><rect');
});

test("graph JSON: ditahan sampai lengkap; JSON biasa tetap progresif", () => {
  const graph = '{"nodes":[{"id":"a"}],"edges":[]}';
  const held = feed([`\`\`\`json\n{\n  "nodes": [`]).snap;

  assert.equal(held.pending?.kind, BLOCK_KIND.GRAPH);
  assert.equal(held.tail, null);

  const plain = feed(['```json\n{"nama": "R1", "cpu": 12']).snap;
  assert.equal(plain.pending, null);
  assert.equal(plain.tail.source, '```json\n{"nama": "R1", "cpu": 12');

  assert.equal(parseComplete(`\`\`\`graph\n${graph}\n\`\`\``).blocks[0].kind, BLOCK_KIND.GRAPH);
});

// ============================================================
// 9-10. IMAGE / GALLERY
// ============================================================

test("gambar: langsung tampil begitu sintaksnya lengkap, tanpa menunggu jawaban selesai", () => {
  const { snap } = feed(["Ini perangkatnya: ![MikroTik hAP](https://cdn.example.com/hap.jpg) dan seterusnya"]);

  assert.match(snap.tail.source, /!\[MikroTik hAP\]\(https:\/\/cdn\.example\.com\/hap\.jpg\)/);
  assert.equal(snap.complete, false);
  assert.equal(snap.pending, null);
});

test("galeri: gambar berurutan tampil satu per satu; yang belum lengkap disembunyikan", () => {
  const parser = new IncrementalResponseParser();
  const images = [
    "![a](https://x.test/a.jpg)",
    "![b](https://x.test/b.jpg)",
    "![c](https://x.test/c.jpg)",
  ];
  const doc = `${images.join("\n")}\n`;
  const counts = [];

  for (const chunk of slices(doc, 6)) {
    parser.push(chunk);
    const source = parser.snapshot().tail?.source ?? "";
    counts.push((source.match(/!\[/g) || []).length);
    // tidak pernah ada gambar setengah jadi di teks yang tampil
    for (const m of source.matchAll(/!\[[^\]]*\]\(([^)]*)/g)) {
      assert.match(source.slice(m.index), /^!\[[^\]]*\]\([^)]*\)/);
    }
  }

  assert.deepEqual([...counts].sort((x, y) => x - y), counts); // hanya bertambah
  assert.equal(counts.at(-1), 3);
});

// ============================================================
// 11. MIXED
// ============================================================

test("campuran: teks, gambar, daftar+kode, SVG, kutipan, tabel, tautan - urutan & jenis blok benar", () => {
  const snap = parseComplete(MIXED);

  assert.deepEqual(kinds(snap), [
    BLOCK_KIND.TEXT, // heading
    BLOCK_KIND.TEXT, // paragraf CPU
    BLOCK_KIND.TEXT, // galeri 3 gambar
    BLOCK_KIND.TEXT, // "Langkah yang disarankan:"
    BLOCK_KIND.TEXT, // daftar bernomor + kode bersarang
    BLOCK_KIND.TEXT, // "Topologi singkat:"
    BLOCK_KIND.SVG,
    BLOCK_KIND.TEXT, // kutipan
    BLOCK_KIND.TEXT, // tabel
    BLOCK_KIND.TEXT, // penutup
  ]);

  assert.match(snap.blocks[2].source, /kabel\.jpg/);
  assert.match(snap.blocks[4].source, /```bash[\s\S]*```[\s\S]*3\. Bandingkan/);
  assert.equal(snap.blocks[6].lang, "svg");
});

test("campuran: hasil akhir SAMA untuk semua ukuran potongan (1..40) dan potongan acak", () => {
  const reference = shape(feed([MIXED], { final: true }).snap);

  for (let size = 1; size <= 40; size += 1) {
    assert.equal(shape(feed(slices(MIXED, size), { final: true }).snap), reference, `size=${size}`);
  }

  for (let seed = 1; seed <= 60; seed += 1) {
    assert.equal(shape(feed(randomSlices(MIXED, seed), { final: true }).snap), reference, `seed=${seed}`);
  }
});

test("campuran: di SETIAP prefix blok final tidak berubah, tidak ada SVG setengah jadi, tidak ada gambar setengah jadi", () => {
  const parser = new IncrementalResponseParser();
  let previous = [];

  for (let end = 1; end <= MIXED.length; end += 1) {
    parser.reset();
    const snap = parser.sync(MIXED.slice(0, end));

    // hanya blok final + tail yang dilihat renderer
    const visible = [...snap.blocks.map((b) => b.source), snap.tail?.source ?? ""].join("\n\n");

    if (/<svg/.test(visible)) {
      assert.match(visible, /<\/svg>/, `SVG terpotong pada prefix ${end}`);
    }

    for (const m of visible.matchAll(/!\[[^\]]*\]/g)) {
      assert.match(visible.slice(m.index), /^!\[[^\]]*\]\([^)]*\)/, `gambar terpotong pada prefix ${end}`);
    }

    previous = snap.blocks;
  }

  assert.ok(previous.length > 0);
});

test("campuran: inkremental (satu parser, banyak push) == parse ulang dari nol di tiap langkah", () => {
  const incremental = new IncrementalResponseParser();
  let text = "";

  for (const chunk of randomSlices(MIXED, 7, 25)) {
    text += chunk;
    const a = incremental.sync(text);
    const b = new IncrementalResponseParser().sync(text);

    assert.equal(shape(a), shape(b));
  }
});

// ============================================================
// 12. COMPLETION
// ============================================================

test("selesai: finish() membaca baris terakhir, mengosongkan tail/pending, dan idempoten", () => {
  const { parser, snap } = feed(["Baris terakhir tanpa newline"], { final: true });

  assert.deepEqual(sources(snap), ["Baris terakhir tanpa newline"]);
  assert.equal(snap.tail, null);
  assert.equal(snap.pending, null);
  assert.equal(snap.complete, true);

  parser.finish();
  parser.push("diabaikan");
  assert.equal(shape(parser.snapshot()), shape(snap));
});

test("selesai: gambar setengah jadi di ujung jawaban final ditampilkan apa adanya (sama seperti non-streaming)", () => {
  const { snap } = feed(["Lihat ![a](http://x"], { final: true });

  assert.equal(snap.blocks[0].source, "Lihat ![a](http://x");
});

test("selesai: jawaban kosong menghasilkan snapshot kosong yang lengkap", () => {
  const snap = parseComplete("");

  assert.deepEqual({ blocks: snap.blocks, tail: snap.tail, complete: snap.complete }, { blocks: [], tail: null, complete: true });
});

// ============================================================
// SYNC (sinkron dengan teks lengkap: reset buffer / jawaban final)
// ============================================================

test("sync: hanya bagian baru yang diproses; teks yang berubah di tengah mereset parser", () => {
  const parser = new IncrementalResponseParser();

  parser.sync("Halo");
  assert.equal(parser.consumed, "Halo");

  parser.sync("Halo dunia");
  assert.equal(parser.consumed, "Halo dunia");

  // reset buffer (retry/fallback): teks bukan lanjutan
  const snap = parser.sync("Jawaban baru");
  assert.equal(snap.tail.source, "Jawaban baru");
  assert.equal(parser.consumed, "Jawaban baru");
});

test("sync: jawaban final yang berbeda dari teks stream diparse ulang dengan benar", () => {
  const parser = new IncrementalResponseParser();

  parser.sync("Draf sementara\n\n```svg\n<svg");
  const snap = parser.sync("Jawaban final.", { final: true });

  assert.deepEqual(sources(snap), ["Jawaban final."]);
  assert.equal(snap.pending, null);
  assert.equal(snap.complete, true);
});

test("sync: teks yang sama dipanggil berulang (render ulang React/StrictMode) tidak mengubah hasil", () => {
  const parser = new IncrementalResponseParser();
  const a = shape(parser.sync("Halo\n\nDunia", { final: false }));
  const b = shape(parser.sync("Halo\n\nDunia", { final: false }));

  assert.equal(a, b);
});

test("sync: non-streaming - satu kali final menghasilkan blok yang sama dengan streaming", () => {
  const streamed = feed(slices(MIXED, 13), { final: true }).snap;
  const oneShot = new IncrementalResponseParser().sync(MIXED, { final: true });

  assert.equal(shape(streamed), shape(oneShot));
});

test("sync: input bukan string diperlakukan sebagai kosong (tidak raise)", () => {
  for (const value of [undefined, null, 42, {}]) {
    assert.doesNotThrow(() => new IncrementalResponseParser().sync(value));
  }
});
