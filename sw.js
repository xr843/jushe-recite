// 离线 service worker（窄范围，刻意保守）
//
// 设计原则（吸取上一版 SW 把页面卡半残的教训）：
//   1. app-shell（html/js/icons/manifest，<300KB）install 时预缓存 → 无网也能开 app。
//   2. 音频「绝不自动缓存」：单品 mp3 6–16MB，只有用户在设置里点了某品「下载离线」、
//      由页面用 Cache API 显式存入后，本 SW 才从缓存供给；未下载的音频一律走网络
//      （正常 HTTP Range 流式），SW 不插手、不缓存。
//   3. 不拦截导航做花活；shell 走 cache-first + 网络回退，仅此而已。
//   4. skipWaiting + clients.claim，配合页面 controllerchange 触发一次 reload，
//      避免旧 shell 卡住；activate 只清自己的旧 shell 缓存，绝不动音频缓存。
//
// 逃生舱：设置里的「重置应用」会注销本 SW 并清空所有缓存。

const SHELL_CACHE = "jushe-shell-v1";
const AUDIO_CACHE = "jushe-audio-v1"; // 跨 shell 升级保持不变，避免误删用户已下载的品

const SHELL_ASSETS = [
  // 不预缓存 "/"：它 302 跳到 /program/index.html，存的是重定向响应，
  // 用于导航会触发 "redirected response" 报错。start_url 本就是 /program/index.html。
  "/index.html",
  "/program/index.html",
  "/program/verses.js",
  "/program/timings.js",
  "/manifest.json",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
  "/icons/icon-180.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(SHELL_CACHE)
      // 个别资源 404 不应阻断整个 install，逐个 add 容错
      .then((c) => Promise.all(SHELL_ASSETS.map((u) => c.add(u).catch(() => {}))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(
        keys.map((k) => {
          // 只清掉自己的旧 shell 缓存；音频缓存（用户下载的品）一律保留
          if (k !== SHELL_CACHE && k !== AUDIO_CACHE) return caches.delete(k);
        })
      );
      await self.clients.claim();
    })()
  );
});

function isAudioPath(pathname) {
  // 音频在 /600颂-单品/ 下（请求路径为 URL 编码形式，以 /600 开头），扩展名 .mp3 或 .opus
  return /\.(mp3|opus)$/i.test(pathname) && pathname.indexOf("/600") === 0;
}

// 从缓存的完整响应里，按请求的 Range 头切出 206 partial（音频元素 seek 必需）。
// 无 Range 时返回完整 200。
async function serveFromCache(request, cached) {
  // 用 Blob 而非 ArrayBuffer：blob.slice 惰性，不把整品（最多 16MB）读进内存，
  // 媒体元素 seek 时会发很多小 Range 请求，这点对移动端很关键。
  const blob = await cached.blob();
  const total = blob.size;
  const range = request.headers.get("range");
  // .opus → audio/ogg，否则 audio/mpeg
  const ctype = /\.opus(\?|$)/i.test(request.url) ? "audio/ogg" : "audio/mpeg";
  const baseHeaders = { "Content-Type": ctype, "Accept-Ranges": "bytes" };

  if (!range) {
    return new Response(blob, {
      status: 200,
      headers: Object.assign({ "Content-Length": String(total) }, baseHeaders),
    });
  }
  const m = /bytes=(\d*)-(\d*)/.exec(range);
  let start, end;
  if (m && m[1] === "" && m[2] !== "") {
    // 后缀形式 bytes=-N：取最后 N 字节（Safari 偶尔探测文件尾部 metadata）
    const n = parseInt(m[2], 10);
    start = isNaN(n) ? 0 : Math.max(0, total - n);
    end = total - 1;
  } else {
    start = m && m[1] ? parseInt(m[1], 10) : 0;
    end = m && m[2] ? parseInt(m[2], 10) : total - 1;
  }
  if (isNaN(start)) start = 0;
  if (isNaN(end) || end >= total) end = total - 1;
  if (start > end || start >= total) {
    return new Response(null, {
      status: 416,
      headers: { "Content-Range": "bytes */" + total },
    });
  }
  const slice = blob.slice(start, end + 1);
  return new Response(slice, {
    status: 206,
    headers: Object.assign(
      {
        "Content-Range": "bytes " + start + "-" + end + "/" + total,
        "Content-Length": String(slice.size),
      },
      baseHeaders
    ),
  });
}

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  let url;
  try {
    url = new URL(req.url);
  } catch (e) {
    return;
  }
  if (url.origin !== self.location.origin) return; // 第三方请求不管

  if (isAudioPath(url.pathname)) {
    event.respondWith(
      (async () => {
        const cache = await caches.open(AUDIO_CACHE);
        const cached = await cache.match(url.href, { ignoreVary: true });
        if (cached) return serveFromCache(req, cached); // 已下载 → 离线供给
        return fetch(req); // 未下载 → 走网络（正常 Range 流式），不缓存
      })()
    );
    return;
  }

  // app-shell / 其它同源 GET：stale-while-revalidate。
  // 先给缓存（保证离线可开 + 秒开），同时后台拉新存回 SHELL_CACHE，下次加载即更新——
  // 这样只改了 HTML/JS 而没改 sw.js 时，用户也不会被钉死在旧壳上（当年自杀脚本要治的病）。
  // 无缓存时走网络；网络失败且是导航请求则回退到 app 壳。
  event.respondWith(
    caches.open(SHELL_CACHE).then((cache) =>
      cache.match(req).then((hit) => {
        const network = fetch(req)
          .then((resp) => {
            // 只回存成功的同源完整响应（200 basic），不存重定向/opaque/错误
            if (resp && resp.status === 200 && resp.type === "basic") {
              cache.put(req, resp.clone()).catch(() => {});
            }
            return resp;
          })
          .catch(() => null);
        return (
          hit ||
          network.then((resp) =>
            resp ||
            (req.mode === "navigate" ? cache.match("/program/index.html") : Response.error())
          )
        );
      })
    )
  );
});
