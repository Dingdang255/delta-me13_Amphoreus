# -*- coding: utf-8 -*-
"""HSR 4.6 剧情文本导出工具（自包含，只依赖同目录 data/）

用法：
  python export_story.py --list                      列出所有章节/任务
  python export_story.py --mission 2021901           导出单个任务
  python export_story.py --mission 2021901,1030101   导出多个
  python export_story.py --all --out ./out           全部导出为一个文件
  python export_story.py --mission 2021901 --json    机器可读格式
  python export_story.py --grep 卡芙卡                按内容搜索
  python export_story.py --mission 2021901 --no-empty 跳过无台词节点

数据：
  data/story_full.jsonl   剧情结构 + 台词
  data/name_by_role.json  角色资源名 -> 中文名
  data/names.json         全量名字 key -> 中文（备用）
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")


def load_data():
    for f in ("story_full.jsonl", "name_by_role.json", "names.json"):
        p = os.path.join(DATA, f)
        if not os.path.exists(p):
            sys.exit(f"缺少数据文件：{p}")
    story = [json.loads(l) for l in open(os.path.join(DATA, "story_full.jsonl"), encoding="utf-8")]
    names = json.load(open(os.path.join(DATA, "name_by_role.json"), encoding="utf-8"))
    allnames = json.load(open(os.path.join(DATA, "names.json"), encoding="utf-8"))
    return story, names, allnames


_PREFIXES = ("NPC_Avatar_Lady_", "NPC_Avatar_Lad_", "NPC_Avatar_Girl_",
             "NPC_Avatar_Miss_", "NPC_Avatar_Male_", "NPC_Avatar_Boy_",
             "NPC_Avatar_Maid_", "NPC_Avatar_", "Avatar_", "NPC_", "Monster_")


def cn_role(role, names, allnames):
    """角色资源名 -> 中文名（多级回退，找不到就返回原名）。"""
    if not role:
        return None
    if role in names:
        return names[role]
    base = re.sub(r"_\d{2}$", "", role)
    if base in names:
        return names[base]
    # 从资源名里剥出英文名，再查名字表
    for pre in _PREFIXES:
        if base.startswith(pre):
            cand = base[len(pre):]
            for tpl in ("NPCName_Avatar_{}", "TalkSentenceName_{}", "NPCName_{}"):
                v = allnames.get(tpl.format(cand))
                if v:
                    return v
            break
    return role


def split_node(path):
    """从 path 提取 (节点名, 分支序号)。"""
    base = path.rsplit("/", 1)[-1]
    for suf in (".playable", ".prefab"):
        if base.endswith(suf):
            n = base[:-len(suf)]
            if n.startswith("Story") and len(n) >= 13:
                return n[:-2], n[-2:]
            return n, None
    return os.path.splitext(base)[0], None


def group_by_mission(story):
    g = {}
    for s in story:
        g.setdefault(s["mission"], []).append(s)
    for k in g:
        g[k].sort(key=lambda x: x["path"])
    return g


def render_mission(mid, segs, names, allnames, no_empty=False):
    title = next((s.get("mission_name") for s in segs if s.get("mission_name")), None)
    out = [f"# {title}（Mission {mid}）" if title else f"# Mission {mid}", ""]

    total = sum(len(s["lines"]) for s in segs)
    got = sum(1 for s in segs for ln in s["lines"] if ln["text"])
    out.append(f"- 台词 {total} 句（有译文 {got}，{got/max(1,total):.0%}）")

    allchars = []
    for s in segs:
        for c in s.get("characters") or []:
            if c not in allchars:
                allchars.append(c)
    if allchars:
        out.append("- 在场角色：" + "、".join(cn_role(c, names, allnames) for c in allchars[:12]))
    out.append("")

    # 按节点分组
    bynode = {}
    for s in segs:
        node, seq = split_node(s["path"])
        bynode.setdefault(node, []).append((seq, s))

    for node in sorted(bynode):
        if node == f"Story{mid}" or node is None:
            continue
        items = bynode[node]
        items.sort(key=lambda x: x[0] or "")
        withlines = [(sq, s) for sq, s in items if s["lines"]]
        if not withlines:
            if not no_empty:
                out.append(f"## {node}（无对白）")
                out.append("")
            continue

        out.append(f"## {node}")
        chars = []
        for _, s in items:
            for c in s.get("characters") or []:
                if c not in chars:
                    chars.append(c)
        if chars:
            out.append("> 在场：" + "、".join(cn_role(c, names, allnames) for c in chars[:10]))
            out.append("")

        multi = len(withlines) > 1
        withlines.sort(key=lambda x: -len(x[1]["lines"]))
        for i, (sq, s) in enumerate(withlines):
            if multi:
                tag = "主线" if i == 0 else f"变体 {i}"
                out.append(f"### {tag}　{s['path'].rsplit('/', 1)[-1]}")
            out.append("")
            for ln in s["lines"]:
                if ln["text"] is None:
                    out.append(f"- `{ln['id']}` ⟨缺译文 / 玩家选项⟩")
                elif ln.get("speaker"):
                    out.append(f"- **{cn_role(ln['speaker'], names, allnames)}**：{ln['text']}")
                else:
                    out.append(f"- {ln['text']}")
            out.append("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="HSR 剧情文本导出")
    ap.add_argument("--list", action="store_true", help="列出所有任务")
    ap.add_argument("--mission", help="任务 ID，逗号分隔")
    ap.add_argument("--all", action="store_true", help="导出全部")
    ap.add_argument("--out", help="输出文件或目录（默认打印到 stdout）")
    ap.add_argument("--json", action="store_true", help="输出 JSON 而非 Markdown")
    ap.add_argument("--grep", help="按台词内容搜索")
    ap.add_argument("--no-empty", action="store_true", help="跳过无台词节点")
    a = ap.parse_args()

    story, names, allnames = load_data()
    g = group_by_mission(story)

    if a.list:
        rows = []
        for mid, segs in g.items():
            title = next((s.get("mission_name") for s in segs if s.get("mission_name")), "")
            lines = sum(len(s["lines"]) for s in segs)
            rows.append((mid, title, lines))
        rows.sort(key=lambda x: x[0])
        print(f"{'任务ID':<12}{'任务名':<26}台词")
        for mid, title, n in rows:
            print(f"{mid:<12}{title[:24]:<26}{n}")
        return

    if a.grep:
        kw = a.grep
        for mid, segs in sorted(g.items()):
            for s in segs:
                for ln in s["lines"]:
                    if ln["text"] and kw in ln["text"]:
                        sp = cn_role(ln.get("speaker"), names, allnames) or ""
                        print(f"{mid}  {s['path']}\n  {'**'+sp+'**：' if sp else ''}{ln['text']}")
        return

    targets = []
    if a.all:
        targets = sorted(g)
    elif a.mission:
        targets = [m.strip() for m in a.mission.split(",") if m.strip()]
    else:
        ap.print_help()
        return

    results = {}
    for mid in targets:
        if mid not in g:
            print(f"[跳过] 找不到 Mission {mid}", file=sys.stderr)
            continue
        if a.json:
            results[mid] = [{"path": s["path"], "characters": s.get("characters"),
                             "lines": [{"id": ln["id"],
                                        "speaker": cn_role(ln.get("speaker"), names, allnames),
                                        "text": ln["text"]} for ln in s["lines"]]}
                            for s in g[mid]]
        else:
            results[mid] = render_mission(mid, g[mid], names, allnames, a.no_empty)

    if a.json:
        txt = json.dumps(results, ensure_ascii=False, indent=1)
    else:
        txt = "\n\n---\n\n".join(results.values())

    if a.out:
        os.makedirs(a.out if a.out.endswith(("/", "\\")) or not os.path.splitext(a.out)[1] else
                    os.path.dirname(a.out) or ".", exist_ok=True)
        if a.all or len(targets) > 1:
            os.makedirs(a.out, exist_ok=True)
            for mid, body in results.items():
                ext = ".json" if a.json else ".md"
                open(os.path.join(a.out, f"mission_{mid}{ext}"), "w", encoding="utf-8").write(body)
            print(f"已导出 {len(results)} 个任务到 {a.out}")
        else:
            open(a.out, "w", encoding="utf-8").write(txt)
            print(f"已写入 {a.out}")
    else:
        print(txt)


if __name__ == "__main__":
    main()
