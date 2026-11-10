/**
 * src/platform/adaptive-experience/assets/imagePolicy.js
 *
 * Remote Image Asset Security Policy.
 * Validates and sanitizes image URLs rendered by Markdown, VAE blocks, and DIO fields:
 * - Rejects non-HTTP(S) schemes (blocks javascript:, vbscript:, file:, etc.)
 * - Prevents SSRF / private network exfiltration by rejecting localhost, private IPs, and cloud metadata
 * - Enforces zero-referrer leakage policy (referrerPolicy: no-referrer)
 */

const BLOCKED_HOSTNAMES = new Set([
  "localhost",
  "127.0.0.1",
  "0.0.0.0",
  "169.254.169.254", // AWS/GCP/Azure metadata service
  "metadata.google.internal",
  "instance-data",
]);

/**
 * Checks if an IPv4 address falls within private, loopback, or link-local ranges.
 */
function isPrivateOrReservedIpv4(ip) {
  const parts = ip.split(".").map(Number);
  if (parts.length !== 4 || parts.some((p) => isNaN(p) || p < 0 || p > 255)) {
    return false;
  }
  const [b0, b1] = parts;

  // 127.0.0.0/8 (Loopback)
  if (b0 === 127) return true;
  // 10.0.0.0/8 (Private RFC 1918)
  if (b0 === 10) return true;
  // 172.16.0.0/12 (Private RFC 1918: 172.16.0.0 – 172.31.255.255)
  if (b0 === 172 && b1 >= 16 && b1 <= 31) return true;
  // 192.168.0.0/16 (Private RFC 1918)
  if (b0 === 192 && b1 === 168) return true;
  // 169.254.0.0/16 (Link-Local & Cloud Metadata)
  if (b0 === 169 && b1 === 254) return true;
  // 0.0.0.0/8
  if (b0 === 0) return true;

  return false;
}

/**
 * Validates an image URL against scheme and SSRF/private host rules.
 *
 * @param {string} url - Target URL to validate
 * @returns {{ valid: boolean, sanitizedUrl?: string, reason?: string }}
 */
export function validateImageUrl(url) {
  if (!url || typeof url !== "string") {
    return { valid: false, reason: "Missing or invalid URL string" };
  }

  const trimmed = url.trim();

  // Allow safe relative paths (e.g. /static/logo.svg)
  if (trimmed.startsWith("/") && !trimmed.startsWith("//")) {
    return { valid: true, sanitizedUrl: trimmed };
  }

  // Allow safe base64 images (PNG, JPEG, GIF, WEBP)
  if (/^data:image\/(png|jpeg|jpg|gif|webp);base64,/i.test(trimmed)) {
    return { valid: true, sanitizedUrl: trimmed };
  }

  // Parse URL
  let parsed;
  try {
    parsed = new URL(trimmed);
  } catch {
    return { valid: false, reason: "Malformed URL" };
  }

  // Only allow http: and https: protocols
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    return {
      valid: false,
      reason: `Disallowed protocol scheme: ${parsed.protocol}`,
    };
  }

  const hostname = parsed.hostname.toLowerCase();

  // Check known blocked hostnames
  if (BLOCKED_HOSTNAMES.has(hostname)) {
    return {
      valid: false,
      reason: `Blocked private or cloud metadata hostname: ${hostname}`,
    };
  }

  // Check IPv4 private and link-local ranges
  if (isPrivateOrReservedIpv4(hostname)) {
    return {
      valid: false,
      reason: `Blocked private or reserved IP address: ${hostname}`,
    };
  }

  // Check IPv6 loopback and private ranges
  if (
    hostname === "::1" ||
    hostname.startsWith("fe80:") ||
    hostname.startsWith("fc00:") ||
    hostname.startsWith("fd00:")
  ) {
    return {
      valid: false,
      reason: `Blocked private or loopback IPv6 address: ${hostname}`,
    };
  }

  return { valid: true, sanitizedUrl: parsed.toString() };
}

/**
 * Returns true if the image URL passes security policy.
 */
export function isSafeImageUrl(url) {
  return validateImageUrl(url).valid;
}

/**
 * Standard security attributes to attach to <img> elements rendering external media.
 */
export const IMAGE_SECURITY_ATTRIBUTES = Object.freeze({
  referrerPolicy: "no-referrer",
  crossOrigin: "anonymous",
  loading: "lazy",
});
