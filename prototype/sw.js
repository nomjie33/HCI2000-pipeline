// Service worker: precache every file so the installed app runs with no network (proposal 4.4
// "runs locally with no network connection, so there is no loading delay").
//
// When you change ANY file in prototype/, bump CACHE_VERSION (and appVersion in data/study.json).
// Installed phones fetch the new version the next time the app is opened online; it takes over
// after the app is closed and reopened. Export data before updating.

const CACHE_VERSION = "nav-study-v1.0.0";

const FILES = [
  "./",
  "index.html",
  "manifest.webmanifest",
  "css/app.css",
  "data/study.json",
  "data/tree.csv",
  "icons/icon-192.png",
  "icons/icon-512.png",
  "js/app.js",
  "js/export.js",
  "js/logger.js",
  "js/store.js",
  "js/tree.js",
  "js/patterns/common.js",
  "js/patterns/index.js",
  "js/patterns/megamenu.js",
  "js/patterns/practice.js",
  "js/patterns/stub.js",
];

self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE_VERSION).then(c => c.addAll(FILES)));
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE_VERSION).map(k => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

// Cache first: the app never waits on the network once installed.
self.addEventListener("fetch", event => {
  if (event.request.method !== "GET") return;
  event.respondWith(
    caches.match(event.request, { ignoreSearch: true }).then(hit => hit || fetch(event.request).then(res => {
      if (res.ok && new URL(event.request.url).origin === location.origin) {
        const copy = res.clone();
        caches.open(CACHE_VERSION).then(c => c.put(event.request, copy));
      }
      return res;
    })),
  );
});
