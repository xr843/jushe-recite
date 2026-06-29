#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从「偈颂白话解.docx」（一张表：科判 | 本颂句 | 白话解）提取每颂的白话解 + 科判路径，
生成前端用的 program/trans.js（window.TRANS = {颂id: {jie, ke}}）。

docx 跨品格式不一致（界品逐句简体，世间品等繁体且两句合并），故：
  - 繁→简（opencc t2s）后再与 verses.js 的简体行匹配；
  - 单元格按空格/全角空格拆成多句；
  - 科判列用 vMerge 向下继承（合并的续行为空 → 沿用上次非空）；
  - 同一颂各句白话解去重相邻重复后拼接（couplet 的解释常重复挂在两句上）。

用法：python3 extract_trans.py <docx路径>
"""
import sys, re, json, zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent

try:
    from opencc import OpenCC
    _cc = OpenCC("t2s")
    t2s = lambda s: _cc.convert(s)
except Exception:
    t2s = lambda s: s   # 没装 opencc 就不转（匹配率会掉）


def norm(s):
    return s.strip().strip("，。、；！？.． 　")


def clean_ke(label):
    # 去掉科判前的判教编号（如「D1 明三界」「B1 正明宗旨」→「明三界」「正明宗旨」）
    return re.sub(r"^[A-Za-z]+\d*\s+", "", label).strip()


def cell_text(tc):
    return "".join(re.findall(r"<w:t(?:\s[^>]*)?>(.*?)</w:t>", tc, re.S)).strip()


def main():
    docx = sys.argv[1] if len(sys.argv) > 1 else str(HERE.parent / "偈颂白话解.docx")
    verses = json.loads(re.search(r"const VERSES = (\[.*?\]);",
                                  (HERE / "verses.js").read_text(encoding="utf-8"), re.S).group(1))
    line2v = {}
    for v in verses:
        for i, ln in enumerate(v["lines"]):
            line2v[norm(ln)] = (v["id"], i)

    xml = zipfile.ZipFile(docx).read("word/document.xml").decode("utf-8", "ignore")
    rows = re.findall(r"<w:tr\b.*?</w:tr>", xml, re.S)

    trans = {}          # vid -> {"lines": {i: jie}, "ke": "科判路径"}
    ke_cols = {}        # 科判列 colIdx -> 最近非空值（vMerge 向下继承）
    for row in rows:
        cells = [t2s(cell_text(c)) for c in re.findall(r"<w:tc\b.*?</w:tc>", row, re.S)]
        # 品分隔行（单格「X品」/「流通分」）：进入新品，重置科判继承
        if len(cells) == 1 and re.fullmatch(r"[一-鿿]{1,3}品|流通分", cells[0].strip()):
            ke_cols = {}
            continue
        # 找「本颂句」单元格：先清掉散落句点（docx 里本颂句夹了 . ／．），再按空格拆句
        bi, hits = None, None
        for idx, c in enumerate(cells):
            pieces = re.split(r"[\s　]+", c.replace(".", "").replace("．", "").strip())
            h = [(p, line2v[norm(p)]) for p in pieces if norm(p) in line2v]
            if h:
                bi, hits = idx, h
                break
        if bi is None:
            continue
        # 本颂句之前的单元格 = 科判，非空则更新继承
        for ci in range(bi):
            val = cells[ci].strip()
            if val:
                ke_cols[ci] = val
        ke_path = " · ".join(clean_ke(ke_cols[ci]) for ci in sorted(ke_cols)
                             if ci < bi and ke_cols.get(ci) and clean_ke(ke_cols[ci]))
        jie = cells[bi + 1].strip() if bi + 1 < len(cells) else ""
        for _, (vid, li) in hits:
            t = trans.setdefault(vid, {"lines": {}, "ke": ke_path})
            if not t["ke"] and ke_path:
                t["ke"] = ke_path
            if jie:
                t["lines"][li] = jie

    # 组装每颂：按句序拼白话解，去掉相邻重复（couplet 重复挂在两句上）
    out = {}
    for v in verses:
        t = trans.get(v["id"])
        if not t:
            continue
        parts = []
        for i in range(len(v["lines"])):
            j = t["lines"].get(i, "")
            if j and (not parts or parts[-1] != j):
                parts.append(j)
        jie = "\n".join(parts)   # 各句释义换行分隔，前端按行显示
        entry = {}
        if jie:
            entry["jie"] = jie
        if t["ke"]:
            entry["ke"] = t["ke"]
        if entry:
            out[v["id"]] = entry

    (HERE / "trans.js").write_text(
        "// 自动生成，请勿手动编辑。源：偈颂白话解.docx（extract_trans.py）。\n"
        "window.TRANS = " + json.dumps(out, ensure_ascii=False) + ";\n",
        encoding="utf-8")

    have_jie = sum(1 for e in out.values() if e.get("jie"))
    have_ke = sum(1 for e in out.values() if e.get("ke"))
    miss = [v["id"] for v in verses if not out.get(v["id"], {}).get("jie")]
    print(f"  共 {len(verses)} 颂；有白话解 {have_jie}，有科判 {have_ke}")
    print(f"  缺白话解 {len(miss)} 颂：{miss[:20]}")
    print(f"  → trans.js")


if __name__ == "__main__":
    main()
