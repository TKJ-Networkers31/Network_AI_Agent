import test from "node:test";
import assert from "node:assert/strict";
import { formatQuotedMessage, parseQuotedMessage, MAX_QUOTE_CHARS } from "./quotedMessage.js";

test("format + parse round-trip", () => {
  const msg = formatQuotedMessage("VRRP pakai virtual IP", "jelaskan dong");
  assert.equal(msg, "> VRRP pakai virtual IP\n\njelaskan dong");
  assert.deepEqual(parseQuotedMessage(msg), { quote: "VRRP pakai virtual IP", body: "jelaskan dong" });
});

test("kutipan multi-baris", () => {
  const msg = formatQuotedMessage("baris1\nbaris2", "tanya");
  assert.deepEqual(parseQuotedMessage(msg), { quote: "baris1\nbaris2", body: "tanya" });
});

test("tanpa pertanyaan -> hanya kutipan", () => {
  const parsed = parseQuotedMessage(formatQuotedMessage("abc", ""));
  assert.deepEqual(parsed, { quote: "abc", body: "" });
});

test("kutipan panjang dipotong", () => {
  const msg = formatQuotedMessage("x".repeat(MAX_QUOTE_CHARS + 50), "q");
  assert.ok(parseQuotedMessage(msg).quote.length <= MAX_QUOTE_CHARS);
});

test("pesan biasa bukan kutipan; quote kosong -> pertanyaan saja", () => {
  assert.equal(parseQuotedMessage("halo"), null);
  assert.equal(formatQuotedMessage("  ", "halo"), "halo");
});