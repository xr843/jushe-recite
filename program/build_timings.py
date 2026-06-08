#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把所有 aligned_<品>.json 合并成前端用的 timings.js。

前端通过 <script src="timings.js"> 加载（与 verses.js 同款），避免 file://
下 fetch 本地 json 的 CORS 限制。每颂映射到 {file, start, end}：
  - file：该颂音频所在的 mp3（序分 3 偈录在 1.界品.mp3 里，故映射到界品音频）。
  - start/end：来自强制对齐结果。

用法：
  .venv/bin/python build_timings.py      # 扫描 aligned_*.json 生成 timings.js
对齐每跑完一品后重跑本脚本，timings.js 即增量纳入该品。
"""
import json, glob
from pathlib import Path

HERE = Path(__file__).resolve().parent

# 品全名 -> mp3 文件。序分 3 偈录在界品音频开头，单列处理。
PIN_AUDIO = {
    "序分": "1.界品.mp3",
    "界品": "1.界品.mp3", "根品": "2.根品.mp3", "世间品": "3.世间品.mp3", "业品": "4.业品.mp3",
    "随眠品": "5.随眠品.mp3", "贤圣品": "6.贤圣品.mp3", "智品": "7.智品.mp3", "定品": "8.定品.mp3",
}


def main():
    timings = {}
    pins_done = []
    for path in sorted(HERE.glob("aligned_*.json")):
        verses = json.loads(path.read_text(encoding="utf-8"))
        n = 0
        for v in verses:
            file = PIN_AUDIO.get(v["pin"])
            if not file:
                print(f"  ! 未知品名 {v['pin']}（{v['id']}），跳过")
                continue
            timings[v["id"]] = {
                "file": file,
                "start": v["start"],
                "end": v["end"],
            }
            n += 1
        pins_done.append(f"{path.name}({n})")

    out = HERE / "timings.js"
    body = json.dumps(timings, ensure_ascii=False, indent=0)
    out.write_text(
        "// 自动生成，请勿手动编辑。源：aligned_*.json（强制对齐结果）。\n"
        "// 重新生成：.venv/bin/python build_timings.py\n"
        "window.TIMINGS = " + body + ";\n",
        encoding="utf-8",
    )
    print(f"  合并 {len(timings)} 颂 → timings.js")
    print(f"  来源：{', '.join(pins_done) if pins_done else '无 aligned_*.json'}")


if __name__ == "__main__":
    main()
