# -*- coding: utf-8 -*-
"""B1：翁法罗斯相关书籍/阅读物/碑文索引 + 全文。

来源：分类:书籍 与 分类:任务道具 中含 {{书籍}} 模板的页面（批量抓取，按 3.x 版本或正文含「翁法罗斯」筛选）。
产出：
  lore/story/wiki_structured/books_index.jsonl  一书一条
  lore/story/wiki_structured/books_full.jsonl   一卷一条（正文）
用法：python fetch_wiki_books.py
"""
import json
import os
import re
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_wiki_amphoreus as fw
import fetch_wiki_structured as fs

OUT = os.path.join(os.path.dirname(fw.HERE), "story", "wiki_structured")
SITE = "https://wiki.biligame.com/sr/"
CATS = ("分类:书籍", "分类:任务道具")


def members(cat):
    out, cont = [], None
    while True:
        p = {"action": "query", "list": "categorymembers", "cmtitle": cat,
             "cmlimit": "500", "format": "json"}
        if cont:
            p["cmcontinue"] = cont
        d = fw.http_get(p)
        out += [m["title"] for m in d.get("query", {}).get("categorymembers", [])]
        cont = d.get("continue", {}).get("cmcontinue")
        if not cont:
            return out


def fetch_many(titles, batch=40):
    """批量取 wikitext，减少请求数。"""
    out = {}
    for i in range(0, len(titles), batch):
        chunk = titles[i:i + batch]
        d = fw.http_get({"action": "query", "prop": "revisions", "rvslots": "main",
                         "rvprop": "content", "titles": "|".join(chunk),
                         "format": "json", "formatversion": "2"})
        for p in d.get("query", {}).get("pages", []):
            if p.get("revisions"):
                out[p["title"]] = p["revisions"][0]["slots"]["main"]["content"]
        time.sleep(0.25)
    return out


def blocks(w, name):
    """取出全部 {{name …}} 块的 inner。"""
    out = []
    for m in re.finditer(r"\{\{" + re.escape(name) + r"(?=[\s|}])", w):
        depth = 0
        j = m.start()
        while j < len(w):
            if w.startswith("{{", j):
                depth += 1
                j += 2
            elif w.startswith("}}", j):
                depth -= 1
                j += 2
                if depth == 0:
                    break
            else:
                j += 1
        out.append(w[m.start() + 2 + len(name):j - 2])
    return out


def field(inner, key):
    for part in fw.split_top(inner):
        m = re.match(r"\s*%s\s*=\s*(.*)$" % re.escape(key), part, re.S)
        if m:
            return m.group(1).strip()
    return ""


def to_text(s):
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
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


def main():
    os.makedirs(OUT, exist_ok=True)
    titles = []
    for c in CATS:
        titles += members(c)
    titles = sorted(set(titles))
    print(f"候选页面 {len(titles)}")

    pages = fetch_many(titles)
    print(f"取回 {len(pages)} 页")

    idx_path = os.path.join(OUT, "books_index.jsonl")
    full_path = os.path.join(OUT, "books_full.jsonl")
    n_book = n_vol = 0
    with open(idx_path, "w", encoding="utf-8") as fi, \
            open(full_path, "w", encoding="utf-8") as ff:
        for title, w in sorted(pages.items()):
            metas = blocks(w, "书籍")
            if not metas:
                continue
            meta_inner = metas[0]
            name = fw.clean_inline(field(meta_inner, "书籍名")) or title
            ver = fw.clean_inline(field(meta_inner, "实装版本"))
            btype = fw.clean_inline(field(meta_inner, "类型"))
            desc = to_text(field(meta_inner, "描述"))
            no = fw.clean_inline(field(meta_inner, "编号"))

            vols = []
            for inner in blocks(w, "书籍/分卷"):
                vols.append({
                    "volume": fw.clean_inline(field(inner, "卷数")) or "",
                    "obtain": to_text(field(inner, "获取方式")),
                    "content": to_text(field(inner, "内容")),
                })
            if len(vols) == 1 and not vols[0]["content"]:
                vols = []

            blob = desc + "".join(v["content"] for v in vols)
            if not (ver.startswith("3.") or "翁法罗斯" in blob or "泰坦" in blob):
                continue

            url = SITE + urllib.parse.quote(title.replace(" ", "_"))
            fi.write(json.dumps({
                "name": name,
                "page": title,
                "type": btype,
                "version": ver,
                "no": no,
                "volume_count": len(vols) or (fw.clean_inline(field(meta_inner, "卷数")) or ""),
                "description": desc,
                "source_url": url,
                "captured_at": "2026-10-31",
                "grade": "B",
            }, ensure_ascii=False) + "\n")
            n_book += 1

            for i, v in enumerate(vols, 1):
                if not v["content"]:
                    continue
                ff.write(json.dumps({
                    "book": name,
                    "page": title,
                    "volume": v["volume"] or str(i),
                    "obtain": v["obtain"],
                    "content": v["content"],
                    "source_url": url,
                    "captured_at": "2026-10-31",
                    "grade": "B",
                }, ensure_ascii=False) + "\n")
                n_vol += 1

    print(f"翁法罗斯相关书籍 {n_book} 本 / {n_vol} 卷")
    print("→", idx_path)
    print("→", full_path)


if __name__ == "__main__":
    main()
