#!/usr/bin/env python3
"""Build `presets/plot-full/messages.jsonl` and the scepter dossier.

两个来源，两个产物 —— 同一份语料、同一次运行：

来源 A（→ messages.jsonl）
    八卷剧情原文 `lore/story/amphoreus_wiki/amphoreus_{3.0..3.7}.md` 里**所有含 `>>>`
    的行**都属于终端内容。原文照抄，只去掉排版标记（`*（旁白）`、斜体 `*`、
    `{{颜色|…}}` 模板），保留 `>>>` 前缀与 `█` 遮蔽符。按「章节 + 归一化文本」
    去重，同一句在多卷重复时只留最早那次。
    3.0–3.3 的原卷**一条 `>>>` 都没有**：本构建器不补位、不借帧，该段终端因此为 0。

来源 B（→ messages.jsonl）
    `lore/story/wiki_structured/terminals_wiki.jsonl` 里 `page == "Δ-me13.exe"` 的
    权杖档案页：取 `terminal_prompt / terminal_line / bracket / redacted` 四类，
    外加「对话日志」段里的行。这些行没有逐行帧位 —— 能对上「永劫回归#N」的走
    loop→frame 映射，其余写 `frame: null` + `require_event`（该页被翻开的那一拍）。

来源 C（→ lore/D6_terminal/scepter_dossier.jsonl）
    同一页的 467 条原文解析成结构化档案：`==…==` 标题不进正文，只做 `section`
    路径；`进度：N%` 单独标 `kind: "progress"`。

帧分配
    既有手写条目原样保留（`frame_source: "anchor"`）。本脚本生成的条目按章排：
    章锚点取 `events.jsonl` 里该章已有的事件帧，N 条按原文行号顺序线性铺在锚点
    之前（`frame_source: "projected"`），钉在章锚点事件上的那条记 `"anchor"`；
    带「永劫回归#N」且官方锚点给了数字帧的，直接用 loop→frame 映射
    （`frame_source: "loop"`）。`official_anchors.jsonl` 里的帧一律 `UNKNOWN`，
    故当前这条分支不会命中。

幂等：同一输入连跑两次输出逐字节相同。

    python tools/lore_build/build_terminal_messages.py
    python tools/lore_build/build_terminal_messages.py --check
    python tools/lore_build/build_terminal_messages.py --out /tmp/messages.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError):
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WIKI_DIR = os.path.join(ROOT, "lore", "story", "amphoreus_wiki")
TERMINALS_WIKI = os.path.join(
    ROOT, "lore", "story", "wiki_structured", "terminals_wiki.jsonl")
TRIGGERS = os.path.join(ROOT, "lore", "D6_terminal", "triggers.json")
OFFICIAL_ANCHORS = os.path.join(ROOT, "lore", "D5_loops", "official_anchors.jsonl")
EVENTS = os.path.join(ROOT, "presets", "plot-full", "events.jsonl")
OUT = os.path.join(ROOT, "presets", "plot-full", "messages.jsonl")
DOSSIER = os.path.join(ROOT, "lore", "D6_terminal", "scepter_dossier.jsonl")

VERSIONS = ("3.0", "3.1", "3.2", "3.3", "3.4", "3.5", "3.6", "3.7")

#: 每章的锚点：用 events.jsonl 里已经存在的事件名，而不是自造帧号。
CHAPTER_ANCHORS = {
    "3.0": "nikador_felled",
    "3.1": "mydei_ascends",
    "3.2": "two_titans_fall",
    "3.3": "anaxa_proves",
    "3.4": "aglaea_exits",
    "3.5": "cipher_falls",
    "3.6": "elysian_reunion",
    "3.7": "page_eternal",
}

#: 章节帧段：用来把既有（手写）消息计入该章，也用来报告各章条数。
#: 段界取相邻两章的锚点帧，末端开放。
CHAPTER_RANGES = {
    "3.0": (0, 12000),
    "3.1": (12001, 16000),
    "3.2": (16001, 18400),
    "3.3": (18401, 23000),
    "3.4": (23001, 30000),
    "3.5": (30001, 36000),
    "3.6": (36001, 33594260),
    "3.7": (33594261, None),
}

#: 权杖档案页在 terminals_wiki.jsonl 里的页名。
DOSSIER_PAGE = "Δ-me13.exe"

#: 档案页里属于「终端口吻」的四类文本；其余（page_text）只进档案。
TERMINAL_TEXT_KINDS = ("terminal_prompt", "terminal_line", "bracket", "redacted")

#: 档案页里要额外抽出来的段落（对话原文）。
DIALOG_SECTION = "对话日志"

#: wiki 片段类别 -> 终端 kind（apps/terminal.py 的 KINDS 子集）。
KIND_BY_TEXT_KIND = {
    "terminal_prompt": "log",
    "terminal_line": "log",
    "bracket": "status",
    "redacted": "warn",
}

#: 没有帧位的档案行挂在这一拍上（《如我所书》/档案页被翻开的那一刻）。
UNFRAMED_EVENT = "tomb_secret"

#: 生成行的 `source` 前缀：重跑时据此把上一次生成的行整批重算。
GENERATED_PREFIX = "S-024:"

#: 上一版构建器写下的标记，同样视为可重算的行。
LEGACY_GENERATED = ("wiki",)

#: 手写条目（没有原文行号）的 `source` 标记。
KEPT_SOURCE = "preset:plot-full"

#: 档案条目 id 前缀。
DOSSIER_ID = "DOS-%03d"

#: `{{颜色|描述1|正文}}` 这类模板：只留最后一个字段。
_TEMPLATE = re.compile(r"\{\{([^{}]*)\}\}")
_HEADING = re.compile(r"^(=+)(.+?)\1$")
_LOOP = re.compile(r"永劫回归#(\d+)")


def _jsonl(path, with_lines=False):
    rows = []
    if not path or not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if with_lines and isinstance(row, dict):
                row["_line"] = ln
            rows.append(row)
    return rows


def _norm(text):
    """归一化：去模板、折叠空白。只用于比较与去重，不改原文语义。"""
    text = _TEMPLATE.sub(lambda m: m.group(1).split("|")[-1], str(text or ""))
    return " ".join(text.split())


def _event_frames(rows):
    """payload.event -> 最早帧；只认 payload 里真有的 event。"""
    out = {}
    for row in rows:
        name = (row.get("payload") or {}).get("event")
        frame = row.get("frame")
        if not name or not isinstance(frame, int) or isinstance(frame, bool):
            continue
        if name not in out or frame < out[name]:
            out[name] = frame
    return out


def _chapter_of_frame(frame):
    """帧 -> 章节（按 CHAPTER_RANGES）；无帧或越界返回 None。"""
    if not isinstance(frame, int) or isinstance(frame, bool):
        return None
    for ver in VERSIONS:
        lo, hi = CHAPTER_RANGES[ver]
        if frame >= lo and (hi is None or frame <= hi):
            return ver
    return None


def _generated(row):
    src = str(row.get("source") or "")
    return src.startswith(GENERATED_PREFIX) or src in LEGACY_GENERATED


def _gt_text(line):
    """从一行原文里取出 `>>>` 之后的终端文本（保留前缀与 `█`）。"""
    i = line.find(">>>")
    if i < 0:
        return None
    body = line[i + 3:].lstrip("*").rstrip("*")
    body = _norm(body)
    if not body:
        return None
    return ">>>" + body


def _source_a():
    """八卷里所有含 `>>>` 的行：[(章节, 行号, 文本)]，按卷、按行排好。"""
    out = []
    for ver in VERSIONS:
        path = os.path.join(WIKI_DIR, "amphoreus_%s.md" % ver)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            for ln, line in enumerate(f, 1):
                line = line.rstrip("\r\n")
                if ">>>" not in line:
                    continue
                text = _gt_text(line)
                if text:
                    out.append({"chapter": ver, "line": ln, "text": text,
                                "loop": _loop_of(text)})
    return out


def _loop_of(text):
    m = _LOOP.search(text or "")
    return int(m.group(1)) if m else None


def _loop_frames(anchors, triggers=None):
    """轮次 -> 帧：只认语料里明写的数字帧。

    `official_anchors.jsonl` 与 `triggers.json` 都只给轮次和出处，帧号一律
    `UNKNOWN`（客户端没保留），故这张表在本包语料里是空的 —— 拿到数字帧时
    才会用上 `frame_source: "loop"`，否则该段一律按行号插值。
    """
    out = {}
    for row in anchors or ():
        loop, frame = row.get("loop"), row.get("frame")
        if not isinstance(loop, int) or isinstance(loop, bool):
            continue
        if not isinstance(frame, int) or isinstance(frame, bool):
            continue
        if loop not in out or frame < out[loop]:
            out[loop] = frame
    for row in ((triggers or {}).get("triggers") or ()):
        loop, frame = row.get("loop"), row.get("frame")
        if not isinstance(loop, int) or not isinstance(frame, int):
            continue
        if loop not in out or frame < out[loop]:
            out[loop] = frame
    return out


def _load_json(path):
    if not path or not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def _parse_page(rows):
    """把档案页拆成 [(行, section 路径)]；`==…==` 标题只做路径。"""
    stack, out = [], []
    for row in rows:
        text = str(row.get("text") or "").strip()
        m = _HEADING.match(text)
        if m:
            depth = max(len(m.group(1)) - 2, 0)
            stack = stack[:depth]
            stack.append(m.group(2).strip())
            continue
        out.append((row, " / ".join(stack)))
    return out


def _dossier_rows(rows):
    """档案页 -> 结构化条目。标题行不进正文，`进度：N%` 标 progress。"""
    out = []
    for row, section in _parse_page(rows):
        text = _norm(row.get("text"))
        if not text:
            continue
        out.append({
            "id": DOSSIER_ID % (len(out) + 1),
            "section": section,
            "kind": "progress" if text.startswith("进度：") else "text",
            "text": text,
            "text_kind": str(row.get("text_kind") or ""),
            "loop": _loop_of(text),
            "source_url": str(row.get("source_url") or ""),
            "grade": str(row.get("grade") or "B"),
        })
    return out


def _source_b(rows):
    """档案页里属于终端口的行：四类文本 + 对话日志段。"""
    out = []
    for row, section in _parse_page(rows):
        kind = str(row.get("text_kind") or "")
        if kind not in TERMINAL_TEXT_KINDS and DIALOG_SECTION not in section:
            continue
        text = _norm(row.get("text"))
        if not text:
            continue
        out.append({
            "text": text,
            "kind": KIND_BY_TEXT_KIND.get(kind, "log"),
            "line": row["_line"],
            "section": section,
        })
    return out


def _assign(rows, anchor, loop_map, floor, occupied=()):
    """把 N 条铺进 [floor, 章尾]：有 loop→frame 的钉住，其余按序线性插值。

    返回 [(frame, frame_source)]，与 `rows` 等长、帧单调递增。章尾默认就是
    章锚点事件的帧；若手写条目已经占用了这段帧位，整段往前让，宁可不到锚点
    也不与既有条目重合。
    """
    n = len(rows)
    occupied = sorted(occupied or ())
    hi = anchor
    while n:
        hits = [f for f in occupied if hi - n + 1 <= f <= hi]
        if not hits:
            break
        hi = min(hits) - 1
        if hi - n + 1 < floor:
            hi = anchor                    # 挤不下就接受与既有条目同帧
            break
    fixed, last = {}, None
    for i, row in enumerate(rows):
        loop = row.get("loop")
        frame = loop_map.get(loop) if loop is not None else None
        if frame is None or frame < floor or frame > hi:
            continue
        if last is not None and frame <= last:
            continue
        fixed[i] = frame
        last = frame
    lo = hi - n
    for i, frame in fixed.items():
        lo = min(lo, frame - i - 1)
    lo = max(lo, floor - 1)
    accepted, prev_i, prev_f = {}, -1, lo
    for i in sorted(fixed):
        frame = fixed[i]
        if frame - prev_f < i - prev_i or hi - frame < n - 1 - i:
            continue                       # 前后都塞不下，退回插值
        accepted[i] = frame
        prev_i, prev_f = i, frame
    anchors = [(-1, lo)] + sorted(accepted.items()) + [(n, hi)]
    out = [None] * n
    for (i0, f0), (i1, f1) in zip(anchors, anchors[1:]):
        gap = i1 - i0 - 1
        span = f1 - f0
        prev = f0
        for k in range(gap):
            frame = f0 + int(round(span * float(k + 1) / (gap + 1)))
            frame = min(frame, f1 - (gap - k))
            frame = max(frame, prev + 1)
            out[i0 + 1 + k] = (frame, "projected")
            prev = frame
    for i, frame in accepted.items():
        out[i] = (frame, "loop")
    if n:
        out[n - 1] = (hi, "anchor" if hi == anchor else "projected")
    return out


def _rows_a(items, events, loop_map, occupied=()):
    """来源 A -> 消息行：按章去重、按章铺帧。"""
    seen, buckets = set(), {ver: [] for ver in VERSIONS}
    for item in items:
        key = _norm(item["text"])
        if key in seen:
            continue
        seen.add(key)
        buckets[item["chapter"]].append(item)
    out = []
    for ver in VERSIONS:
        rows = buckets[ver]
        if not rows:
            continue
        anchor = events[CHAPTER_ANCHORS[ver]]
        frames = _assign(rows, anchor, loop_map, CHAPTER_RANGES[ver][0] + 1,
                         [f for f in occupied
                          if _chapter_of_frame(f) == ver])
        for row, (frame, source_kind) in zip(rows, frames):
            out.append({
                "frame": frame,
                "kind": "log",
                "text": row["text"],
                "authority": "user",
                "source": "%samphoreus_%s.md#L%d" % (
                    GENERATED_PREFIX, row["chapter"], row["line"]),
                "frame_source": source_kind,
            })
    return out


def _rows_b(items, events, taken):
    """来源 B -> 消息行：无逐行帧位，统一挂 `require_event`。"""
    if UNFRAMED_EVENT not in events:
        raise SystemExit("events.jsonl 缺少事件：%s" % UNFRAMED_EVENT)
    out = []
    for item in items:
        key = _norm(item["text"])
        if key in taken:
            continue
        taken.add(key)
        out.append({
            "frame": None,
            "kind": item["kind"],
            "text": item["text"],
            "authority": "kernel",
            "source": "%sterminals_wiki.jsonl#L%d" % (GENERATED_PREFIX, item["line"]),
            "frame_source": "projected",
            "require_event": UNFRAMED_EVENT,
        })
    return out


def _key(row):
    return (row.get("kind", "log"), _norm(row.get("text")).lstrip(">").strip())


def _merge(kept, generated):
    """手写行原样保留；本脚本产出的行每次重建，再按（kind, 文本）去重。"""
    merged, seen = [], set()
    for row in kept:
        row.setdefault("authority", "user")
        row.setdefault("source", KEPT_SOURCE)
        row.setdefault("frame_source",
                       "anchor" if isinstance(row.get("frame"), int) else "projected")
        merged.append(row)
        seen.add(_key(row))
    for row in generated:
        key = _key(row)
        if key in seen:
            continue
        seen.add(key)
        merged.append(row)
    merged.sort(key=lambda r: (r.get("frame") is None, r.get("frame") or 0))
    return merged


def _render(rows):
    return "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)


def build(out_path=OUT, dossier_path=DOSSIER):
    events = _event_frames(_jsonl(EVENTS))
    missing = sorted(set(CHAPTER_ANCHORS.values()) - set(events))
    if missing:
        raise SystemExit("events.jsonl 缺少章节锚点事件：%s" % ", ".join(missing))

    source = out_path if os.path.exists(out_path) else OUT
    existing = _jsonl(source)
    kept = [row for row in existing if not _generated(row)]
    loop_map = _loop_frames(_jsonl(OFFICIAL_ANCHORS), _load_json(TRIGGERS))

    page = [row for row in _jsonl(TERMINALS_WIKI, with_lines=True)
            if row.get("page") == DOSSIER_PAGE]

    dossier = _dossier_rows(page)
    occupied = [row["frame"] for row in kept
                if isinstance(row.get("frame"), int)
                and not isinstance(row.get("frame"), bool)]
    a_rows = _rows_a(_source_a(), events, loop_map, occupied)
    taken = {_norm(row["text"]) for row in a_rows}
    b_rows = _rows_b(_source_b(page), events, taken)

    rows = _merge(kept, a_rows + b_rows)
    return _render(rows), rows, _render(dossier), dossier


def _counts(rows):
    counts = {ver: 0 for ver in VERSIONS}
    for row in rows:
        chapter = _chapter_of_frame(row.get("frame"))
        if chapter:
            counts[chapter] += 1
    return counts


def main(argv=None):
    ap = argparse.ArgumentParser(description="build plot-full terminal messages")
    ap.add_argument("--out", default=OUT,
                    help="写入路径（默认 presets/plot-full/messages.jsonl）")
    ap.add_argument("--dossier-out", default=DOSSIER,
                    help="权杖档案写入路径（默认 lore/D6_terminal/scepter_dossier.jsonl）")
    ap.add_argument("--check", action="store_true", help="只校验磁盘内容是否已是最新")
    args = ap.parse_args(argv)

    text, rows, dossier_text, dossier = build(args.out, args.dossier_out)
    counts = _counts(rows)
    summary = " · ".join("%s=%d" % (ver, counts[ver]) for ver in VERSIONS)

    if args.check:
        stale = []
        for path, payload in ((args.out, text),
                              (args.dossier_out, dossier_text)):
            current = ""
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    current = f.read()
            if current != payload:
                stale.append(os.path.relpath(path, ROOT))
        if stale:
            print("✗ 终端消息 / 权杖档案已过期：%s" % "、".join(stale))
            print("  重新运行 python tools/lore_build/build_terminal_messages.py")
            return 1
        print("✓ 终端消息已是最新（%s；档案 %d 条）" % (summary, len(dossier)))
        return 0

    for path, payload in ((args.out, text), (args.dossier_out, dossier_text)):
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(payload)
    print("✓ 写入 %s（%s）" % (os.path.relpath(args.out, ROOT), summary))
    print("✓ 写入 %s（%d 条）" % (
        os.path.relpath(args.dossier_out, ROOT), len(dossier)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
