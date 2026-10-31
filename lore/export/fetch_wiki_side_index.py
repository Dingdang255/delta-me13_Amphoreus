# -*- coding: utf-8 -*-
"""统计翁法罗斯全部任务并按类型分组，输出非开拓任务（冒险/活动/同行）索引。

产出：lore/story/wiki_structured/side_missions_index.jsonl
用法：python fetch_wiki_side_index.py
"""
import json
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_wiki_amphoreus as fw

OUT = os.path.join(os.path.dirname(fw.HERE), "story", "wiki_structured")
SITE = "https://wiki.biligame.com/sr/"


def ask(q):
    d = fw.http_get({"action": "ask", "query": q, "format": "json",
                     "api_version": "2", "limit": "500"})
    res = d.get("query", {}).get("results", {})
    return {} if isinstance(res, list) else res


def rows_of(q):
    out = []
    for name, v in ask(q).items():
        po = v.get("printouts", {})
        g = lambda f: (po.get(f) or [""])[0]
        out.append({
            "name": name,
            "type": g("任务类型"),
            "version": g("所属版本"),
            "region": g("任务地区"),
            "no": g("任务编号"),
            "chapter": g("系列任务").replace("[[", "").replace("]]", ""),
            "source_url": SITE + urllib.parse.quote(name.replace(" ", "_")),
        })
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    exact = rows_of("[[任务地区::翁法罗斯]]|?任务类型|?所属版本|?任务编号|?系列任务")
    # 补齐 任务地区 写成「翁法罗斯-xxx」的任务
    fuzzy = rows_of("[[任务地区::~*翁法罗斯*]]|?任务类型|?所属版本|?任务编号|?系列任务")
    seen = {r["name"] for r in exact}
    for r in fuzzy:
        if r["name"] not in seen:
            exact.append(r)
            seen.add(r["name"])

    kinds = {}
    for r in exact:
        kinds[r["type"]] = kinds.get(r["type"], 0) + 1
    print("翁法罗斯任务总数：", len(exact), kinds)

    side = sorted([r for r in exact if r["type"] != "开拓任务"],
                  key=lambda r: (r["version"], r["type"], r["no"], r["name"]))
    p = os.path.join(OUT, "side_missions_index.jsonl")
    with open(p, "w", encoding="utf-8") as f:
        for r in side:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"非开拓任务 {len(side)} 条 → {p}")
    for r in side:
        print(f"  [{r['type']}] {r['version'] or '-':4s} {r['name']}")


if __name__ == "__main__":
    main()
