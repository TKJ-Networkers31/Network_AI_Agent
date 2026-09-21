import { STATUS_META, normalizeStatus } from "./cockpitContracts.js";

const TONE_VAR = {
  ok: "var(--ck-ok)",
  accent: "var(--ck-accent)",
  err: "var(--ck-err)",
  muted: "var(--ck-muted)",
};

/**
 * Penanda status yang dibedakan lewat BENTUK (bukan hanya warna):
 *  connected  = titik penuh        connecting = lingkaran kosong berdenyut
 *  busy       = titik + cincin     failed     = belah ketupat merah
 *  disconnected = lingkaran kosong redup
 */
export default function StatusDot({ status, size = 8 }) {
  const meta = STATUS_META[normalizeStatus(status)];
  const color = TONE_VAR[meta.tone];

  if (meta.shape === "diamond") {
    const s = Math.max(5, size - 1);
    return (
      <span
        aria-hidden="true"
        className="inline-block shrink-0 rotate-45 rounded-[1px]"
        style={{ width: s, height: s, background: color }}
      />
    );
  }

  if (meta.shape === "ping") {
    return (
      <span aria-hidden="true" className="relative inline-flex shrink-0" style={{ width: size, height: size }}>
        <span
          className="absolute inset-0 rounded-full opacity-60 motion-safe:animate-ping"
          style={{ background: color }}
        />
        <span className="relative rounded-full" style={{ width: size, height: size, background: color }} />
      </span>
    );
  }

  const hollow = meta.shape === "hollow";

  return (
    <span
      aria-hidden="true"
      className={`inline-block shrink-0 rounded-full ${meta.pulse ? "motion-safe:animate-pulse" : ""}`}
      style={{
        width: size,
        height: size,
        background: hollow ? "transparent" : color,
        boxShadow: hollow ? `inset 0 0 0 1.5px ${color}` : "none",
      }}
    />
  );
}
