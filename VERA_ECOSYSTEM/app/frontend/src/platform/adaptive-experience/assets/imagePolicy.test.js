/**
 * src/platform/adaptive-experience/assets/imagePolicy.test.js
 *
 * Tests for Remote Image Asset Policy.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import {
  validateImageUrl,
  isSafeImageUrl,
  IMAGE_SECURITY_ATTRIBUTES,
} from "./imagePolicy.js";

test("Remote Image Policy: allows valid public HTTPS and HTTP URLs", () => {
  const allowed = [
    "https://example.com/image.png",
    "http://cdn.network.internal.public.org/photo.jpg",
    "https://images.unsplash.com/photo-1542838132?auto=format",
    "/static/assets/vera-logo.svg",
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
  ];

  for (const url of allowed) {
    const res = validateImageUrl(url);
    assert.equal(res.valid, true, `Expected valid for ${url}`);
    assert.equal(isSafeImageUrl(url), true);
  }
});

test("Remote Image Policy: rejects dangerous protocol schemes", () => {
  const dangerous = [
    "javascript:alert(1)",
    "file:///etc/passwd",
    "vbscript:msgbox",
    "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==",
    "ftp://example.com/file.jpg",
  ];

  for (const url of dangerous) {
    const res = validateImageUrl(url);
    assert.equal(res.valid, false, `Expected rejected for ${url}`);
    assert.equal(isSafeImageUrl(url), false);
  }
});

test("Remote Image Policy: blocks SSRF / loopback / private IP addresses", () => {
  const ssrf = [
    "http://localhost:8080/secret.png",
    "http://127.0.0.1/admin.png",
    "http://127.0.0.2:3000/avatar.jpg",
    "https://10.0.0.1/router.png",
    "http://10.254.1.20/image.jpg",
    "http://172.16.0.10/switch.png",
    "http://172.31.255.255/internal.png",
    "http://192.168.1.1/dashboard.png",
    "http://192.168.100.50/map.png",
    "http://169.254.169.254/latest/meta-data/",
    "http://metadata.google.internal/computeMetadata/v1/",
    "http://instance-data/latest/api/token",
    "http://0.0.0.0/test.png",
  ];

  for (const url of ssrf) {
    const res = validateImageUrl(url);
    assert.equal(res.valid, false, `Expected blocked for SSRF target ${url}`);
    assert.match(res.reason, /Blocked/i);
  }
});

test("Remote Image Policy: exposes standard security attributes", () => {
  assert.equal(IMAGE_SECURITY_ATTRIBUTES.referrerPolicy, "no-referrer");
  assert.equal(IMAGE_SECURITY_ATTRIBUTES.loading, "lazy");
});
