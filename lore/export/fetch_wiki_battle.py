# -*- coding: utf-8 -*-
"""A6：抽取翁法罗斯主线任务里的战斗段（阶段播报 + 战斗内台词），并汇总 Boss 敌人页。

产出：
  lore/story/wiki_structured/battle_lines.jsonl   战斗段逐行（含阶段标记）
  lore/story/wiki_structured/enemy_pages.jsonl    3.x Boss 敌人页（wiki 无语音则标 none_in_wiki）

用法：python fetch_wiki_battle.py
"""
import json
import os
import re
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_wiki_amphoreus as fw
import fetch_wiki_side as sd

OUT = os.path.join(os.path.dirname(fw.HERE), "story", "wiki_structured")
SITE = "https://wiki.biligame.com/sr/"

# 战斗阶段标记（wiki 用 :{{颜色|灰|…}} 写在场地上）
BATTLE_RE = re.compile(
    r"进入战斗|战斗开始|战斗结束|战斗胜利|获得胜利|战斗失败|进入第[一二三四五六七八九十\d]+阶段|"
    r"第[一二三四五六七八九十\d]+阶段|即将释放|血量降低|状态回满|场外支援"
)
PHASE_RULES = (
    (re.compile(r"进入第([一二三四五六七八九十\d]+)阶段|第([一二三四五六七八九十\d]+)阶段"), "阶段"),
    (re.compile(r"进入战斗|战斗开始"), "战斗开始"),
    (re.compile(r"即将释放"), "大招前"),
    (re.compile(r"血量降低"), "血量阈值"),
    (re.compile(r"战斗胜利|战斗结束|获得胜利"), "战斗结束"),
)


def phase_of(marker):
    for rx, label in PHASE_RULES:
        m = rx.search(marker)
        if m:
            if label == "阶段":
                n = m.group(1) or m.group(2)
                return f"第{n}阶段"
            return label
    return "阶段未标注"


def split_segments(items):
    """按小节标题、折叠标题、分隔线把行流切段，返回 [(step, [item])]。"""
    segs = []
    step = ""
    cur = []
    for it in items:
        if it["kind"] == "step":
            if cur:
                segs.append((step, cur))
                cur = []
            step = it["text"]
            continue
        if it["kind"] == "fold":
            if cur:
                segs.append((step, cur))
                cur = []
            step = it["text"] or step
            continue
        if it["kind"] == "paragraph" and it["text"].strip() in ("----", "---"):
            if cur:
                segs.append((step, cur))
                cur = []
            continue
        cur.append(it)
    if cur:
        segs.append((step, cur))
    return segs


def main():
    os.makedirs(OUT, exist_ok=True)
    tasks = fw.ask_tasks()
    battles_path = os.path.join(OUT, "battle_lines.jsonl")
    stat = {}
    total = 0
    n_battle_total = 0

    with open(battles_path, "w", encoding="utf-8") as fo:
        for t in tasks:
            try:
                w = fw.fetch_wikitext(t["name"])
            except Exception as e:
                print(f"  失败 {t['name']}: {e}", file=sys.stderr)
                continue
            i = w.find("==剧情内容==")
            if i < 0:
                continue
            url = SITE + urllib.parse.quote(t["name"].replace(" ", "_"))
            items = sd.sub_lines(w[i + len("==剧情内容=="):])

            n_battle = 0
            for step, lines in split_segments(items):
                idxs = [k for k, it in enumerate(lines)
                        if it["kind"] == "narration" and BATTLE_RE.search(it["text"])]
                if not idxs:
                    continue
                # 只保留从「进入战斗」到「战斗结束/获得胜利」之间的行
                start = idxs[0]
                end = len(lines)
                for k in idxs:
                    if re.search(r"战斗胜利|战斗结束|获得胜利|战斗失败", lines[k]["text"]):
                        end = k + 1
                        break
                lines = lines[start:end]
                n_battle += 1
                n_battle_total += 1
                bid = f"BAT-{t['ver']}-{n_battle_total:03d}"
                phase = "阶段未标注"
                for it in lines:
                    is_marker = it["kind"] == "narration" and bool(BATTLE_RE.search(it["text"]))
                    if is_marker:
                        phase = phase_of(it["text"])
                    rec = {
                        "battle_id": bid,
                        "version": t["ver"],
                        "task": t["name"],
                        "step": step,
                        "phase": phase,
                        "kind": it["kind"],
                        "speaker": it["speaker"],
                        "text": it["text"],
                        "marker": is_marker,
                        "source_url": url,
                        "captured_at": "2026-10-31",
                        "grade": "B",
                    }
                    fo.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    total += 1
                stat[t["ver"]] = stat.get(t["ver"], 0) + 1
            print(f"  [{t['ver']}] {t['name']}：战斗段 {n_battle}")
            time.sleep(0.4)

    print(f"\n战斗段 {n_battle_total} 段 / {total} 行；按版本 {dict(sorted(stat.items()))}")
    print("→", battles_path)

    # ---- Boss 敌人页 ----
    merged = {}
    for q in ("[[分类:敌人]]|?类型|?分类|?实装版本|?介绍|?历战余响",
              "[[分类:泰坦眷属]]|?类型|?分类|?实装版本|?介绍|?历战余响",
              "[[分类:黑潮造物]]|?类型|?分类|?实装版本|?介绍|?历战余响"):
        d = fw.http_get({"action": "ask", "query": q, "format": "json",
                         "api_version": "2", "limit": "500"})
        res = d.get("query", {}).get("results", {})
        if not isinstance(res, list):
            merged.update(res)
    res = merged
    enemy_path = os.path.join(OUT, "enemy_pages.jsonl")
    n = 0
    with open(enemy_path, "w", encoding="utf-8") as fe:
        for name, v in sorted(res.items()):
            po = v.get("printouts", {})
            g = lambda f: (po.get(f) or [""])[0]
            ver = str(g("实装版本"))
            cats = po.get("分类") or []
            cat = cats[0].get("fulltext", "").replace("分类:", "") if cats else ""
            # 翁法罗斯专属敌人类别即使没填版本也收
            if not ver.startswith("3.") and cat not in ("泰坦眷属", "黑潮造物"):
                continue
            rec = {
                "name": name,
                "type": g("类型"),
                "category": cat,
                "version": ver,
                "intro": fw.clean_inline(g("介绍")),
                "weekly": g("历战余响"),
                "battle_lines": [],
                "none_in_wiki": True,
                "note": "wiki 敌人页只收录属性与介绍，不含战斗语音/阶段播报",
                "source_url": SITE + urllib.parse.quote(name.replace(" ", "_")),
                "captured_at": "2026-10-31",
                "grade": "B",
            }
            fe.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    print(f"3.x Boss/敌人页 {n} 条 → {enemy_path}")


if __name__ == "__main__":
    main()
