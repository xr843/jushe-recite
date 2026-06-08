// jushe-recite service worker
// 策略：壳层（HTML/JS/icons/manifest）走 stale-while-revalidate；
// mp3 音频绕过 SW，让浏览器原生 HTTP cache + Range 处理（避免 Cache API 对 206 部分响应处理不当）。
// 注：每次代码变更后 bump 一下 CACHE_NAME，旧客户端激活新 SW 时会清掉旧 cache。

const CACHE_NAME = 'jushe-recite-v2';
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
      // 后台拉新版更新缓存（无论是否命中缓存都拉一次）
      const networkPromise = fetch(req).then((resp) => {
        if (resp && resp.ok && resp.type === 'basic') {
          const copy = resp.clone();
          caches.open(CACHE_NAME).then((c) => c.put(req, copy)).catch(() => {});
        }
        return resp;
      });
      if (cached) {
        networkPromise.catch(() => {}); // 后台失败不要变成未处理 reject
        return cached;
      }
      // 无缓存：等网络；若网络也失败，至少返回一个明确的 503 而不是 undefined
      return networkPromise.catch(() =>
        new Response('Service Worker fetch failed', { status: 503, statusText: 'SW offline' })
      );
    })
  );
});
