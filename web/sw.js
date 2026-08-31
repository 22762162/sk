const CACHE = "sanjian-shell-v8";
const SHELL = [
  "/", "/manifest.webmanifest", "/static/app.css", "/static/app.js",
  "/static/icons/icon.svg", "/static/icons/icon-192.png", "/static/icons/icon-512.png",
  "/static/icons/icon-maskable-512.png"
];

self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", event => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin) return;

  // 私密 API 由页面按需写入本机 localStorage；绝不进入共享的 Service Worker Cache。
  if (url.pathname.startsWith("/api/")) {
    event.respondWith(fetch(request));
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(fetch(request).catch(() => caches.match("/")));
    return;
  }

  // 联网时优先取最新壳文件，避免发布后手机仍长期命中旧 JS/CSS；断网才回退缓存。
  event.respondWith(
    fetch(request).then(response => {
      if (response.ok) caches.open(CACHE).then(cache => cache.put(request, response.clone()));
      return response;
    }).catch(() => caches.match(request))
  );
});
