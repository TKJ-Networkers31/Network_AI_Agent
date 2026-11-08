/**
 * utils/clipboard.js — salin teks ke clipboard.
 *
 * navigator.clipboard HANYA tersedia di "secure context" (https atau
 * localhost). AIRA sering dibuka lewat http://192.168.x.x (PWA di HP
 * satu jaringan) - di situ navigator.clipboard undefined, jadi ada
 * fallback lewat textarea tersembunyi + execCommand("copy").
 *
 * Return: true kalau berhasil, false kalau gagal.
 */
export async function copyText(text) {
  const value = String(text ?? "");

  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(value);
      return true;
    }
  } catch {
    // jatuh ke fallback di bawah
  }

  try {
    const area = document.createElement("textarea");
    area.value = value;
    area.setAttribute("readonly", "");
    area.style.cssText =
      "position:fixed;top:0;left:0;width:1px;height:1px;opacity:0;pointer-events:none;";
    document.body.appendChild(area);
    area.focus();
    area.select();
    area.setSelectionRange(0, value.length);
    const ok = document.execCommand("copy");
    document.body.removeChild(area);
    return ok;
  } catch {
    return false;
  }
}
