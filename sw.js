// jushe-recite service worker
// 策略：壳层（HTML/JS/icons/manifest）走 stale-while-revalidate；
// mp3 音频绕过 SW，让浏览器原生 HTTP cache + Range 处理（避免 Cache API 对 206 部分响应处理不当）。

const CACHE_NAME = 'jushe-recite-v1';
const SHELL_URLS = [
  '/program/index.html',
  '/program/verses.js',
  '/program/timings.js',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
  '/icons/icon-180.png',
  '/manifest.json'
];

self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) =>
      cache.addAll(SHELL_URLS).catch(() => {})
    )
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  // mp3 音频：不接管，让浏览器处理 Range / HTTP cache
  if (url.pathname.endsWith('.mp3')) return;
  // 跨域（理论上不应该有，但保险起见）
  if (url.origin !== self.location.origin) return;

  event.respondWith(
    caches.match(req).then((cached) => {
      const networkFetch = fetch(req).then((resp) => {
        if (resp && resp.ok && resp.type === 'basic') {
          const copy = resp.clone();
          caches.open(CACHE_NAME).then((c) => c.put(req, copy)).catch(() => {});
        }
        return resp;
      }).catch(() => cached);
      return cached || networkFetch;
    })
  );
});
