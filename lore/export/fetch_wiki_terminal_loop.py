# -*- coding: utf-8 -*-
"""B4：终端 / 管理员批注等特殊文本；B3：轮回编号与光历纪年全集。

产出：terminals_wiki.jsonl、loop_mentions.jsonl
"""
import json, os, re, sys, time, urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_wiki_amphoreus as fw

OUT = os.path.join(os.path.dirname(fw.HERE), "story", "wiki_structured")
SITE = "https://wiki.biligame.com/sr/"
TERM_PAGES = ["管理员批注.wav", "Δ-me13.exe", "邮箱.exe", "迷迷.exe",
              "逐火者的命路.exe", "翁法罗斯英雄纪.exe"]
TERM_RE = re.compile(r"权杖δ-me13|>>>|【载入核心变量|管理员批注|ERROR|错误码")
LOOP_RE = re.compile(r"第[一二三四五六七八九十百千万亿两\d]+次永劫回归|永劫回归|"
                     r"光历\s*\d+\s*年|\d+\s*次轮回|第\s*\d+\s*次轮回")


def txt(s):
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = fw.clean_inline(s)
    return "\n".join(ln.strip() for ln in s.split("\n") if ln.strip())


def main():
    os.makedirs(OUT, exist_ok=True)
    tasks = fw.ask_tasks()

    # ---- B4 ----
    tp = os.path.join(OUT, "terminals_wiki.jsonl")
    n = 0
    with open(tp, "w", encoding="utf-8") as f:
        for page in TERM_PAGES:
            try:
                w = fw.fetch_wikitext(page)
            except Exception:
                continue
            body = txt(w)
            url = SITE + urllib.parse.quote(page.replace(" ", "_"))
            for ln in body.split("\n"):
                if len(ln) < 2:
                    continue
                f.write(json.dumps({
                    "kind": "page", "page": page, "task": "", "text": ln,
                    "source_url": url, "captured_at": "2026-10-31", "grade": "B",
                }, ensure_ascii=False) + "\n")
                n += 1
            time.sleep(0.4)
        # 任务页里的终端行
        for t in tasks:
            try:
                w = fw.fetch_wikitext(t["name"])
            except Exception:
                continue
            i = w.find("==剧情内容==")
            if i < 0:
                continue
            url = SITE + urllib.parse.quote(t["name"].replace(" ", "_"))
            for ln in txt(w[i:]).split("\n"):
                s = ln.lstrip("*:").strip()
                if s and TERM_RE.search(s) and ("δ-me13" in s or s.startswith(">>>")
                                                or "载入核心变量" in s):
                    f.write(json.dumps({
                        "kind": "task", "page": "", "task": t["name"],
                        "version": t["ver"], "text": s, "source_url": url,
                        "captured_at": "2026-10-31", "grade": "B",
                    }, ensure_ascii=False) + "\n")
                    n += 1
            time.sleep(0.35)
    print("terminals:", n)

    # ---- B3 ----
    lp = os.path.join(OUT, "loop_mentions.jsonl")
    srcs = []
    for fn, fields in (
        ("missions.jsonl", ("description", "synopsis")),
        ("books_full.jsonl", ("content",)),
        ("ruwoshuo.jsonl", ("text",)),
        ("battle_lines.jsonl", ("text",)),
        ("side_missions.jsonl", ("description", "synopsis")),
    ):
        p = os.path.join(OUT, fn)
        if not os.path.exists(p):
            continue
        for line in open(p, encoding="utf-8"):
            r = json.loads(line)
            for fldname in fields:
                v = r.get(fldname)
                for chunk in (v if isinstance(v, list) else [v]):
                    if isinstance(chunk, str) and chunk:
                        srcs.append((fn, r.get("name") or r.get("task") or r.get("book")
                                     or r.get("character"), chunk,
                                     r.get("source_url", "")))
    m = 0
    with open(lp, "w", encoding="utf-8") as f:
        for fn, who, text, url in srcs:
            for mt in LOOP_RE.finditer(text):
                a = max(0, mt.start() - 80)
                ctx = text[a:mt.end() + 80].replace("\n", " ")
                f.write(json.dumps({
                    "match": mt.group(0), "context": ctx, "who": who,
                    "from": fn, "source_url": url,
                    "captured_at": "2026-10-31", "grade": "B",
                }, ensure_ascii=False) + "\n")
                m += 1
    print("loop mentions:", m)


if __name__ == "__main__":
    main()
