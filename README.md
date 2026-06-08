# 俱舍论本颂背诵辅助 / Kusha Chant Helper

按品浏览俱舍论本颂，勾选今日要背的颂，配合念诵音频自动连播。纯静态 HTML/JS，无构建步骤。

A web app for memorizing 俱舍论 (Abhidharmakośa) root verses with synchronized chant audio. Pure static HTML/JS — no build step.

## 功能 / Features

- 9 个分组（序分 + 8 品，共 ~600 颂）目录式浏览，左栏一键跳转
- 勾选"今日背诵"列表，自动按全局顺序连播，正文区随音频自动滚动
- 单颂播放 / 单颂循环 / 列表连播 / 列表循环 / 真暂停-续播（保留位置）
- 音量、播放速度可调
- 选择状态保存在 localStorage

## 在线使用 / Live

部署在 Cloudflare Pages：将在首次部署后补上链接。

## 本地开发 / Local dev

```bash
cd program
python3 serve.py            # 默认 8777 端口；支持 HTTP Range（浏览器精确 seek 偈颂起点必需）
# 浏览器打开 http://localhost:8777/program/index.html
```

部署到 Cloudflare Pages 后，`serve.py` 仅本地开发用 — CDN 原生支持 Range。

## 目录结构 / Layout

```
program/
  index.html             单页 UI
  verses.js              偈颂文本（由 extract_verses.py 从 docx 生成）
  timings.js             逐颂时间戳（由 build_timings.py 从 aligned_*.json 合并）
  aligned_*.json         强制对齐结果（保留以便重新生成 timings.js）
  trans_*.json           对齐用的转写
  extract_verses.py      从 docx 重新生成 verses.js
  align.py               单品强制对齐脚本
  build_timings.py       合并 aligned_*.json → timings.js
  serve.py               本地 HTTP Range 服务
600颂-单品/*.mp3          8 个品的念诵音频，已 ffmpeg loudnorm 至 -14 LUFS
文本资料/                  偈颂校对版 docx
```

## 致谢 / Acknowledgements

念诵音频由团队同事录制，授权用于公开学习。
Recitation audio recorded by team members, shared for study purposes.

俱舍论本颂为汉传佛教论藏经典文本，公共领域。
The Abhidharmakośa root verses are a classical Chinese Buddhist text in the public domain.

## License

MIT — see [LICENSE](LICENSE).
