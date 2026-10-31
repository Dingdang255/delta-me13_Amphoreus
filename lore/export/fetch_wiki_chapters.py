# -*- coding: utf-8 -*-
"""B5：版本 / 章节 / 任务编号 / 任务名 对照表（翁法罗斯全量，含非开拓任务）。

产出：lore/story/wiki_structured/chapter_map.jsonl
用法：python fetch_wiki_chapters.py
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
VERSIONS = ("3.0", "3.1", "3.2", "3.3", "3.4", "3.5", "3.6", "3.7", "3.8")


def ask(q):
    d = fw.http_get({"action": "ask", "query": q, "format": "json",
                     "api_version": "2", "limit": "500"})
    res = d.get("query", {}).get("results", {})
    return {} if isinstance(res, list) else res


def chapter_meta(name):
    """从 {{系列任务|…}} 取章节的版本 / 地区 / 描述。"""
    try:
        w = fw.fetch_wikitext(name)
    except Exception:
        return {}
    m = re.search(r"\{\{系列任务\b(.*?)\n\}\}", w, re.S)
    if not m:
        return {}
    body = m.group(1)
    out = {}
    for k in ("所属版本", "任务地区", "任务类型", "描述"):
        mm = re.search(r"\|%s=(.*?)(?=\n\|[^\n=]+=|\Z)" % k, body, re.S)
        if mm:
            out[k] = re.sub(r"<!--.*?-->", "", mm.group(1), flags=re.S).strip()
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    cache = {}
    rows = []
    for ver in VERSIONS:
        res = ask("[[任务地区::翁法罗斯]][[所属版本::%s]]"
                  "|?任务类型|?任务编号|?系列任务" % ver)
        for name, v in res.items():
            po = v.get("printouts", {})
            g = lambda f: (po.get(f) or [""])[0]
            chap = re.sub(r"\[\[(.*?)\]\]", r"\1", g("系列任务"))
            no = g("任务编号")
            typ = g("任务类型")
            if chap not in cache:
                cache[chap] = chapter_meta(chap) if chap else {}
                time.sleep(0.3)
            cm = cache[chap] or {}
            rows.append({
                "version": ver,
                "chapter": chap,
                "chapter_region": cm.get("任务地区", ""),
                "chapter_desc": cm.get("描述", ""),
                "mission_no": no,
                "type": typ,
                "name": name,
                "is_chapter_index": (not no and typ == "开拓任务"),
                "source_url": SITE + urllib.parse.quote(name.replace(" ", "_")),
                "captured_at": "2026-10-31",
                "grade": "B",
            })
        print(f"  {ver}: {sum(1 for r in rows if r['version'] == ver)} 条")

    rows.sort(key=lambda r: (r["version"], r["mission_no"] or "99", r["name"]))
    path = os.path.join(OUT, "chapter_map.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\n合计 {len(rows)} 行 → {path}")


if __name__ == "__main__":
    main()
