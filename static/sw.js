/* Service worker DocEdit : met l'interface en cache pour un démarrage rapide.
   Les documents (API) passent toujours par le réseau. */
const CACHE = "docedit-v1";
const SHELL = ["/", "/static/style.css?v=1", "/static/app.js?v=1", "/manifest.webmanifest",
  "/static/icons/icon-192.png", "/static/icons/icon-512.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin || url.pathname.startsWith("/api/")) return;
  // réseau d'abord (toujours la dernière version), cache si l'ordinateur ne répond pas
  e.respondWith(
    fetch(e.request).then(res => {
      const copy = res.clone();
      if (res.ok) caches.open(CACHE).then(c => c.put(e.request, copy));
      return res;
    }).catch(() => caches.match(e.request).then(r => r || caches.match("/")))
  );
});
