#!/usr/bin/env python3
"""Build the wiki narrative corpus (S-024) into project data files.

Source of truth
    lore/story/amphoreus_wiki/amphoreus_3.0.md … amphoreus_3.7.md
    (BWIKI 剧情原文全量，S-024；.gitignore 挡住，不入库)

What it emits (all deterministic, byte-identical on re-run)
    lore/D4_dialogue/scenes_wiki.jsonl        one scene per mission (66)
    lore/D4_dialogue/dialogues_wiki.jsonl     every wiki line: dialogue / narration / option
    lore/D3_plot/options_wiki.jsonl           options baseline + dlg_id / next
    lore/D6_terminal/terminals_from_wiki.jsonl terminal_* / bracket / redacted fragments

Parsing strategy (nothing is invented; every field is copied or omitted)
    ## 标题（3.x · 章节）      -> mission / scene boundary
    **任务描述** / **出场人物** / **任务流程** / **剧情梗概**  -> scene before / cast / during / after
    **剧情内容**               -> everything before it is metadata, never dialogue
    ### 小节                   -> section context recorded on each line (`step`)
    **〔额外对话（X）〕**       -> fold-block context (`block`)
    **【地点】** 描述           -> narration line with `location`
    - 说话人：台词              -> kind="dialogue", speaker = 冒号前的原文
    - **〔选项〕** 文本          -> kind="option", speaker=null（wiki 不标说话人）
    - 无冒号的文本              -> kind="narration", speaker=null
    *（旁白）…* / > 字幕 / 正文 -> kind="narration", speaker=null
    模板结束 / --- / {{#css:…}} -> structural noise, skipped

    Speaker heuristic is deliberately timid: a prefix only counts as a speaker when it
    is <=20 chars, is not a UI caption such as 战斗效果…, and carries no sentence
    punctuation except at its tail (「？？？」「三月七！」). Everything else stays a
    narration line with the raw text intact.

    Scene `gap` records what the wiki does not give us (voice, camera, timeline,
    option consequences); it never guesses.

    python tools/lore_build/build_wiki_scenes.py
    python tools/lore_build/build_wiki_scenes.py --check   # verify without writing
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
STRUCT_DIR = os.path.join(ROOT, "lore", "story", "wiki_structured")

OUT_SCENES = os.path.join(ROOT, "lore", "D4_dialogue", "scenes_wiki.jsonl")
OUT_DIALOGUES = os.path.join(ROOT, "lore", "D4_dialogue", "dialogues_wiki.jsonl")
OUT_OPTIONS = os.path.join(ROOT, "lore", "D3_plot", "options_wiki.jsonl")
OUT_TERMINALS = os.path.join(ROOT, "lore", "D6_terminal", "terminals_from_wiki.jsonl")

VERSIONS = ("3.0", "3.1", "3.2", "3.3", "3.4", "3.5", "3.6", "3.7")

MISSION_HEAD = re.compile(r"^## (.+?)（(3\.\d) · (.+?)）\s*$")
STEP_HEAD = re.compile(r"^### (.+?)\s*$")
LOC_HEAD = re.compile(r"^\*\*【(.+?)】\*\*\s*(.*)$")
FOLD_HEAD = re.compile(r"^\*\*〔(.+?)〕\*\*$")
BOLD_LINE = re.compile(r"^\*\*(.+?)\*\*$")
OPTION_BULLET = re.compile(r"^-\s+\*\*〔选项〕\*\*\s*(.*)$")
BULLET = re.compile(r"^-\s+(.*)$")
ITALIC_LINE = re.compile(r"^\*(?!\*)(.+?)\*\s*$")
SPEAKER_SPLIT = re.compile(r"^([^：:]{1,20})[：:](.*)$")
SPEAKER_BAN = re.compile(r"[。！？…]")
CAPTION_HEAD = re.compile(r"^(战斗效果|战斗技能|成就|道具|任务)")
NUMBERED = re.compile(r"^\d+\.\s*(.*)$")
CSS_TEMPLATE = re.compile(r"\{\{#css:")

META_DESC = "**任务描述**："
META_CAST = "**出场人物**："
META_FLOW = "**任务流程**："
META_SYNOPSIS = "**剧情梗概**"
META_CONTENT = "**剧情内容**"

# terminals_wiki text_kind -> terminal authority in the canon terminal window
TERMINAL_KINDS = {
    "terminal_prompt": "user",   # 玩家在终端里输入的指令/选项
    "terminal_line": "kernel",   # 权杖/系统直接输出的正文行
    "bracket": "kernel",         # 【…】系统通告
    "redacted": "kernel",        # 被 █ 遮蔽的系统记录
}


def clean(text: str) -> str:
    """Strip wiki markup (color templates, links, bold, html tags) but keep the prose."""
    s = text
    s = re.sub(r"\{\{颜色\|[^{}|]*\|(.*?)\}\}", r"\1", s)
    s = re.sub(r"\{\{[^{}]*?\|([^{}|]*)\}\}", r"\1", s)
    s = re.sub(r"\[(?:https?://)?[^\s\]]+\s+([^\]]*)\]", r"\1", s)
    s = s.replace("**", "")
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("'''", "")
    return s.strip()


def indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def split_speaker(body: str):
    """Return (speaker, text) when the wiki marks a speaker, else (None, body)."""
    m = SPEAKER_SPLIT.match(body)
    if not m:
        return None, body
    name, text = m.group(1).strip(), m.group(2)
    if not name or CAPTION_HEAD.match(name):
        return None, body
    # punctuation is only tolerated at the tail (「？？？」「三月七！」), never mid-sentence
    core = name.rstrip("。！？…")
    if not core:
        return (name, text) if set(name) <= {"？"} else (None, body)
    if SPEAKER_BAN.search(core):
        return None, body
    return name, text


def read_jsonl(path):
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def dump_jsonl(rows) -> bytes:
    return "".join(
        json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in rows
    ).encode("utf-8")


def write_if_changed(path: str, data: bytes) -> bool:
    """Write only when bytes differ, so re-runs keep mtimes (and canon stamps) stable."""
    if os.path.exists(path):
        with open(path, "rb") as f:
            if f.read() == data:
                return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return True


class Mission:
    def __init__(self, version: str, name: str, chapter: str, lineno: int):
        self.version = version
        self.name = name
        self.chapter = chapter
        self.start = lineno
        self.end = lineno
        self.description = ""
        self.cast = []
        self.flow = ""
        self.synopsis = []
        self.steps = []
        self.records = []
        self.scene_id = ""

    def finish(self, end_lineno: int):
        self.end = end_lineno


def parse_mission_file(path: str, version: str):
    """Split one volume into missions and turn every in-content wiki line into a record."""
    with open(path, "r", encoding="utf-8") as f:
        lines = f.read().split("\n")

    mission = None
    missions = []
    in_content = False
    in_synopsis = False
    step = None
    block = None
    skipping_css = False
    stack = []  # (indent, record) inside the current bullet tree
    counter = [0]

    def close(end_lineno):
        if mission is not None:
            mission.finish(end_lineno)
            missions.append(mission)

    def next_id():
        counter[0] += 1
        return "DLG-W%s-%04d" % (version, counter[0])

    def add(record, lineno):
        record["id"] = next_id()
        record["scene_id"] = mission.scene_id
        record["order"] = len(mission.records) + 1
        record["line"] = lineno
        record["step"] = step
        record["block"] = block
        record["source"] = "S-024:%s" % os.path.basename(path)
        record["locator"] = "S-024:%s:%d" % (os.path.basename(path), lineno)
        record["confidence"] = "B"
        record["verbatim_claim"] = False
        mission.records.append(record)
        return record

    for lineno, raw in enumerate(lines, 1):
        stripped = raw.strip()

        head = MISSION_HEAD.match(stripped)
        if head:
            close(lineno - 1)
            mission = Mission(version, head.group(1).strip(), head.group(3).strip(), lineno)
            mission.scene_id = ""  # filled in later from missions.jsonl mission_no
            in_content = False
            in_synopsis = False
            step = None
            block = None
            stack = []
            continue

        if mission is None:
            continue

        if skipping_css:
            if "}}" in stripped:
                skipping_css = False
            continue
        if CSS_TEMPLATE.search(stripped):
            skipping_css = True
            continue

        if stripped == META_CONTENT:
            in_content = True
            in_synopsis = False
            continue

        if not in_content:
            if stripped.startswith(META_DESC):
                mission.description = clean(stripped[len(META_DESC):])
            elif stripped.startswith(META_CAST):
                mission.cast = [n.strip() for n in stripped[len(META_CAST):].split("、") if n.strip()]
            elif stripped.startswith(META_FLOW):
                mission.flow = clean(stripped[len(META_FLOW):])
            elif stripped == META_SYNOPSIS:
                in_synopsis = True
            elif in_synopsis:
                m = NUMBERED.match(stripped)
                if m:
                    mission.synopsis.append(clean(m.group(1)))
                elif stripped.startswith("**"):
                    in_synopsis = False
            continue

        if not stripped or stripped in ("---", "模板结束"):
            stack = []
            continue

        step_head = STEP_HEAD.match(stripped)
        if step_head:
            step = clean(step_head.group(1))
            mission.steps.append(step)
            block = None
            stack = []
            continue

        fold_head = FOLD_HEAD.match(stripped)
        if fold_head:
            block = clean(fold_head.group(1))
            stack = []
            continue

        loc_head = LOC_HEAD.match(stripped)
        if loc_head:
            text = clean(loc_head.group(2))
            if text:
                add({
                    "speaker": None, "form": None, "kind": "narration",
                    "verbatim": text, "verbatim_raw": stripped,
                    "location": clean(loc_head.group(1)),
                }, lineno)
            stack = []
            continue

        bullet = BULLET.match(stripped)
        if bullet:
            indent = indent_of(raw)
            option = OPTION_BULLET.match(stripped)
            if option:
                text = clean(option.group(1))
                if not text:
                    continue
                rec = add({
                    "speaker": None, "form": None, "kind": "option",
                    "verbatim": text, "verbatim_raw": stripped,
                }, lineno)
            else:
                body = bullet.group(1).strip()
                name, text = split_speaker(body)
                text = clean(text)
                if not text:
                    continue
                rec = add({
                    "speaker": name,
                    "form": name,
                    "kind": "dialogue" if name else "narration",
                    "verbatim": text, "verbatim_raw": stripped,
                }, lineno)
            while stack and stack[-1][0] >= indent:
                stack.pop()
            if stack:
                parent = stack[-1][1]
                if parent["kind"] == "option":
                    parent.setdefault("_children", []).append(rec["id"])
            rec["_children"] = []
            stack.append((indent, rec))
            continue

        # --- non-bullet content lines -------------------------------------
        text = stripped
        if text.startswith(">"):
            text = text.lstrip(">").strip()
            if not text or "{{#css" in text:
                continue
        italic = ITALIC_LINE.match(text)
        if italic:
            text = italic.group(1)
        bold = BOLD_LINE.match(text)
        if bold:
            text = bold.group(1)
        text = clean(text)
        if not text:
            continue
        add({
            "speaker": None, "form": None, "kind": "narration",
            "verbatim": text, "verbatim_raw": stripped,
        }, lineno)
        stack = []

    close(len(lines))
    return missions


def build_missions():
    mission_meta = {
        (m["version"], m["name"]): m
        for m in read_jsonl(os.path.join(STRUCT_DIR, "missions.jsonl"))
    }
    all_missions = []
    for version in VERSIONS:
        path = os.path.join(WIKI_DIR, "amphoreus_%s.md" % version)
        if not os.path.exists(path):
            raise SystemExit("missing wiki volume: %s" % path)
        missions = parse_mission_file(path, version)
        for ordinal, mission in enumerate(missions, 1):
            meta = mission_meta.get((version, mission.name))
            if meta is None:
                raise SystemExit("mission not in missions.jsonl: %s/%s" % (version, mission.name))
            mission.mission_no = meta.get("mission_no") or ""
            mission.mission_id = meta.get("mission_id") or None
            # mission_no is not unique inside 3.3, so the scene id uses the reading order
            mission.scene_id = "SCN-W%s-%02d" % (version, ordinal)
            for record in mission.records:
                record["scene_id"] = mission.scene_id
        all_missions.extend(missions)
    return all_missions


def build_scenes(missions):
    rows = []
    for mission in missions:
        records = mission.records
        speaker_missing = sum(
            1 for r in records if r["kind"] == "narration" and r.get("verbatim_raw", "").startswith("-")
        )
        gaps = []
        if not records:
            gaps.append("正文无可读对白或旁白，仅保留任务概述")
        else:
            gaps.append("对白逐行取自 wiki 正文，wiki 未提供配音、镜头、BGM 与演出时序")
        if speaker_missing:
            gaps.append("%d 行正文未标注说话人，按旁白收录（原文保留）" % speaker_missing)
        gaps.append("选项分支只记录到分支行，未记录对游戏状态的影响")
        rows.append({
            "id": mission.scene_id,
            "version": mission.version,
            "chapter": mission.chapter,
            "mission": mission.name,
            "mission_no": mission.mission_no,
            "mission_id": mission.mission_id,
            "title": mission.name,
            "before": mission.description,
            "during": mission.flow,
            "after": mission.synopsis[-1] if mission.synopsis else "",
            "sections": mission.steps,
            "participants": mission.cast,
            "dialogue_count": len(records),
            "dialogue_range": [records[0]["id"], records[-1]["id"]] if records else [],
            "line_range": [mission.start, mission.end],
            "gap": gaps,
            "source": "S-024:amphoreus_%s.md#%s" % (mission.version, mission.name),
            "locator": "S-024:amphoreus_%s.md:%d-%d" % (mission.version, mission.start, mission.end),
            "confidence": "B",
            "verbatim_claim": False,
        })
    return rows


def build_dialogues(missions):
    rows = []
    for mission in missions:
        for i, rec in enumerate(mission.records):
            children = rec.pop("_children", [])
            nxt = mission.records[i + 1]["id"] if i + 1 < len(mission.records) else None
            rec["next"] = [nxt] if nxt else []
            rec["children"] = children
            rows.append(rec)
    return rows


def build_options(missions):
    """Attach `dlg_id` / `next` to the wiki_structured options baseline.

    The baseline `line` column comes from a different page snapshot, so it does not
    address our markdown. Options are matched instead by (volume, mission, option text)
    occurrence order, which is stable: the per-mission multiset of option texts is
    identical in both sources, only the flattened order differs in 9 missions.
    """
    base = read_jsonl(os.path.join(STRUCT_DIR, "options.jsonl"))
    queues = {}
    for mission in missions:
        for record in mission.records:
            if record["kind"] != "option":
                continue
            key = (mission.version, mission.name, record["verbatim"])
            queues.setdefault(key, []).append(record)

    rows = []
    missing = 0
    for opt in base:
        key = (opt["version"], opt["task"], clean(opt["option"]).strip())
        bucket = queues.get(key) or []
        record = bucket.pop(0) if bucket else None
        if record is None:
            missing += 1
            dlg_id = None
            nxt = []
            scene_id = None
            md_line = None
        else:
            dlg_id = record["id"]
            nxt = list(record.get("children") or [])
            scene_id = record["scene_id"]
            md_line = record["line"]
        rows.append({
            "id": opt["id"],
            "version": opt["version"],
            "task": opt["task"],
            "step": opt["step"],
            "option": opt["option"],
            "scene_id": scene_id,
            "dlg_id": dlg_id,
            "next": nxt,
            "branch_lines": opt.get("branch_lines") or [],
            "merge_at": opt.get("merge_at") or "",
            "result": opt.get("result") or "",
            "no_branch": opt.get("no_branch"),
            "parent": opt.get("parent"),
            "line": md_line,
            "baseline_line": opt.get("line"),
            "source": "S-024:amphoreus_%s.md#%s" % (opt["version"], opt["task"]),
            "locator": "S-024:amphoreus_%s.md:%s" % (opt["version"], md_line if md_line else "?"),
            "confidence": "B",
            "verbatim_claim": False,
            "grade": opt.get("grade", "B"),
            "source_url": opt.get("source_url", ""),
        })
    return rows, missing


def build_terminals():
    base = read_jsonl(os.path.join(STRUCT_DIR, "terminals_wiki.jsonl"))
    rows = []
    for idx, item in enumerate(base, 1):
        text_kind = item.get("text_kind")
        if text_kind not in TERMINAL_KINDS:
            continue
        page = item.get("page") or ""
        rows.append({
            "id": "TRM-W-%04d" % (len(rows) + 1),
            "text": item.get("text", ""),
            "text_kind": text_kind,
            "authority": TERMINAL_KINDS[text_kind],
            "trigger": {"frame": None, "require_event": None},
            "page": page,
            "task": item.get("task") or "",
            "source": item.get("source_url", ""),
            "locator": "wiki:%s:%d" % (page, idx),
            "confidence": "B",
            "verbatim_claim": False,
        })
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description="build wiki narrative corpus")
    ap.add_argument("--check", action="store_true", help="verify without writing")
    args = ap.parse_args(argv)

    missions = build_missions()
    scenes = build_scenes(missions)
    dialogues = build_dialogues(missions)
    options, missing = build_options(missions)
    terminals = build_terminals()

    targets = [
        (OUT_SCENES, scenes),
        (OUT_DIALOGUES, dialogues),
        (OUT_OPTIONS, options),
        (OUT_TERMINALS, terminals),
    ]
    changed = 0
    for path, rows in targets:
        rel = os.path.relpath(path, ROOT)
        if args.check:
            data = dump_jsonl(rows)
            same = os.path.exists(path) and open(path, "rb").read() == data
            print(("ok   " if same else "drift") + " %-8d %s" % (len(rows), rel))
            if not same:
                changed += 1
        else:
            if write_if_changed(path, dump_jsonl(rows)):
                changed += 1
            print("%-8d %s" % (len(rows), rel))

    print("missions %d  scenes %d  lines %d  options %d  terminals %d"
          % (len(missions), len(scenes), len(dialogues), len(options), len(terminals)))
    if missing:
        print("WARN options without a wiki line: %d" % missing)
    if args.check:
        return 1 if changed else 0
    print("files written: %d" % changed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
