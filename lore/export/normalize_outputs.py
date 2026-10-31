# -*- coding: utf-8 -*-
"""收尾清洗：chapter_map / terminals / books / lightcones / relics / b6 / ruwoshuo。"""
import json, os, re

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "story", "wiki_structured")


def load(name):
    return [json.loads(l) for l in open(os.path.join(OUT, name), encoding="utf-8")]


def dump(name, rows):
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(name, len(rows))


def scope_of(ver):
    v = str(ver or "")
    if v in ("3.0", "3.1", "3.2", "3.3", "3.4", "3.5", "3.6", "3.7"):
        return "main"
    if v.startswith("3."):
        return "side"
    return "out_of_scope"


def main():
    # chapter_map
    rows = load("chapter_map.jsonl")
    for r in rows:
        ch = r.get("chapter") or ""
        r["chapter"] = None if ch in ("", "None", "-") else ch
        r["scope"] = "chapter_index" if r.get("is_chapter_index") else (
            "main" if r.get("type") == "开拓任务" else "side")
    dump("chapter_map.jsonl", rows)

    # terminals
    rows = load("terminals_wiki.jsonl")
    for r in rows:
        t = r.get("text", "")
        if t.startswith(">>>"):
            r["text_kind"] = "terminal_prompt"
        elif "█" in t:
            r["text_kind"] = "redacted"
        elif re.match(r"^【.*】", t):
            r["text_kind"] = "bracket"
        elif "δ-me13" in t:
            r["text_kind"] = "terminal_line"
        else:
            r["text_kind"] = "page_text"
    dump("terminals_wiki.jsonl", rows)

    # books / lightcones / relics：明确 scope + version
    ver_by_page = {}
    for f in ("books_index.jsonl", "lightcones.jsonl", "relics.jsonl"):
        rows = load(f)
        for r in rows:
            r["version"] = str(r.get("version") or "")
            # 书籍空版本是用「正文提及翁法罗斯」筛进来的，仍属主线
            if f == "books_index.jsonl" and (not r["version"] or not re.search(r"\d", r["version"])):
                r["scope"] = "main"
            else:
                r["scope"] = scope_of(r["version"])
            r.pop("in_scope_3x", None)
            ver_by_page[r["page"]] = (r["version"], r["scope"])
        dump(f, rows)

    # books_full：补 version / scope（按 page join）
    rows = load("books_full.jsonl")
    for r in rows:
        v, s = ver_by_page.get(r.get("page"), ("", "main"))
        r["version"] = v
        r["scope"] = s
    dump("books_full.jsonl", rows)

    # b6：加无版本后缀的 task_name
    rows = load("b6_crosscheck.jsonl")
    for r in rows:
        r["task_name"] = r["task"].rsplit("（", 1)[0].strip()
    dump("b6_crosscheck.jsonl", rows)

    # ruoshuo：progress 无 wiki 依据，显式标注
    rows = load("ruwoshuo.jsonl")
    for r in rows:
        r.setdefault("progress", None)
        r["progress_source"] = "UNKNOWN" if r["progress"] is None else "wiki"
    dump("ruwoshuo.jsonl", rows)


if __name__ == "__main__":
    main()
