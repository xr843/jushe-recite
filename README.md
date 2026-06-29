# 俱舍论本颂背诵辅助 / Jushe Recite

按品浏览俱舍论本颂，配合念诵音频逐句跟诵，再用遮罩自测 + 间隔复习（SRS）把 603 颂背下来。纯静态 HTML/JS，无构建步骤，可离线，数据全在本地。

A web app to memorize the root verses of 俱舍论 (Abhidharmakośa): browse by chapter, chant along with synchronized audio (line-by-line highlight), then drill them with cloze self-tests and a lightweight spaced-repetition scheduler. Pure static HTML/JS — no build step, works offline, all data stays on your device.

**在线 / Live：<https://jushe-recite.pages.dev>**

## 功能 / Features

### 浏览与跟诵
- 9 个分组（序分 + 8 品，共 603 颂）目录式浏览，左栏一键跳转
- 跟诵：播放念诵音频，**逐句高亮**当前所诵的句子，正文随音频自动滚动
- 单颂播放 / 单颂循环 / 列表连播 / 列表循环 / 真暂停-续播（保留位置）
- 锁屏 / 通知栏播放控制（Media Session）；音量、播放速度可调
- **检索**：按正文跨句搜索，命中高亮；`#verse-<id>` 深链可分享 / 书签定位
- 键盘快捷键：空格=连播/暂停、←/→=上/下颂、`/`=聚焦搜索

### 背诵训练
- **遮罩自测**：遮住正文（露首字 / 全遮），凭记忆背 → 「揭晓」对答案（显文 + 放参考音）→ 自评 忘 / 会
- **间隔复习（SRS-lite）**：会 → 间隔渐长，忘 → 当场重练；每日新颂上限防贪多；「练习」标签每天给你该复习的颂
- **熟练度**：未学 / 学习中 / 已熟（复习间隔 ≥ 21 天），「只看未背熟」筛选，顶部「已熟 X / 603」进度
- **自由练习**（不受每日上限，随时选、随时练）：
  - 「今日背诵」勾选清单 →「▶ 练习这 N 颂」
  - 「全部颂」里每品 →「▶ 练本品」
  - 搜索结果 →「▶ 练习这 N 条结果」
- **进度备份**：设置里「导出 / 导入」JSON（熟练度等全在 localStorage，清缓存 / 换设备前记得导出）

### 离线 / PWA
- 可「添加到主屏幕」安装为 App
- 设置里按品「下载离线」，下载后该品可无网背诵
- app 壳离线可开；service worker 窄范围缓存（app-shell + 用户下载的音频），不拦花活

## 数据与隐私 / Data & privacy

全部数据（选颂、熟练度、复习进度、设置）只存在你浏览器的 localStorage，**不上传任何服务器**。换设备或清缓存前用设置里的「导出进度」备份，到新环境「导入进度」即可。无账号、无后端、无追踪。

## 本地开发 / Local dev

```bash
cd program
python3 serve.py            # 默认 8777 端口；支持 HTTP Range（浏览器精确 seek 偈颂起点必需）
# 浏览器打开 http://localhost:8777/program/index.html
```

部署到 Cloudflare Pages 后，`serve.py` 仅本地开发用 — CDN 原生支持 Range。整个 app（浏览 / 跟诵 / 检索 / 离线 / 背诵训练）都在 `program/index.html` 一个文件里，纯 vanilla JS、无构建、无依赖。

## 目录结构 / Layout

```
index.html               根入口，重定向到 /program/
manifest.json sw.js      PWA：清单 + service worker（窄范围离线缓存）
program/
  index.html             整个单页 app（浏览 / 跟诵 / 检索 / 训练 / 离线，纯 vanilla 无构建）
  verses.js              偈颂文本（由 extract_verses.py 从 docx 生成）
  timings.js             逐颂时间戳（由 build_timings.py 从 aligned_*.json 合并）
  aligned_*.json         强制对齐结果（保留以便重新生成 timings.js）
  trans_*.json           Whisper 转写缓存（重跑对齐时复用）
  extract_verses.py      从 docx 重新生成 verses.js
  align.py               单品强制对齐脚本（faster-whisper 字级时间戳 → 逐颂 [start,end]）
  build_timings.py       合并 aligned_*.json → timings.js
  serve.py               本地 HTTP Range 服务（仅开发用）
600颂-单品/*.mp3          8 个品的念诵音频，已 ffmpeg loudnorm 至 -14 LUFS
600颂-单品/*.opus         同上的 Opus 版（48k mono，约省 2/3 体积）；浏览器支持则优先用，否则回退 mp3
文本资料/                  偈颂校对版 docx
```

数据流：`docx → extract_verses.py → verses.js`；`mp3 + verses.js → align.py → aligned_*.json → build_timings.py → timings.js`。

重新生成 Opus（改了 mp3 后）：

```bash
cd 600颂-单品
for f in *.mp3; do ffmpeg -y -i "$f" -c:a libopus -b:a 48k -ac 1 -application audio "${f%.mp3}.opus"; done
```

## 致谢 / Acknowledgements

念诵音频由团队同事录制，授权用于公开学习。
Recitation audio recorded by team members, shared for study purposes.

俱舍论本颂为汉传佛教论藏经典文本，公共领域。
The Abhidharmakośa root verses are a classical Chinese Buddhist text in the public domain.

## License

MIT — see [LICENSE](LICENSE).
