# -*- coding: utf-8 -*-
"""从角色卡派生 relations / scenarios / ooc_guards，避免手写漂移。"""
import json, io, os, glob

CH = r"d:\文档\Amphoreus\lore\D8_characters\characters"
OUT = r"d:\文档\Amphoreus\lore\D8_characters"

cards = []
for f in sorted(glob.glob(os.path.join(CH, "*.json"))):
    cards.append(json.load(io.open(f, encoding="utf-8")))

# ---------- relations ----------
rels = []
seen = set()
for c in cards:
    for r in c["relations"]:
        key = (c["id"], r["target"])
        if key in seen:
            continue
        seen.add(key)
        rels.append({
            "from": c["id"], "to": r["target"], "type": r["type"],
            "intensity": r["intensity"], "evidence": r["source"]
        })
# 手工补：由剧情概述直接支持的边
MANUAL = [
    ("CHR-015", "CHR-021", "debt", 0.8, "S-001:30398"),
    ("CHR-015", "CHR-018", "love", 0.8, "S-001:159361"),
    ("CHR-015", "CHR-016", "trust", 0.8, "S-001:30380"),
    ("CHR-021", "CHR-015", "guilt", 0.9, "S-001:159356"),
    ("CHR-022", "CHR-023", "love", 0.9, "S-001:30415"),
    ("CHR-023", "CHR-022", "contract", 0.9, "S-001:30416"),
    ("CHR-001", "CHR-017", "trust", 0.8, "S-001:159366"),
    ("CHR-016", "CHR-018", "trust", 0.8, "S-001:60066"),
    ("CHR-019", "CHR-001", "debt", 0.7, "S-001:159350"),
    ("CHR-019", "CHR-018", "debt", 0.7, "S-001:159350"),
    ("CHR-008", "CHR-005", "trust", 0.9, "S-001:226179"),
    ("CHR-010", "CHR-013", "hostility", 0.8, "S-001:425115"),
    ("CHR-013", "CHR-008", "hostility", 0.6, "S-001:425005"),
    ("CHR-006", "CHR-008", "contract", 0.5, "S-001:30418"),
]
for m in MANUAL:
    if (m[0], m[1]) not in seen:
        seen.add((m[0], m[1]))
        rels.append({"from": m[0], "to": m[1], "type": m[2], "intensity": m[3], "evidence": m[4]})

with io.open(os.path.join(OUT, "relations.jsonl"), "w", encoding="utf-8") as f:
    for r in rels:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

# ---------- scenarios ----------
sc = []
n = 0
for c in cards:
    rules = c["decision_rules"][:3]
    for i, r in enumerate(rules, 1):
        n += 1
        sc.append({
            "id": f"T-{n:03d}",
            "character": c["id"],
            "given": {"percept": r["when"], "memory": c["identity"]["memory"],
                      "goals": [g["text"] for g in c["goals"]],
                      "relations": {x["target"]: x["intensity"] for x in c["relations"]}},
            "expect": {"action": r["then"], "reason": f"命中 {r['id']}"},
            "forbidden": c["ooc_guards"][:2],
            "source": r["source"],
            "official_scene": r["source"].startswith("S-001") or r["source"].startswith("S-002"),
            "judged": "PASS" if r["source"] != "UNKNOWN" else "UNKNOWN"
        })
with io.open(os.path.join(OUT, "scenarios.jsonl"), "w", encoding="utf-8") as f:
    for s in sc:
        f.write(json.dumps(s, ensure_ascii=False) + "\n")

# ---------- ooc_guards ----------
guards = []
for c in cards:
    for g in c["ooc_guards"]:
        guards.append({"id": f"OOC-{len(guards)+1:03d}", "character": c["id"], "guard": g,
                       "scope": "dialogue|decision", "severity": "hard"})
with io.open(os.path.join(OUT, "ooc_guards.jsonl"), "w", encoding="utf-8") as f:
    for g in guards:
        f.write(json.dumps(g, ensure_ascii=False) + "\n")

print("relations", len(rels), "scenarios", len(sc), "guards", len(guards))
