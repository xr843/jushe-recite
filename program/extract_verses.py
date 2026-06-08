#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
俱舍论本颂数据提取脚本
从 docx 提取序分 + 600 个编号颂，输出结构化数据到 verses.js（供 index.html 内联使用）。

解析要点（已据实际数据验证）：
- 品标题：分别X品第N（M颂）  作为分组边界
- 颂：编号——内容。同一段可能连写两颂（如 38——…。39——…），需再切分
- (上)(下) 拆分的颂需按编号合并（根62 / 世间28 / 世间84 / 业60 / 业79）
- 序分：开头无编号的敬礼偈颂，单列为"序分"分组
"""
import zipfile
import re
import json
import sys
from pathlib import Path

# 路径相对脚本所在的 program/ 目录的上一级
ROOT = Path(__file__).resolve().parent.parent
DOCX = ROOT / "文本资料" / "偈颂校对版20230127-各品编号(1).docx"
OUT_JS = Path(__file__).resolve().parent / "verses.js"

# 8 品顺序、名称、对应音频文件、应有颂数
PIN_INFO = [
    ("界品",   "1.界品.mp3",   44),
    ("根品",   "2.根品.mp3",   74),
    ("世间品", "3.世间品.mp3", 99),
    ("业品",   "4.业品.mp3",  131),
    ("随眠品", "5.随眠品.mp3", 69),
    ("贤圣品", "6.贤圣品.mp3", 83),
    ("智品",   "7.智品.mp3",   61),
    ("定品",   "8.定品.mp3",   39),
]
EXPECT = {name: cnt for name, _, cnt in PIN_INFO}
AUDIO = {name: af for name, af, _ in PIN_INFO}

PIN_TITLE_RE = re.compile(r"分别(\S+?)品第.*?（(\d+)颂）")
# 拆出段落中每一个"编号(可带上下标记)——正文"片段
VERSE_TOKEN_RE = re.compile(r"(\d+)(?:（([上下])）)?——([^0-9]*?)(?=\d+(?:（[上下]）)?——|$)")


def extract_paragraphs(docx_path):
    """从 docx 提取非空段落纯文本。"""
    z = zipfile.ZipFile(docx_path)
    xml = z.read("word/document.xml").decode("utf-8")
    paras = re.split(r"</w:p>", xml)
    out = []
    for p in paras:
        texts = re.findall(r"<w:t[^>]*>(.*?)</w:t>", p)
        line = "".join(texts).strip()
        if line:
            out.append(line)
    return out


def split_lines(body):
    """把颂正文按 ，。和空白切成句子数组（去掉句末标点）。
    部分颂在句间误用空格代替逗号（如世间85），故一并按空白切分。"""
    body = body.strip()
    parts = re.split(r"[，。、\s　]+", body)
    return [s for s in (x.strip() for x in parts) if s]


def main():
    if not DOCX.exists():
        sys.exit(f"找不到 docx 文件: {DOCX}")

    paras = extract_paragraphs(DOCX)

    verses = []          # 最终颂列表
    global_no = 0
    cur_pin = None       # 当前品名；None 表示尚未进入正文（序分阶段）
    in_xu = False        # 是否在序分段
    # 临时累积 (上)(下) 颂：键 (pin, localNo) -> verse dict
    pending = {}

    def finalize_pending():
        """把 pending 中已凑齐的上下颂收尾（实际在遇到下一颂时即时合并，这里兜底）。"""
        pass

    for line in paras:
        # 序分标记
        if line == "序分":
            in_xu = True
            continue
        # 品标题 → 切换分组
        m = PIN_TITLE_RE.search(line)
        if m:
            cur_pin = m.group(1) + "品"
            in_xu = False
            pending.clear()
            continue

        # 序分阶段：无编号的敬礼偈，逐段（每段是半偈 4 句中的 2 句，合并相邻两段为一颂）
        if in_xu and "——" not in line:
            lines = split_lines(line)
            if not lines:
                continue
            # 序分每段本身就是两句，两段凑一偈；这里简单地每段作为一条 2 句记录，
            # 但用户的颂是 4 句，序分敬礼偈实际是两两成偈。合并策略：累积到 4 句。
            if verses and verses[-1].get("pin") == "序分" and len(verses[-1]["lines"]) < 4:
                verses[-1]["lines"].extend(lines)
            else:
                global_no += 1
                verses.append({
                    "id": f"序-{global_no}",
                    "pin": "序分",
                    "pinIndex": 0,
                    "localNo": global_no,   # 序分仅 3 颂，与 globalNo 同序，直接复用
                    "globalNo": global_no,
                    "audioFile": "",
                    "lines": lines,
                })
            continue

        # 正文颂：一段里可能含多个 编号——正文
        if cur_pin and "——" in line:
            for tok in VERSE_TOKEN_RE.finditer(line):
                local_no = int(tok.group(1))
                mark = tok.group(2)      # '上' / '下' / None
                body = tok.group(3)
                key = (cur_pin, local_no)

                if mark == "上":
                    # 起一个待合并颂
                    global_no += 1
                    v = {
                        "id": f"{cur_pin[:-1]}-{local_no}",
                        "pin": cur_pin,
                        "pinIndex": [p[0] for p in PIN_INFO].index(cur_pin) + 1,
                        "localNo": local_no,
                        "globalNo": global_no,
                        "audioFile": AUDIO[cur_pin],
                        "lines": split_lines(body),
                    }
                    verses.append(v)
                    pending[key] = v
                elif mark == "下":
                    # 合并到上半
                    if key in pending:
                        pending[key]["lines"].extend(split_lines(body))
                        del pending[key]
                    else:
                        # 兜底：没有上半，单独成颂
                        global_no += 1
                        verses.append({
                            "id": f"{cur_pin[:-1]}-{local_no}",
                            "pin": cur_pin,
                            "pinIndex": [p[0] for p in PIN_INFO].index(cur_pin) + 1,
                            "localNo": local_no,
                            "globalNo": global_no,
                            "audioFile": AUDIO[cur_pin],
                            "lines": split_lines(body),
                        })
                else:
                    global_no += 1
                    verses.append({
                        "id": f"{cur_pin[:-1]}-{local_no}",
                        "pin": cur_pin,
                        "pinIndex": [p[0] for p in PIN_INFO].index(cur_pin) + 1,
                        "localNo": local_no,
                        "globalNo": global_no,
                        "audioFile": AUDIO[cur_pin],
                        "lines": split_lines(body),
                    })

    # ---- 自检 ----
    counts = {}
    for v in verses:
        if v["pin"] == "序分":
            continue
        counts[v["pin"]] = counts.get(v["pin"], 0) + 1

    print("各品颂数自检：")
    ok = True
    for name, _, exp in PIN_INFO:
        got = counts.get(name, 0)
        flag = "✓" if got == exp else "✗"
        if got != exp:
            ok = False
        print(f"  {flag} {name}: 应 {exp} 实际 {got}")
    total_main = sum(counts.values())
    xu_count = sum(1 for v in verses if v["pin"] == "序分")
    print(f"正文合计: {total_main} (应 600)   序分: {xu_count} 偈")
    if total_main != 600:
        ok = False

    # 句数检查：每个正文颂应为 4 句
    bad_lines = [v["id"] for v in verses if v["pin"] != "序分" and len(v["lines"]) != 4]
    if bad_lines:
        print(f"⚠ 非 4 句的颂: {bad_lines}")

    if not ok:
        sys.exit("✗ 自检未通过，请检查解析规则。")

    # ---- 输出 verses.js ----
    js = "// 自动生成，请勿手动编辑。源：偈颂校对版20230127-各品编号(1).docx\n"
    js += "const PIN_LIST = " + json.dumps(
        [{"name": n, "audio": a, "count": c} for n, a, c in PIN_INFO],
        ensure_ascii=False,
    ) + ";\n"
    js += "const VERSES = " + json.dumps(verses, ensure_ascii=False, indent=0).replace("\n", "") + ";\n"
    OUT_JS.write_text(js, encoding="utf-8")
    print(f"\n✓ 自检通过，已写出 {OUT_JS} （共 {len(verses)} 条，含序分 {xu_count}）")


if __name__ == "__main__":
    main()
