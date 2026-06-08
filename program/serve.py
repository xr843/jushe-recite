#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地预览服务器（支持 HTTP Range）。

Python 自带的 http.server 不支持 Range 请求，会一次性返回整个 mp3，导致
浏览器无法可靠地 seek 到每颂起点（强制对齐播放的核心动作）。这里用
RangeRequestHandler 处理 Range，从仓库根目录提供静态文件。

用法：
  .venv/bin/python serve.py            # 默认 8777 端口
  .venv/bin/python serve.py 9000       # 指定端口
然后浏览器打开 http://localhost:8777/program/index.html
"""
import sys, os, re
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent)  # 仓库根


class RangeRequestHandler(SimpleHTTPRequestHandler):
    """在 SimpleHTTPRequestHandler 基础上支持单段 Range（够浏览器 seek 用）。"""

    def end_headers(self):
        self.send_header("Accept-Ranges", "bytes")
        super().end_headers()

    def send_head(self):
        rng = self.headers.get("Range")
        if not rng:
            return super().send_head()
        m = re.match(r"bytes=(\d*)-(\d*)", rng.strip())
        if not m:
            return super().send_head()

        path = self.translate_path(self.path)
        if not os.path.isfile(path):
            return super().send_head()  # 交给父类返回 404
        size = os.path.getsize(path)
        start = int(m.group(1)) if m.group(1) else 0
        end = int(m.group(2)) if m.group(2) else size - 1
        end = min(end, size - 1)
        if start > end or start >= size:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.end_headers()
            return None

        f = open(path, "rb")
        f.seek(start)
        self.send_response(206)
        ctype = self.guess_type(path)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        self._range = (start, end)
        return f

    def copyfile(self, source, outputfile):
        rng = getattr(self, "_range", None)
        if not rng:
            return super().copyfile(source, outputfile)
        start, end = rng
        remaining = end - start + 1
        while remaining > 0:
            chunk = source.read(min(64 * 1024, remaining))
            if not chunk:
                break
            outputfile.write(chunk)
            remaining -= len(chunk)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8777
    handler = partial(RangeRequestHandler, directory=ROOT)
    httpd = ThreadingHTTPServer(("0.0.0.0", port), handler)
    print(f"预览服务器（支持 Range）启动：http://localhost:{port}/program/index.html")
    print(f"根目录：{ROOT}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
