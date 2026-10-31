# -*- coding: utf-8 -*-
"""把翁法罗斯（3.0–3.7，Mission 104*）剧情原文抽成按版本分卷的可读 Markdown。

输出：lore/story/amphoreus/amphoreus_<ver>.md + README.md
复用 export_story 的角色名解析（cn_role）、节点切分（split_node）与渲染（render_mission）。
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from export_story import cn_role, split_node, group_by_mission, render_mission

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
OUT = os.path.join(os.path.dirname(HERE), "story", "amphoreus")

# Mission 前缀 → 游戏版本（10436=3.6、10437=3.7，其余 1040X=3.X）
VERSION_MAP = [
    ("10401", "3.0"),
    ("10402", "3.1"),
    ("10403", "3.2"),
    ("10404", "3.3"),
    ("10405", "3.4"),
    ("10406", "3.5"),
    ("10436", "3.6"),
    ("10437", "3.7"),
]

_TAG = re.compile(r"<[^>]*>")
_RUBY_B = re.compile(r"\{RUBY_B#[^}]*\}")
_RUBY_E = re.compile(r"\{RUBY_E#\}")


def clean_tags(s):
    """去掉富文本标签，保留正文与换行（<color>/<unbreak>/<i>/RUBY 注音等）。"""
    s = _TAG.sub("", s)
    s = _RUBY_B.sub("", s)
    s = _RUBY_E.sub("", s)
    return s


def version_of(mid):
    for prefix, ver in VERSION_MAP:
        if mid.startswith(prefix):
            return ver
    return None


def load_data():
    story = [json.loads(l) for l in open(os.path.join(DATA, "story_full.jsonl"), encoding="utf-8")]
    names = json.load(open(os.path.join(DATA, "name_by_role.json"), encoding="utf-8"))
    allnames = json.load(open(os.path.join(DATA, "names.json"), encoding="utf-8"))
    return story, names, allnames


def mission_title(segs):
    return next((s.get("mission_name") for s in segs if s.get("mission_name")), None)


def main():
    story, names, allnames = load_data()
    g = group_by_mission(story)

    # 只保留翁法罗斯任务，并按版本聚合
    amph = {mid: segs for mid, segs in g.items() if version_of(mid)}
    by_ver = {}
    for mid, segs in amph.items():
        by_ver.setdefault(version_of(mid), []).append(mid)
    for v in by_ver:
        by_ver[v].sort()

    os.makedirs(OUT, exist_ok=True)

    # 写每个版本一个分卷
    index_rows = []
    for ver, mids in sorted(by_ver.items()):
        bodies = []
        total_lines = got_lines = 0
        for mid in mids:
            segs = amph[mid]
            body = render_mission(mid, segs, names, allnames, no_empty=True)
            body = clean_tags(body)
            bodies.append(body)
            total_lines += sum(len(s["lines"]) for s in segs)
            got_lines += sum(1 for s in segs for ln in s["lines"] if ln["text"])

        header = (
            f"# 翁法罗斯 {ver} 剧情原文\n\n"
            f"> 版本 {ver} · Mission {mids[0]}–{mids[-1]} · 共 {len(mids)} 个任务 · "
            f"{total_lines} 句台词（有译文 {got_lines}，{got_lines/max(1,total_lines):.0%}）\n"
            f"> 台词取自客户端 4.6.0 本地数据；富文本标签已去除；`{{NICKNAME}}` = 玩家名（开拓者）。\n"
        )
        text = header + "\n\n---\n\n" + "\n\n---\n\n".join(bodies) + "\n"
        path = os.path.join(OUT, f"amphoreus_{ver}.md")
        open(path, "w", encoding="utf-8").write(text)
        index_rows.append((ver, len(mids), total_lines, got_lines))
        print(f"{path}  {len(mids)}任务/{total_lines}句/{got_lines}有译文")

    # 写 README 索引
    lines = [
        "# 翁法罗斯剧情原文 · 分卷索引",
        "",
        "逐字台词来自客户端 4.6.0 本地数据（`lore/export/data/story_full.jsonl`），",
        "仅含翁法罗斯（Mission 104*，3.0–3.7），按版本拆成 8 个分卷，每个文件足够小、可整卷喂给 AI 阅读。",
        "",
        "| 版本 | 分卷 | 任务数 | 台词（有译文） |",
        "|---|---|---|---|",
    ]
    for ver, n, total, got in index_rows:
        lines.append(f"| {ver} | [amphoreus_{ver}.md](amphoreus_{ver}.md) | {n} | {total}（{got}） |")
    lines += [
        "",
        "## 说明",
        "",
        "- 台词已去除富文本标签（`<color>`/`<unbreak>`/`{RUBY_*}` 注音等）；`{NICKNAME}` 为玩家名占位符（游戏内即「开拓者」）。",
        "- `⟨缺译文 / 玩家选项⟩` 表示该句在客户端文本表里没有中文（多为玩家选择项）。",
        "- 同一剧情节点下「主线」为该节点台词最多的走向，「变体 N」为其它分支（通常是选了不同选项）。",
        "- 说话人仅约 20% 台词可识别（客户端未保留 SpeakerID 字段），其余以 `- 台词` 裸行呈现。",
        "- 原始逐字引用请回指 `story_full.jsonl`（`path` + `lines[].id`），本分卷只做可读呈现。",
    ]
    readme = "\n".join(lines) + "\n"
    open(os.path.join(OUT, "README.md"), "w", encoding="utf-8").write(readme)
    print(os.path.join(OUT, "README.md"))


if __name__ == "__main__":
    main()
