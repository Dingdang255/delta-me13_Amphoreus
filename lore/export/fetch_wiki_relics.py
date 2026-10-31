# -*- coding: utf-8 -*-
"""B2：翁法罗斯相关光锥 / 遗器故事。输出 lightcones.jsonl、relics.jsonl。"""
import json, os, re, sys, time, urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_wiki_amphoreus as fw

OUT = os.path.join(os.path.dirname(fw.HERE), "story", "wiki_structured")
SITE = "https://wiki.biligame.com/sr/"
KEY_RE = re.compile(r"^\|([^=\n]{1,16})=", re.M)


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
    out = {}
    for i in range(0, len(titles), batch):
        d = fw.http_get({"action": "query", "prop": "revisions", "rvslots": "main",
                         "rvprop": "content", "titles": "|".join(titles[i:i + batch]),
                         "format": "json", "formatversion": "2"})
        for p in d.get("query", {}).get("pages", []):
            if p.get("revisions"):
                out[p["title"]] = p["revisions"][0]["slots"]["main"]["content"]
        time.sleep(0.2)
    return out


def fld(w, k):
    m = re.search(r"\|%s=(.*?)(?=\n\|[^\n=]+=|\Z)" % re.escape(k), w, re.S)
    return m.group(1).strip() if m else ""


def txt(s):
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"<i>(.*?)</i>", r"*\1*", s, flags=re.S | re.I)
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
    res = {}
    for cat in ("分类:光锥", "分类:遗器"):
        titles = sorted(set(members(cat)))
        pages = fetch_many(titles)
        n = 0
        for title, w in sorted(pages.items()):
            ver = fw.clean_inline(fld(w, "实装版本"))
            keys = KEY_RE.findall(w)
            story_keys = [k for k in keys if ("故事" in k or k == "描述")]
            parts = {k: txt(fld(w, k)) for k in story_keys}
            parts = {k: v for k, v in parts.items() if v}
            blob = "".join(parts.values()) + fld(w, "技能效果")
            if not (ver.startswith("3.") or "翁法罗斯" in blob or "泰坦" in blob):
                continue
            rec = {
                "kind": "lightcone" if cat == "分类:光锥" else "relic",
                "name": fw.clean_inline(fld(w, "名称")) or title,
                "page": title,
                "version": ver,
                "path": fw.clean_inline(fld(w, "命途") or fld(w, "类别")),
                "rarity": fw.clean_inline(fld(w, "稀有度")),
                "stories": parts,
                "source_url": SITE + urllib.parse.quote(title.replace(" ", "_")),
                "captured_at": "2026-10-31",
                "grade": "B",
            }
            res.setdefault("lightcone" if cat == "分类:光锥" else "relic", []).append(rec)
            n += 1
        print(cat, len(titles), "→", n)

    for kind, fn in (("lightcone", "lightcones.jsonl"), ("relic", "relics.jsonl")):
        rows = res.get(kind, [])
        with open(os.path.join(OUT, fn), "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(fn, len(rows))


if __name__ == "__main__":
    main()
