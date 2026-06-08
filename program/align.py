#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
强制对齐：把整品 mp3 对齐到该品的逐颂文本，输出每颂 [start, end] 时间戳。

原理：
1. faster-whisper 转录音频，拿到「词级」时间戳（每个字/词 + start/end）。
2. 把识别出的字序列 与 标准文本字序列 做序列对齐（最长公共子序列 / 双指针）。
   因为标准文本是已知的，识别错字不影响——我们只借识别的时间轴。
3. 按标准文本里"每颂多少字"切分，得到每颂的起止时间。

用法：
  .venv/bin/python align.py <品名>           # 单品，如 界
  .venv/bin/python align.py --all            # 全部 8 品
输出：aligned_<品名>.json （含每颂 start/end/字数/质检标记）
"""
import sys, json, re, os, difflib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
AUDIO_DIR = ROOT / "600颂-单品"
VERSES_JS = HERE / "verses.js"

PIN_AUDIO = {
    "界": "1.界品.mp3", "根": "2.根品.mp3", "世间": "3.世间品.mp3", "业": "4.业品.mp3",
    "随眠": "5.随眠品.mp3", "贤圣": "6.贤圣品.mp3", "智": "7.智品.mp3", "定": "8.定品.mp3",
}
PIN_FULL = {  # 短名 -> verses.js 里的 pin 全名
    "界": "界品", "根": "根品", "世间": "世间品", "业": "业品",
    "随眠": "随眠品", "贤圣": "贤圣品", "智": "智品", "定": "定品",
}


def load_verses():
    js = VERSES_JS.read_text(encoding="utf-8")
    m = re.search(r"const VERSES = (\[.*\]);", js)
    return json.loads(m.group(1))


def verses_of_pin(all_verses, pin_full):
    vs = [v for v in all_verses if v["pin"] == pin_full]
    vs.sort(key=lambda v: v["globalNo"])
    return vs


def verses_for_audio(all_verses, short):
    """返回某品音频实际对应的颂序列（用于对齐）。
    界品音频 1.界品.mp3 开头约 18s 念的是序分 3 偈（敬礼偈），录在了界品音频里，
    故对齐界品时必须把序分 3 偈前置进标准文本，否则首字即错位、全盘对不齐。
    其余 7 品音频只含本品内容。"""
    vs = verses_of_pin(all_verses, PIN_FULL[short])
    if short == "界":
        xu = verses_of_pin(all_verses, "序分")
        return xu + vs
    return vs


def ffprobe_duration(audio_path):
    """用 ffprobe 取音频时长（秒），失败返回 0。"""
    import subprocess
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(audio_path)],
            capture_output=True, text=True, timeout=30,
        ).stdout.strip()
        return float(out)
    except Exception:
        return 0.0


_model = None
def get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        # large-v3 中文最准；CPU int8 兼顾速度。首次运行会下载模型。
        size = os.environ.get("WHISPER_MODEL", "large-v3")
        print(f"  加载模型 {size} (CPU/int8，首次会下载)…", flush=True)
        threads = int(os.environ.get("WHISPER_THREADS", str(os.cpu_count() or 8)))
        _model = WhisperModel(size, device="cpu", compute_type="int8", cpu_threads=threads)
    return _model


_cc = None
def to_simplified(s):
    """繁体 → 简体。faster-whisper 中文常输出繁体，需转简体才能与原文逐字比对。"""
    global _cc
    if _cc is None:
        try:
            from opencc import OpenCC
            _cc = OpenCC("t2s")
        except Exception:
            _cc = False  # 没装就跳过转换
    return _cc.convert(s) if _cc else s


def to_pinyin_seq(chars):
    """把汉字列表逐字转成无声调拼音 token 列表，长度与输入一一对应。
    念诵腔 + 佛经专名导致 whisper 大量「同音错字」（择→则、惑→祸、慧→会、冥→民…），
    逐字相等比对几乎全错。改在拼音层做序列对齐，同音字即可命中，锚点密度大幅提升。
    标准文本与识别文本都过同一函数，保证两侧拼音口径一致。"""
    from pypinyin import lazy_pinyin, Style
    out = []
    for ch in chars:
        # 逐字转换：每个汉字恰好得到一个拼音 token，保持索引一一对应。
        py = lazy_pinyin(ch, style=Style.NORMAL, errors=lambda x: x)
        out.append(py[0] if py else ch)
    return out


def transcribe_chars(audio_path, total_dur=0, cache_key="", initial_prompt=None):
    """转录 → 返回字级列表 [(char, start, end), ...]，边转边报进度。
    结果缓存到 trans_<key>.json，重跑对齐时直接复用，避免重跑 Whisper。
    initial_prompt：把该品标准文本前若干字喂给 whisper 作语言偏置，引导其识别
    向正确的佛经专名靠拢（如「择灭」「随眠」「俱舍」），减少同音错字。"""
    cache = HERE / f"trans_{cache_key}.json"
    if cache_key and cache.exists():
        print(f"  复用转录缓存 {cache.name}", flush=True)
        raw = json.loads(cache.read_text(encoding="utf-8"))
        return [(c[0], c[1], c[2]) for c in raw]

    model = get_model()
    segments, info = model.transcribe(
        str(audio_path), language="zh", word_timestamps=True,
        vad_filter=True, vad_parameters=dict(min_silence_duration_ms=200),
        initial_prompt=initial_prompt,
    )
    chars = []
    last_pct = -10
    for seg in segments:
        if total_dur:
            pct = int(seg.end / total_dur * 100)
            if pct >= last_pct + 10:
                print(f"    转录进度 ~{pct}% ({seg.end:.0f}/{total_dur:.0f}s)", flush=True)
                last_pct = pct
        if not seg.words:
            continue
        for w in seg.words:
            tok = re.sub(r"\s", "", w.word)
            tok = to_simplified(tok)  # 繁→简
            if not tok:
                continue
            # word 可能是多字，按时间均分到每个字
            n = len(tok)
            dur = (w.end - w.start) / n if n else 0
            for i, ch in enumerate(tok):
                if re.match(r"[一-鿿]", ch):  # 只保留汉字
                    chars.append((ch, w.start + i * dur, w.start + (i + 1) * dur))
    if cache_key:
        cache.write_text(json.dumps(chars, ensure_ascii=False), encoding="utf-8")
        print(f"  转录缓存已存 {cache.name}", flush=True)
    return chars


def align(std_chars, rec):
    """
    把标准字序列 std_chars 对齐到识别结果 rec=[(ch,s,e),...]。
    返回 mapping[i] = (start,end) 或 None，对应 std_chars[i] 的时间。
    在「拼音」层做全局序列对齐（最长公共子序列）：whisper 的同音错字在拼音上
    与标准字相等，故能命中，比逐字字面比对的锚点多一个量级。
    """
    n = len(std_chars)
    mapping = [None] * n
    rec_chars = [r[0] for r in rec]
    std_py = to_pinyin_seq(std_chars)
    rec_py = to_pinyin_seq(rec_chars)
    sm = difflib.SequenceMatcher(a=std_py, b=rec_py, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for off in range(i2 - i1):
                r = rec[j1 + off]
                mapping[i1 + off] = (r[1], r[2])
    return mapping


def interpolate(mapping, rec):
    """对 None 的位置用相邻锚点线性插值，保证每颂能拿到边界。"""
    n = len(mapping)
    # 收集锚点 (索引, 时间中点)
    anchors = [(i, (mp[0] + mp[1]) / 2) for i, mp in enumerate(mapping) if mp]
    if not anchors:
        return [(0, 0)] * n
    times = [None] * n
    for i, mp in enumerate(mapping):
        if mp:
            times[i] = mp
    # 头部
    first_i, first_t = anchors[0]
    for i in range(first_i):
        times[i] = mapping[first_i] if False else (rec[0][1], rec[0][1])
    # 中间插值
    for a in range(len(anchors) - 1):
        i0, _ = anchors[a]; i1, _ = anchors[a + 1]
        s0 = times[i0][1]; s1 = times[i1][0]
        gap = i1 - i0
        for k in range(i0 + 1, i1):
            frac = (k - i0) / gap
            t = s0 + (s1 - s0) * frac
            times[k] = (t, t)
    # 尾部
    last_i, _ = anchors[-1]
    end_t = rec[-1][2]
    for i in range(last_i + 1, n):
        times[i] = (end_t, end_t)
    return times


def process_pin(short, all_verses, audio_dur_cache={}):
    pin_full = PIN_FULL[short]
    audio = AUDIO_DIR / PIN_AUDIO[short]
    vs = verses_for_audio(all_verses, short)
    extra = " (含序分 3 偈)" if short == "界" else ""
    print(f"\n=== {pin_full}：{len(vs)} 颂{extra}，音频 {audio.name} ===", flush=True)

    # 标准字序列（拼接所有颂，记录每颂字数）
    std_chars = []
    counts = []
    for v in vs:
        s = "".join(v["lines"])
        std_chars.extend(list(s))
        counts.append(len(s))

    # initial_prompt：取标准文本前 ~120 字作语言偏置，引导 whisper 识别佛经专名。
    # whisper 提示窗约 224 token，中文按字粗略截断到安全长度。
    prompt = "".join(std_chars)[:120]

    print("  转录中…", flush=True)
    dur = ffprobe_duration(audio)
    rec = transcribe_chars(audio, total_dur=dur, cache_key=short, initial_prompt=prompt)
    print(f"  识别到 {len(rec)} 个汉字，标准文本 {len(std_chars)} 字", flush=True)

    mapping = align(std_chars, rec)
    matched = sum(1 for x in mapping if x)
    print(f"  拼音对齐命中 {matched}/{len(std_chars)} 字 ({matched*100//len(std_chars)}%)", flush=True)
    times = interpolate(mapping, rec)

    # 按每颂字数切出 [start,end]
    out = []
    pos = 0
    for v, c in zip(vs, counts):
        seg = times[pos:pos + c]
        pos += c
        start = seg[0][0]
        end = seg[-1][1]
        out.append({
            "id": v["id"], "pin": v["pin"], "localNo": v["localNo"], "globalNo": v["globalNo"],
            "start": round(start, 2), "end": round(end, 2),
            "dur": round(end - start, 2), "nchars": c,
            "text": "".join(v["lines"]),
        })

    # 质检：标记异常颂
    durs = sorted(o["dur"] for o in out)
    med = durs[len(durs) // 2] if durs else 0
    for o in out:
        flags = []
        if o["dur"] < med * 0.4: flags.append("过短")
        if o["dur"] > med * 2.2: flags.append("过长")
        if o["dur"] <= 0.3: flags.append("无时长")
        o["flag"] = ",".join(flags)
    bad = [o for o in out if o["flag"]]
    print(f"  中位时长 {med:.1f}s，需复核 {len(bad)} 颂: " +
          (", ".join(f'{o["localNo"]}({o["flag"]})' for o in bad) if bad else "无"))

    outpath = HERE / f"aligned_{short}.json"
    outpath.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  → {outpath.name}")
    return out


def main():
    args = sys.argv[1:]
    all_verses = load_verses()
    if not args:
        print("用法: align.py <品名(界/根/...)> 或 --all"); return
    targets = list(PIN_FULL.keys()) if args[0] == "--all" else args
    for t in targets:
        if t not in PIN_FULL:
            print(f"未知品名: {t}（可选: {'/'.join(PIN_FULL)}）"); continue
        process_pin(t, all_verses)


if __name__ == "__main__":
    main()
