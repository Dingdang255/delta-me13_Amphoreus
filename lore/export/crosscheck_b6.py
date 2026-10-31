# -*- coding: utf-8 -*-
"""B6：wiki 台词 vs 本地客户端文本的三栏对照。

口径：wiki 按游戏显示逐行断句，客户端存整句，故用「子串包含」判定而非等值。
输出每任务：matched / only_wiki / only_client 三栏。
"""
import json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MD = os.path.join(ROOT, "story", "amphoreus_wiki")
SRC = os.path.join(HERE, "data", "story_full.jsonl")
OUT = os.path.join(ROOT, "story", "wiki_structured", "b6_crosscheck.jsonl")


def norm(s):
    s = re.sub(r"^\s*[\-\*\u3000]+", "", s)
    s = re.sub(r"^[^：:]{1,20}[：:]", "", s)
    return re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", s)


def main():
    local = {}
    allp = []
    n = 0
    for line in open(SRC, encoding="utf-8"):
        try:
            d = json.loads(line)
        except Exception:
            continue
        name = d.get("mission_name") or ""
        for it in (d.get("lines") or []):
            t = it.get("text") if isinstance(it, dict) else str(it)
            if not t:
                continue
            x = norm(t)
            if len(x) < 2:
                continue
            n += 1
            allp.append(x)
            if name:
                local.setdefault(name, []).append(x)
    print("S-001 句:", n, "任务:", len(local))
    all_join = "\x00".join(allp)
    local_join = {k: "\x00".join(v) for k, v in local.items()}

    mids = {}
    mp = os.path.join(ROOT, "story", "wiki_structured", "missions.jsonl")
    if os.path.exists(mp):
        for l in open(mp, encoding="utf-8"):
            d = json.loads(l)
            mids[d["name"]] = d.get("mission_ids") or []

    wiki = {}
    order = []
    cur = ver = ""
    for fn in sorted(os.listdir(MD)):
        if not fn.startswith("amphoreus_"):
            continue
        for ln in open(os.path.join(MD, fn), encoding="utf-8"):
            s = ln.rstrip("\n")
            if s.startswith("## "):
                cur = s[3:].strip()
                ver = fn.replace("amphoreus_", "").replace(".md", "")
                wiki[cur] = []
                order.append(cur)
                continue
            if not cur or not s.startswith("- "):
                continue
            body = s[2:].strip()
            if body.startswith("**〔选项〕**") or body.startswith("*（旁白）"):
                continue
            x = norm(body)
            if len(x) >= 2:
                wiki[cur].append((x, body[:60]))

    rows = []
    tot = mat = 0
    for task in order:
        tname = task.rsplit("（", 1)[0].strip()
        lj = local_join.get(tname, "")
        wj = "\x00".join(x for x, _ in wiki[task])
        m, only_w = 0, []
        for x, orig in wiki[task]:
            if (lj and x in lj) or x in all_join:
                m += 1
            elif len(only_w) < 5:
                only_w.append(orig)
        client_lines = local.get(tname, [])
        only_c = sum(1 for x in client_lines if x not in wj)
        tot += len(wiki[task])
        mat += m
        rows.append({
            "task": tname,
            "version": task.rsplit("（", 1)[-1].rstrip("）") if "（" in task else "",
            "wiki_lines": len(wiki[task]),
            "matched": m,
            "only_wiki": len(wiki[task]) - m,
            "only_client": only_c,
            "client_lines": len(client_lines),
            "ratio": round(m / len(wiki[task]), 3) if wiki[task] else 0,
            "mission_ids": mids.get(tname, []),
            "only_wiki_samples": only_w,
        })

    with open(OUT, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wiki 行 {tot}，命中 {mat}（{mat / max(tot,1):.1%}），任务 {len(rows)}")


if __name__ == "__main__":
    main()
