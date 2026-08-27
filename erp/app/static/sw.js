/* JTCS ERP service worker — cache shell assets so the app opens on phones/tablets. */
const CACHE = "jtcs-erp-shell-v1";
const PRECACHE = [
  "/static/css/erp.css",
  "/static/js/platform.js",
  "/static/icons/jtcs-app.svg",
];

self.addEventListener("install", function (event) {
  event.waitUntil(
    caches.open(CACHE).then(function (cache) {
      return cache.addAll(PRECACHE).catch(function () {
        return undefined;
      });
    }).then(function () {
      return self.skipWaiting();
    })
  );
});

self.addEventListener("activate", function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(
        keys.filter(function (key) { return key !== CACHE; }).map(function (key) {
          return caches.delete(key);
        })
      );
    }).then(function () {
      return self.clients.claim();
    })
  );
});

self.addEventListener("fetch", function (event) {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.indexOf("/api/") === 0 || url.pathname.indexOf("/login") === 0) return;

  const isAsset =
    url.pathname.indexOf("/static/") === 0 ||
    /\.(?:css|js|png|svg|woff2)$/i.test(url.pathname);

  if (isAsset) {
    event.respondWith(
      caches.match(req).then(function (cached) {
        const fetched = fetch(req).then(function (res) {
          if (res && res.ok) {
            const copy = res.clone();
            caches.open(CACHE).then(function (cache) { cache.put(req, copy); });
          }
          return res;
        }).catch(function () { return cached; });
        return cached || fetched;
      })
    );
    return;
  }

  event.respondWith(
    fetch(req).catch(function () {
      return caches.match(req);
    })
  );
});
