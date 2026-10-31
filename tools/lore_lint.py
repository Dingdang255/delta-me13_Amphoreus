#!/usr/bin/env python3
"""Static lint for the lore corpus (read-only).

Checks, per record:
  * JSONL parses
  * id present and unique inside its kind
  * required fields present
  * confidence is one of A/B/C/D/E/UNKNOWN (when the field exists)
  * a source-ish field is present for fact kinds
  * cross references resolve (dialogue -> scene, scenario -> character, ...)

Exit code 1 when any ERROR is reported. Warnings do not fail the run.

    python tools/lore_lint.py
    python tools/lore_lint.py --json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError):
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LORE = os.path.join(ROOT, "lore")

CONFIDENCE = {"A", "B", "C", "D", "E", "UNKNOWN"}
SOURCE_KEYS = ("source", "sources", "evidence", "claim_source", "url", "locator", "first_seen")

# kind -> (relative path, id field or None, required fields, source required?, extra check)
KINDS = {
    "entity": ("03_entity_index.jsonl", "entity_id", ("name", "type", "coverage"), True, None),
    "event": ("04_event_index.jsonl", "event_id", ("name", "coverage", "source"), True, None),
    "term": ("05_term_index.jsonl", "term_id", ("zh", "definition", "coverage"), False, None),
    "conflict": ("10_conflicts.jsonl", "id", ("summary", "versions", "sources", "resolution"), True, None),
    "unknown": ("11_unknowns.jsonl", "id", ("dimension", "question", "impact"), False, None),
    "worldgen": ("D1_seed/worldgen_dimensions.jsonl", "id", ("dimension", "name", "rules", "confidence"), True, None),
    "trend": ("D2_trends/trends.jsonl", "id", ("name", "direction", "evidence", "observables"), True, None),
    "micro_event": ("D2_trends/micro_variables.jsonl", "id", ("name", "category", "trigger", "effect", "persistence"), True, None),
    "causal": ("D2_trends/causal_links.jsonl", "id", ("from", "to", "type"), True, None),
    "wiki_claim": ("D3_plot/wiki_claims.jsonl", "id", ("version", "chapter", "claim", "claim_source"), True, None),
    "plot": ("D3_plot/plot_expansion.jsonl", "id", ("version", "chapter", "scene", "expansion", "sources"), True, None),
    "preset_beat": ("D3_plot/preset_beats.jsonl", "id", ("frame", "label", "lore_refs", "source"), True, None),
    "gap": ("D3_plot/gaps.jsonl", "id", ("version", "question", "impact"), False, None),
    "scene": ("D4_dialogue/scenes.jsonl", "id", ("name", "participants", "trigger", "coverage", "evidence"), True, None),
    "dialogue": ("D4_dialogue/dialogues.jsonl", "id", ("scene_id", "order", "verbatim", "source", "locator", "confidence"), True, None),
    "loop": ("D5_loops/loops.jsonl", "id", ("loop", "phase", "evidence", "source"), True, None),
    "anchor": ("D5_loops/official_anchors.jsonl", "id", ("loop", "verbatim", "source", "locator"), True, None),
    "terminal": ("D6_terminal/terminals.jsonl", "id", ("text", "kind", "trigger", "source", "locator", "confidence"), True, None),
    "multilingual": ("D6_terminal/multilingual.jsonl", "id", ("term_id", "zh"), True, None),
    "fragment": ("D7_community/fragments.jsonl", "id", ("platform", "type", "url", "source_grade"), True, None),
    "crosscheck": ("D7_community/crosscheck.jsonl", "id", ("fragment_id", "claim", "result"), False, None),
    "debunked": ("D7_community/debunked.jsonl", "id", ("claim", "status", "reason"), False, None),
    "relation": ("D8_characters/relations.jsonl", None, ("from", "to", "type"), True, None),
    "scenario": ("D8_characters/scenarios.jsonl", "id", ("character", "given", "expect", "source"), True, None),
    "guard": ("D8_characters/ooc_guards.jsonl", "id", ("character", "guard", "severity"), False, None),
}

ID_PATTERNS = {
    "scene": r"^SCN-[0-9]{3}$",
    "dialogue": r"^DLG-[0-9]{3}$",
    "loop": r"^LOOP-(P[0-9]-)?[0-9]{1,8}$",
    "terminal": r"^TRM-[0-9]{3}$",
    "preset_beat": r"^PB-[0-9]{3}$",
    "worldgen": r"^WG-[0-9]{3}$",
    "micro_event": r"^MV-[0-9]{3}$",
    "trend": r"^TREND-[0-9]{3}$",
}


class Report:
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.counts: dict[str, int] = {}

    def err(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)


def read_jsonl(path, rep, kind):
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                rep.err(f"{kind}:{lineno} JSON decode failed: {exc}")
                continue
            if not isinstance(obj, dict):
                rep.err(f"{kind}:{lineno} record is not an object")
                continue
            out.append((lineno, obj))
    return out


def has_source(obj):
    return any(k in obj and obj[k] not in (None, "", [], {}) for k in SOURCE_KEYS)


def main(argv=None):
    ap = argparse.ArgumentParser(description="lint the lore corpus")
    ap.add_argument("--json", action="store_true", help="machine readable output")
    args = ap.parse_args(argv)

    rep = Report()
    ids: dict[str, dict[str, str]] = {}
    loaded: dict[str, list[dict]] = {}

    for kind, (rel, id_field, required, need_source, _) in KINDS.items():
        path = os.path.join(LORE, rel.replace("/", os.sep))
        if not os.path.exists(path):
            rep.err(f"{kind}: missing file {rel}")
            continue
        rows = read_jsonl(path, rep, kind)
        rep.counts[kind] = len(rows)
        ids.setdefault(kind, {})
        got = []
        for lineno, obj in rows:
            got.append(obj)
            rid = obj.get(id_field) if id_field else None
            if id_field:
                if not rid:
                    rep.err(f"{rel}:{lineno} missing id field '{id_field}'")
                elif not isinstance(rid, str):
                    rep.err(f"{rel}:{lineno} id is not a string")
                elif rid in ids[kind]:
                    rep.err(f"{rel}:{lineno} duplicate id {rid} (first at {ids[kind][rid]})")
                else:
                    ids[kind][rid] = f"{rel}:{lineno}"
                    pat = ID_PATTERNS.get(kind)
                    if pat and not re.match(pat, rid):
                        rep.err(f"{rel}:{lineno} id {rid} does not match {pat}")
            for field in required:
                if field not in obj or obj[field] is None:
                    rep.err(f"{rel}:{lineno} missing required field '{field}'")
                elif obj[field] in ("", [], {}):
                    rep.warn(f"{rel}:{lineno} empty required field '{field}'")
            if "confidence" in obj and obj["confidence"] not in CONFIDENCE:
                rep.err(f"{rel}:{lineno} bad confidence {obj['confidence']!r}")
            if need_source and not has_source(obj):
                rep.err(f"{rel}:{lineno} no source/locator field")
            if kind == "micro_event":
                cat = obj.get("category")
                if cat not in {
                    "individual", "resource", "technology", "belief",
                    "population", "geography", "event", "protocol", "external",
                }:
                    rep.err(f"{rel}:{lineno} bad category {cat!r}")
        loaded[kind] = got

    # character cards live in a directory, not a JSONL file
    cdir = os.path.join(LORE, "D8_characters", "characters")
    cards = []
    if os.path.isdir(cdir):
        for name in sorted(os.listdir(cdir)):
            if not name.endswith(".json"):
                continue
            path = os.path.join(cdir, name)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    obj = json.load(f)
            except (OSError, json.JSONDecodeError) as exc:
                rep.err(f"characters/{name} unreadable: {exc}")
                continue
            cards.append(obj)
            cid = obj.get("id")
            if not cid:
                rep.err(f"characters/{name} missing id")
            elif not re.match(r"^CHR-[0-9]{3}$", cid):
                rep.err(f"characters/{name} bad id {cid!r}")
            elif cid in ids.setdefault("character", {}):
                rep.err(f"characters/{name} duplicate id {cid}")
            else:
                ids["character"][cid] = f"characters/{name}"
            rules = obj.get("decision_rules") or []
            if len(rules) < 3:
                rep.err(f"characters/{name} has {len(rules)} decision_rules (<3)")
            for rule in rules:
                if not rule.get("source"):
                    rep.err(f"characters/{name} rule {rule.get('id')} has no source")
            if "confidence" in obj and obj["confidence"] not in CONFIDENCE:
                rep.err(f"characters/{name} bad confidence")
        rep.counts["character"] = len(cards)
    else:
        rep.err("missing directory D8_characters/characters")
    loaded["character"] = cards

    # ---- cross references -------------------------------------------------
    def refs(kind, rid):
        return rid in ids.get(kind, {})

    for d in loaded.get("dialogue", []):
        sid = d.get("scene_id")
        if sid and not refs("scene", sid):
            rep.err(f"dialogue {d.get('id')} references unknown scene {sid}")
        for nxt in d.get("next") or []:
            if not refs("dialogue", nxt):
                rep.err(f"dialogue {d.get('id')} next -> unknown line {nxt}")

    for s in loaded.get("scene", []):
        for part in s.get("participants") or []:
            if part.startswith("SYS-"):
                continue
            if not refs("character", part):
                rep.warn(f"scene {s.get('id')} participant {part} not in character cards")

    for c in cards:
        for rel in c.get("relations") or []:
            target = rel.get("target")
            if target and not refs("character", target):
                rep.warn(f"character {c.get('id')} relation target {target} has no card")

    for sc in loaded.get("scenario", []):
        ch = sc.get("character")
        if ch and not refs("character", ch):
            rep.err(f"scenario {sc.get('id')} unknown character {ch}")

    for mv in loaded.get("micro_event", []):
        for link in mv.get("causal_links") or []:
            if not (refs("micro_event", link) or refs("trend", link)):
                rep.warn(f"micro_event {mv.get('id')} causal link {link} unresolved")

    for link in loaded.get("causal", []):
        for end in (link.get("from"), link.get("to")):
            if end and not (refs("micro_event", end) or refs("trend", end)
                            or refs("loop", end) or refs("worldgen", end)
                            or refs("entity", end)):
                rep.warn(f"causal {link.get('id')} endpoint {end} unresolved")

    for pl in loaded.get("plot", []):
        for dlg in pl.get("dialogue_refs") or []:
            if not refs("dialogue", dlg):
                rep.warn(f"plot {pl.get('id')} dialogue ref {dlg} unresolved")

    for cc in loaded.get("crosscheck", []):
        fid = cc.get("fragment_id")
        if fid and not refs("fragment", fid):
            rep.err(f"crosscheck {cc.get('id')} unknown fragment {fid}")

    for db in loaded.get("debunked", []):
        fid = db.get("fragment_id")
        if fid and not refs("fragment", fid):
            rep.err(f"debunked {db.get('id')} unknown fragment {fid}")

    if args.json:
        print(json.dumps(
            {"counts": rep.counts, "errors": rep.errors, "warnings": rep.warnings},
            ensure_ascii=False, indent=2,
        ))
    else:
        print("lore lint")
        for kind in sorted(rep.counts):
            print(f"  {kind:<12} {rep.counts[kind]}")
        print(f"  errors   {len(rep.errors)}")
        print(f"  warnings {len(rep.warnings)}")
        for msg in rep.errors[:80]:
            print(f"  ERROR {msg}")
        for msg in rep.warnings[:40]:
            print(f"  WARN  {msg}")

    return 1 if rep.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
