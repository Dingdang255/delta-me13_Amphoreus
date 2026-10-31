# -*- coding: utf-8 -*-
"""抓取翁法罗斯角色页的「角色故事 1–4」（含 改 版）。

输入：lore/D8_characters/roster.json 的 27 个角色
产出：lore/story/wiki_structured/character_stories.jsonl
用法：python fetch_wiki_charstory.py
"""
import json
import os
import re
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_wiki_amphoreus as fw

ROOT = os.path.dirname(fw.HERE)
OUT = os.path.join(ROOT, "story", "wiki_structured")
ROSTER = os.path.join(ROOT, "D8_characters", "roster.json")
SITE = "https://wiki.biligame.com/sr/"

# 项目内的角色名与 wiki 页名不一致时的映射（其余同名直接取）
ALIAS = {
    "卡厄斯兰那": "白厄",
    "无漏净子（昔涟）": "昔涟",
}


def to_text(s):
    """富文本 → 纯文本：<br> 转行、<i>/<b> 转 md 强调、模板与 HTML 清理、段落归一。"""
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"<i>(.*?)</i>", r"*\1*", s, flags=re.S | re.I)
    s = re.sub(r"<b>(.*?)</b>", r"**\1**", s, flags=re.S | re.I)
    s = fw.clean_inline(s)
    out = []
    for ln in s.split("\n"):
        ln = ln.strip()
        if ln:
            out.append(ln)
        elif out and out[-1] != "":
            out.append("")
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out)


def field(w, key):
    m = re.search(r"\|%s=(.*?)(?=\n\|[^\n=]+=|\Z)" % re.escape(key), w, re.S)
    return to_text(m.group(1)) if m else ""


def main():
    os.makedirs(OUT, exist_ok=True)
    roster = json.load(open(ROSTER, encoding="utf-8"))
    chars = [c["zh"] for c in roster["all"]]
    out_path = os.path.join(OUT, "character_stories.jsonl")

    rows = []
    seen_page = {}
    for zh in chars:
        page = ALIAS.get(zh, zh)
        url = SITE + urllib.parse.quote(page.replace(" ", "_"))
        if page in seen_page:
            rows.append({"character": zh, "wiki_page": page, "part": None,
                         "variant": None, "title": "", "text": "",
                         "status": "alias", "alias_of": seen_page[page],
                         "reason": "同一 wiki 页的另一形态，正文见该角色",
                         "source_url": url, "captured_at": "2026-10-31", "grade": "B"})
            print(f"  {zh}：alias → {seen_page[page]}")
            continue
        seen_page[page] = zh
        try:
            w = fw.fetch_wikitext(page)
        except Exception as e:
            rows.append({"character": zh, "wiki_page": page, "part": None,
                         "variant": None, "title": "", "text": "",
                         "status": "UNKNOWN", "reason": str(e)[:120],
                         "source_url": url, "captured_at": "2026-10-31", "grade": "B"})
            print(f"  {zh}：UNKNOWN（{e}）")
            continue

        count = 0
        for variant, suffix in (("original", ""), ("revised", "改")):
            for part in (1, 2, 3, 4):
                text = field(w, f"角色故事{part}{suffix}")
                if not text:
                    if variant == "original":
                        rows.append({"character": zh, "wiki_page": page, "part": part,
                                     "variant": variant, "title": "", "text": "",
                                     "status": "UNKNOWN",
                                     "reason": "wiki 页面该字段为空或不存在",
                                     "source_url": url, "captured_at": "2026-10-31",
                                     "grade": "B"})
                    continue
                rows.append({
                    "character": zh,
                    "wiki_page": page,
                    "part": part,
                    "variant": variant,
                    "title": "",
                    "text": text,
                    "status": "ok",
                    "source_url": url,
                    "captured_at": "2026-10-31",
                    "grade": "B",
                })
                count += 1
        print(f"  {zh}（{page}）：{count} 段")
        time.sleep(0.4)

    with open(out_path, "w", encoding="utf-8") as fo:
        for r in rows:
            fo.write(json.dumps(r, ensure_ascii=False) + "\n")

    ok = sum(1 for r in rows if r["status"] == "ok")
    unk = sum(1 for r in rows if r["status"] == "UNKNOWN")
    print(f"\n共 {len(rows)} 条：ok {ok} / UNKNOWN {unk} → {out_path}")


if __name__ == "__main__":
    main()
