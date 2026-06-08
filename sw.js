// 自杀脚本 (kill-switch service worker)
// 之前的 SW 给用户造成过 ERR_FAILED 半残状态。决定撤掉 SW，回归"CDN + 浏览器原生 HTTP cache"。
// 此文件部署后：所有装过旧 SW 的浏览器，下次访问会触发此 SW 的 install/activate，自动：
//   1. 删除所有 Cache Storage 条目
//   2. 注销自身
//   3. 通过 clients.navigate 强制刷新已打开的页面（让它们摆脱 SW 控制）

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    try {
      const keys = await caches.keys();
      await Promise.all(keys.map((k) => caches.delete(k)));
    } catch (e) {}
    try {
      await self.registration.unregister();
    } catch (e) {}
    try {
      const clients = await self.clients.matchAll({ type: 'window' });
      clients.forEach((c) => { try { c.navigate(c.url); } catch (e) {} });
    } catch (e) {}
  })());
});

// 没有 fetch 监听 → 任何请求绕开此 SW，直接走网络（== 老 SW 已退场后的正常行为）
