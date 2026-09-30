// src/utils/quotedMessage.js
// Format kutipan ala WhatsApp reply. Disimpan sebagai blockquote Markdown
// biasa ("> ...") sehingga: (1) LLM memahaminya apa adanya, (2) persisten di
// chat_turns tanpa skema baru, (3) MessageBubble bisa merendernya sebagai kartu.

export const MAX_QUOTE_CHARS = 600;

export function formatQuotedMessage(quote, question) {
  let clean = String(quote ?? "").trim();
  if (!clean) return String(question ?? "").trim();

  if (clean.length > MAX_QUOTE_CHARS) clean = `${clean.slice(0, MAX_QUOTE_CHARS - 1).trimEnd()}…`;

  const quoted = clean
    .split(/\r?\n/)
    .map((line) => `> ${line}`)
    .join("\n");

  const q = String(question ?? "").trim();
  return q ? `${quoted}\n\n${q}` : quoted;
}

/** -> { quote, body } atau null kalau pesan tidak diawali blockquote. */
export function parseQuotedMessage(content) {
  const text = String(content ?? "");
  if (!text.startsWith("> ")) return null;

  const lines = text.split("\n");
  const quoteLines = [];
  let i = 0;

  while (i < lines.length && lines[i].startsWith(">")) {
    quoteLines.push(lines[i].replace(/^>\s?/, ""));
    i += 1;
  }

  while (i < lines.length && lines[i].trim() === "") i += 1;

  return { quote: quoteLines.join("\n"), body: lines.slice(i).join("\n") };
}