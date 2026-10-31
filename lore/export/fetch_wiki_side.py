# -*- coding: utf-8 -*-
"""抓取翁法罗斯非开拓任务（冒险/活动）的剧情原文，输出结构化 JSONL。

输入：lore/story/wiki_structured/side_missions_index.jsonl
产出：lore/story/wiki_structured/side_missions.jsonl
用法：python fetch_wiki_side.py
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_wiki_amphoreus as fw
import fetch_wiki_structured as fs

OUT = os.path.join(os.path.dirname(fw.HERE), "story", "wiki_structured")
INDEX = os.path.join(OUT, "side_missions_index.jsonl")


def dialogue_line(s):
    """把一行正文转成 {kind,speaker,text}。"""
    if s.startswith("===") and s.endswith("==="):
        return {"kind": "step", "speaker": "", "text": s.strip("= \t").strip()}
    if s.startswith("*"):
        m = re.match(r"^\*+\s*([^：:]{1,20})[：:](.*)$", s)
        if m:
            return {"kind": "dialogue", "speaker": m.group(1).strip(), "text": m.group(2).strip()}
        return {"kind": "dialogue", "speaker": "", "text": s.lstrip("*").strip()}
    if s.startswith(":"):
        return {"kind": "narration", "speaker": "旁白", "text": s.lstrip(":").strip()}
    return {"kind": "paragraph", "speaker": "", "text": s}


def block_lines(ev):
    """把块级模板转成若干行记录。"""
    name, inner = ev["name"], ev["inner"]
    if name in ("剧情选项", "短信选项"):
        out = []
        for _num, opt, branch in fs.parse_option_fields(inner):
            out.append({"kind": "option", "speaker": "", "text": opt})
            if branch.strip():
                out.extend(sub_lines(branch))
        return out
    if name in ("折叠", "折叠框"):
        mt = re.search(r"\|标题\s*=\s*([^\n|]+)", inner)
        out = []
        if mt:
            out.append({"kind": "fold", "speaker": "",
                        "text": fw.clean_inline(mt.group(1)).strip()})
        content = fs.fold_content(inner)
        if content.strip():
            out.extend(sub_lines(content))
        return out
    if name == "任务描述":
        return [{"kind": "scene", "speaker": "", "text": fw._render_scene(inner)}]
    if name in ("提示", "提示消息"):
        txt = fw._render_hint(inner) if name == "提示" else fw._render_notice(inner)
        return [{"kind": "notice", "speaker": "", "text": ln.strip()}
                for ln in txt.split("\n") if ln.strip()]
    return []


def sub_lines(body):
    """递归展开一段正文（块级模板 + 普通行），返回行记录列表。"""
    out = []
    for ev in fs.scan(body):
        if ev["kind"] == "block":
            out.extend(block_lines(ev))
        elif ev["kind"] == "tabber":
            for part in ev["inner"].split("|-|"):
                if part.strip():
                    out.extend(sub_lines(part))
        else:
            for ln in fs.lines_of(ev["text"]):
                s = ln.strip()
                if s:
                    out.append(dialogue_line(s))
    return out


def main():
    rows = [json.loads(l) for l in open(INDEX, encoding="utf-8")]
    out_path = os.path.join(OUT, "side_missions.jsonl")
    ok = 0
    with open(out_path, "w", encoding="utf-8") as fo:
        for r in rows:
            name = r["name"]
            try:
                w = fw.fetch_wikitext(name)
            except Exception as e:
                print(f"  失败 {name}: {e}", file=sys.stderr)
                continue

            meta = fs.parse_meta_all(w)
            i = w.find("==剧情内容==")
            body = w[i + len("==剧情内容=="):] if i >= 0 else ""
            lines = sub_lines(body) if body else []

            steps = []
            cur = {"name": "", "lines": []}
            for ln in lines:
                if ln["kind"] == "step":
                    if cur["name"] or cur["lines"]:
                        steps.append(cur)
                    cur = {"name": ln["text"], "lines": []}
                else:
                    cur["lines"].append(ln)
            if cur["name"] or cur["lines"]:
                steps.append(cur)

            rec = {
                "name": meta.get("任务名称", name),
                "type": meta.get("任务类型", r["type"]),
                "version": meta.get("所属版本", r["version"]),
                "region": meta.get("任务地区", r["region"]),
                "chapter": meta.get("系列任务", r["chapter"]),
                "condition": meta.get("任务条件", ""),
                "level": meta.get("开放等级", ""),
                "characters": [c for c in re.split(r"[、,，]", meta.get("出场人物", "")) if c],
                "description": meta.get("任务描述", ""),
                "synopsis": [x.strip("# ").strip() for x in meta.get("剧情梗概", "").split("\n")
                             if x.strip("# ").strip()],
                "process": [x.strip("* ").strip() for x in meta.get("任务流程", "").split("\n")
                            if x.strip("* ").strip()],
                "steps": steps,
                "line_count": len(lines),
                "no_plot": not lines,
                "note": "" if lines else "页面为系列/活动总览页，无 ==剧情内容== 章节",
                "source_url": r["source_url"],
                "captured_at": "2026-10-31",
                "grade": "B",
            }
            fo.write(json.dumps(rec, ensure_ascii=False) + "\n")
            ok += 1
            n_d = sum(1 for x in lines if x["kind"] == "dialogue")
            n_n = sum(1 for x in lines if x["kind"] == "narration")
            n_o = sum(1 for x in lines if x["kind"] == "option")
            print(f"  {name}：步骤 {len(steps)}／台词 {n_d}／旁白 {n_n}／选项 {n_o}")
            time.sleep(0.5)

    print(f"\n完成 {ok}/{len(rows)} → {out_path}")


if __name__ == "__main__":
    main()
