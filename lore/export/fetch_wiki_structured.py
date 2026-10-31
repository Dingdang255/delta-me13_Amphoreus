# -*- coding: utf-8 -*-
"""把拓 wiki 的翁法罗斯开拓任务解析成结构化数据（任务元数据 + 选项分支树）。

产出：
  lore/story/wiki_structured/missions.jsonl   45 条任务元数据
  lore/story/wiki_structured/options.jsonl    全部剧情选项及其分支体

用法：python fetch_wiki_structured.py
"""
import json
import os
import re
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_wiki_amphoreus as fw

OUT = os.path.join(os.path.dirname(fw.HERE), "story", "wiki_structured")
SITE = "https://wiki.biligame.com/sr/"
GRADE = "B"

META_KEYS = ("任务名称", "任务地区", "任务类型", "所属版本", "任务描述",
             "出场人物", "系列任务", "任务编号", "任务条件", "开放等级",
             "前置任务", "后续任务", "领取地点", "相关成就", "相关道具", "相关书籍",
             "任务流程", "剧情梗概")


def parse_meta_all(w):
    """解析 {{任务|...}} 的全部字段（值允许跨行，直到下一个 \n|key= 或 \n}}）。"""
    m = re.search(r"\{\{任务\b(.*?)\n\}\}", w, re.S)
    if not m:
        return {}
    body = m.group(1)
    meta = {}
    for k in META_KEYS:
        mm = re.search(r"\|%s=(.*?)(?=\n\|[^\n=]+=|\Z)" % k, body, re.S)
        if mm:
            meta[k] = fw.clean_inline(mm.group(1).strip())
    return meta


def split_links(s):
    """'*[[A]]\\n*[[B]]' -> ['A','B']"""
    if not s:
        return []
    names = re.findall(r"\[\[(?:[^\]|]*\|)?([^\]]+)\]\]", s)
    if names:
        return names
    return [x.strip("* ").strip() for x in s.split("\n") if x.strip("* ").strip()]


# ---------- 逐顶层结构扫描（保留位置，用于行号与合流点） ----------

def scan(body):
    events = []
    buf = []
    buf_start = [0]

    def flush():
        if buf:
            events.append({"kind": "text", "text": "".join(buf), "pos": buf_start[0]})
            buf.clear()
        buf_start[0] = -1

    n = len(body)
    i = 0
    while i < n:
        if body.startswith("{{", i):
            depth = 0
            j = i
            while j < n:
                if body.startswith("{{", j):
                    depth += 1
                    j += 2
                elif body.startswith("}}", j):
                    depth -= 1
                    j += 2
                    if depth == 0:
                        break
                else:
                    j += 1
            inner = body[i + 2:j - 2]
            name = re.split(r"[|\s]", inner.strip(), maxsplit=1)[0].strip()
            if name in fw.BLOCK_TEMPLATES:
                flush()
                events.append({"kind": "block", "name": name, "inner": inner, "pos": i})
            else:
                if not buf:
                    buf_start[0] = i
                buf.append(body[i:j])
            i = j
        elif body[i:i + 8].lower() == "<tabber>":
            j = body.find("</tabber>", i)
            j = n if j < 0 else j + len("</tabber>")
            flush()
            events.append({"kind": "tabber", "inner": body[i + 8:j - 9], "pos": i})
            i = j
        else:
            if not buf:
                buf_start[0] = i
            buf.append(body[i])
            i += 1
    flush()
    return events


def lines_of(text):
    return [ln.rstrip() for ln in fw.clean_inline(text).split("\n")]


def first_nonempty(events, idx):
    """取该事件之后第一段非空正文的首行（选项合流点），去掉 wiki 的 * / : 标记。"""
    for ev in events[idx + 1:]:
        if ev["kind"] == "text":
            for ln in lines_of(ev["text"]):
                s = ln.strip()
                if s:
                    return s.lstrip("*:").strip()
        elif ev["kind"] == "block":
            if ev["name"] in ("剧情选项", "短信选项"):
                continue
            return ""
        elif ev["kind"] == "tabber":
            continue
    return ""


def strip_nested_blocks(text):
    """把分支体里嵌套的块级模板就地展开或丢弃，保证模板语法不进台词。"""
    out = []
    i = 0
    n = len(text)
    while i < n:
        if text.startswith("{{", i):
            depth = 0
            j = i
            while j < n:
                if text.startswith("{{", j):
                    depth += 1
                    j += 2
                elif text.startswith("}}", j):
                    depth -= 1
                    j += 2
                    if depth == 0:
                        break
                else:
                    j += 1
            inner = text[i + 2:j - 2]
            name = re.split(r"[|\s]", inner.strip(), maxsplit=1)[0].strip()
            if name in ("折叠", "折叠框"):
                out.append("\n" + fold_content(inner) + "\n")
            # 剧情选项 / 短信选项：已由 collect_options 递归收录，这里丢弃
            i = j
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def parse_branch(text):
    """把分支体拆成 [{speaker,text}]；: 开头视为旁白，模板语法一律丢弃。"""
    out = []
    for ln in strip_nested_blocks(text).split("\n"):
        s = ln.strip()
        if not s or s.startswith("|") or s.startswith("}}") or s.startswith("{{"):
            continue
        m = re.match(r"^\*+\s*([^：:]{1,20})[：:](.*)$", s)
        if m:
            out.append({"speaker": m.group(1).strip(), "text": m.group(2).strip()})
        elif s.startswith(":"):
            out.append({"speaker": "旁白", "text": s.lstrip(":").strip()})
        elif s.startswith("**〔"):
            out.append({"speaker": "小标题", "text": s})
        else:
            out.append({"speaker": "", "text": s})
    return out


def parse_option_fields(inner):
    """返回 [{num, opt, branch, off}]；off 为该字段在 inner 内的字符偏移，用于算行号。"""
    fields = {}
    order = []
    offs = {}
    cur = None
    cur_val = []
    depth = 0
    pos = 0
    for ln in inner.split("\n"):
        m = re.match(r"\|(选项\d+|剧情\d+|图标\d+)\s*=\s*(.*)$", ln)
        if m and depth == 0:
            if cur is not None:
                fields[cur] = "\n".join(cur_val).strip()
            cur = m.group(1)
            order.append(cur)
            offs[cur] = pos
            cur_val = [m.group(2)]
        else:
            cur_val.append(ln)
        depth += ln.count("{{") - ln.count("}}")
        pos += len(ln) + 1
    if cur is not None:
        fields[cur] = "\n".join(cur_val).strip()

    items = []
    for k in order:
        if not k.startswith("选项"):
            continue
        num = k[len("选项"):]
        items.append({
            "num": num,
            "opt": fw.clean_inline(fields.get(k, "")).strip(),
            "branch": fields.get("剧情" + num, ""),
            "off": offs.get(k, 0),
        })
    return items


def fold_content(inner):
    """取出 {{折叠|内容=...}} 的正文（按括号/字段边界扫描）。"""
    mc = re.search(r"\|内容\s*=\s*", inner)
    if not mc:
        return ""
    cs = mc.end()
    ce = cs
    depth = 0
    while ce < len(inner):
        if inner.startswith("{{", ce):
            depth += 1
            ce += 2
        elif inner.startswith("}}", ce):
            depth -= 1
            ce += 2
        elif depth == 0 and inner[ce] == "|":
            break
        else:
            ce += 1
    return inner[cs:ce]


def collect_options(body, abs_start, w, step, parent, out, counter, ver, task, url,
                    mission_no=""):
    """递归收集选项：折叠内容、以及选项分支体内嵌套的剧情选项都算。"""
    events = scan(body)
    for idx, ev in enumerate(events):
        if ev["kind"] == "tabber":
            for part in ev["inner"].split("|-|"):
                if part.strip():
                    collect_options(part, abs_start + ev["pos"], w, step,
                                    parent, out, counter, ver, task, url, mission_no)
            continue
        if ev["kind"] != "block":
            continue
        if ev["name"] in ("剧情选项", "短信选项"):
            step_here = step_name_of(events, idx) or step or "（任务开场）"
            merge = first_nonempty(events, idx)
            for it in parse_option_fields(ev["inner"]):
                counter[0] += 1
                oid = f"OPT-{ver}-{mission_no or '00'}-{counter[0]:03d}"
                branch = it["branch"]
                lines = parse_branch(branch) if branch.strip() else []
                # 该选项自己那一行的行号（模板起点 + 字段偏移）
                line_no = w[:abs_start + ev["pos"] + 2 + it["off"]].count("\n") + 1
                out.append({
                    "id": oid,
                    "version": ver,
                    "task": task,
                    "step": step_here,
                    "option": it["opt"],
                    "branch_lines": lines,
                    "merge_at": merge,
                    "result": "",
                    "no_branch": not lines,
                    "parent": parent,
                    "source_url": url,
                    "line": line_no,
                    "grade": GRADE,
                })
                if branch.strip():
                    collect_options(branch, abs_start + ev["pos"], w, step_here,
                                    oid, out, counter, ver, task, url, mission_no)
        elif ev["name"] in ("折叠", "折叠框"):
            mt = re.search(r"\|标题\s*=\s*([^\n|]+)", ev["inner"])
            title = fw.clean_inline(mt.group(1)).strip() if mt else step
            content = fold_content(ev["inner"])
            if content.strip():
                collect_options(content, abs_start + ev["pos"], w, title,
                                parent, out, counter, ver, task, url, mission_no)

def step_name_of(events, idx):
    """向前找最近的 === 小节标题或折叠标题作为所属步骤。"""
    for ev in reversed(events[:idx]):
        if ev["kind"] == "text":
            for ln in reversed(lines_of(ev["text"])):
                s = ln.strip()
                if s.startswith("===") and s.endswith("==="):
                    return s.strip("= \t")
        elif ev["kind"] == "block" and ev["name"] in ("折叠", "折叠框"):
            mt = re.search(r"\|标题\s*=\s*([^\n|]+)", ev["inner"])
            if mt:
                return fw.clean_inline(mt.group(1)).strip()
        elif ev["kind"] == "tabber":
            pass
    return ""


def load_mission_ids():
    """从本地客户端提取结果建立「任务名 → 8 位 Mission ID」映射。"""
    p = os.path.join(fw.HERE, "data", "story_full.jsonl")
    m = {}
    if not os.path.exists(p):
        return m
    for line in open(p, encoding="utf-8"):
        try:
            d = json.loads(line)
        except Exception:
            continue
        name = d.get("mission_name") or ""
        mid = str(d.get("mission") or "")
        if name and mid.isdigit():
            lst = m.setdefault(name, [])
            if mid not in lst:
                lst.append(mid)
    return m


MISSION_IDS = {}


def main():
    global MISSION_IDS
    MISSION_IDS = load_mission_ids()
    os.makedirs(OUT, exist_ok=True)
    tasks = fw.ask_tasks()
    print(f"任务数：{len(tasks)}")

    missions_path = os.path.join(OUT, "missions.jsonl")
    options_path = os.path.join(OUT, "options.jsonl")

    stat = {}
    n_opt = n_no_branch = 0
    with open(missions_path, "w", encoding="utf-8") as fm, \
            open(options_path, "w", encoding="utf-8") as fo:
        for t in tasks:
            try:
                w = fw.fetch_wikitext(t["name"])
            except Exception as e:
                print(f"  失败 {t['name']}: {e}", file=sys.stderr)
                continue

            meta = parse_meta_all(w)
            url = SITE + urllib.parse.quote(t["name"].replace(" ", "_"))
            mid = MISSION_IDS.get(meta.get("任务名称", t["name"]), [])
            mission = {
                "mission_no": meta.get("任务编号", ""),
                "mission_id": mid[0] if mid else "",
                "mission_ids": mid,
                "version": meta.get("所属版本", t["ver"]) or t["ver"],
                "type": meta.get("任务类型", "开拓任务"),
                "name": meta.get("任务名称", t["name"]),
                "chapter": meta.get("系列任务", t["chapter"]),
                "region": meta.get("任务地区", ""),
                "level": meta.get("开放等级", ""),
                "condition": meta.get("任务条件", ""),
                "prereq": split_links(meta.get("前置任务", "")),
                "next": split_links(meta.get("后续任务", "")),
                "characters": [c for c in re.split(r"[、,，]", meta.get("出场人物", "")) if c],
                "description": meta.get("任务描述", ""),
                "synopsis": [x.strip("# ").strip() for x in meta.get("剧情梗概", "").split("\n")
                             if x.strip("# ").strip()],
                "steps": [x.strip("* ").strip() for x in meta.get("任务流程", "").split("\n")
                          if x.strip("* ").strip()],
                "source_url": url,
                "captured_at": "2026-10-31",
                "grade": GRADE,
            }
            fm.write(json.dumps(mission, ensure_ascii=False) + "\n")

            i = w.find("==剧情内容==")
            if i < 0:
                continue
            base = i + len("==剧情内容==")
            counter = [0]
            recs = []
            collect_options(w[base:], base, w, "", None, recs,
                            counter, t["ver"], mission["name"], url,
                            mission["mission_no"])
            used = set()
            for rec in recs:
                while rec["id"] in used:  # 3.3 存在两个「编号 07」的任务，避免撞号
                    rec["id"] += "b"
                used.add(rec["id"])
                fo.write(json.dumps(rec, ensure_ascii=False) + "\n")
                n_opt += 1
                if rec["no_branch"]:
                    n_no_branch += 1
                    stat[t["ver"]] = stat.get(t["ver"], 0) + 1
            print(f"  [{t['ver']}] {t['name']} OK（选项 {len(recs)}）")
            time.sleep(0.4)

    print(f"\n选项总数 {n_opt}，无分支 {n_no_branch}（{n_no_branch / max(n_opt,1):.1%}）")
    for k in sorted(stat):
        print(f"  {k}: 无分支 {stat[k]}")
    print("输出 →", OUT)


if __name__ == "__main__":
    main()
