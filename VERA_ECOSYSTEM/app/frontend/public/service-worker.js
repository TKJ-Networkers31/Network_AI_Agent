const CACHE_VERSION = "netagent-v1";
const SHELL_CACHE = `${CACHE_VERSION}-shell`;
const RUNTIME_CACHE = `${CACHE_VERSION}-runtime`;

const SHELL_URLS = ["/", "/index.html", "/manifest.json"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(SHELL_CACHE)
      .then((cache) => cache.addAll(SHELL_URLS))
      .catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter(
            (key) =>
              key.startsWith("netagent-") &&
              key !== SHELL_CACHE &&
              key !== RUNTIME_CACHE
          )
          .map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const { request } = event;

  if (request.method !== "GET") return;

  const url = new URL(request.url);

  // Panggilan API, files, dan host selalu butuh data terbaru - jangan pernah di-cache
  if (
    url.pathname.startsWith("/api/") ||
    url.pathname.startsWith("/files/") ||
    url.pathname === "/files" ||
    url.pathname.startsWith("/host/") ||
    url.pathname === "/host"
  ) {
    return;
  }

  // Navigasi (buka app / refresh halaman) -> network first,
  // fallback ke shell cache kalau offline / backend mati
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(() => caches.match("/index.html"))
    );
    return;
  }

  // Aset statis same-origin (JS/CSS/gambar/font) -> stale-while-revalidate
  if (url.origin === self.location.origin) {
    event.respondWith(
      caches.open(RUNTIME_CACHE).then(async (cache) => {
        const cached = await cache.match(request);

        const networkFetch = fetch(request)
          .then((response) => {
            if (response && response.status === 200) {
              cache.put(request, response.clone());
            }
            return response;
          })
          .catch(() => cached);

        return cached || networkFetch;
      })
    );
  }
});

// ============================================================
// PUSH NOTIFICATIONS & DESKTOP NOTIFICATION CLICK HANDLING
// ============================================================

self.addEventListener("push", (event) => {
  if (!event.data) return;

  let payload = {};
  try {
    payload = event.data.json();
  } catch {
    payload = { title: "VERA Enterprise Intelligence", body: event.data.text() };
  }

  const title = payload.title || "VERA — Network Intelligence Platform";
  const options = {
    body: payload.body || "Operasi jaringan selesai atau memerlukan perhatian.",
    icon: payload.icon || "/favicon.ico",
    badge: payload.badge || "/favicon.ico",
    tag: payload.tag || "vera-background-notification",
    data: payload.data || {},
    renotify: Boolean(payload.renotify),
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();

  const targetUrl = event.notification.data?.url || "/";

  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if ("focus" in client) {
          if (client.url && client.url.includes(self.location.origin)) {
            client.focus();
            if (targetUrl && client.navigate) {
              client.navigate(targetUrl);
            }
            return;
          }
        }
      }
      if (self.clients.openWindow) {
        return self.clients.openWindow(targetUrl);
      }
    })
  );
});