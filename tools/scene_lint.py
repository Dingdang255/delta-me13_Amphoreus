#!/usr/bin/env python3
"""Lint the scene catalogue compiled from the plot expansions.

    python tools/scene_lint.py
    python tools/scene_lint.py --check
    python tools/scene_lint.py --json
"""
from __future__ import annotations

import argparse
import json
import os
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError):
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from apps import canon, scenes  # noqa: E402

REQUIRED_CHAPTERS = ("3.0", "3.1", "3.2", "3.3", "3.4", "3.5", "3.6", "3.7")
#: known corpus gaps: a chapter whose ownership is still UNKNOWN is a warning, not an error
EXPECTED_GAPS = {"3.4": "章节归属 UNKNOWN（CF-007）"}


def audit(bundle):
    rows = scenes.load(bundle)
    known = {
        "dialogue": bundle.ids_of_kind("dialogue"),
        "scene": bundle.ids_of_kind("scene"),
        "micro_event": bundle.ids_of_kind("micro_event"),
        "trend": bundle.ids_of_kind("trend"),
        "worldgen": bundle.ids_of_kind("worldgen"),
    }
    errors = []
    warnings = []
    for scene in rows:
        for field in ("version", "chapter", "scene", "sources"):
            if not scene.get(field):
                errors.append(f"{scene.get('id')}: missing {field}")
        if not (scene.get("dialogue_refs") or scene.get("scene_refs")
                or scene.get("mechanism_refs")):
            warnings.append(f"{scene.get('id')}: no references at all")
        if not scene.get("verbatim_available"):
            warnings.append(f"{scene.get('id')}: no verbatim text, only summary")
        errors.extend(scenes.unresolved(scene, known))

    cov = scenes.coverage(rows)
    for version in REQUIRED_CHAPTERS:
        if cov.get(version, 0) >= 1:
            continue
        if version in EXPECTED_GAPS:
            warnings.append(f"chapter {version} has no scene: {EXPECTED_GAPS[version]}")
        else:
            errors.append(f"chapter {version} has no scene")

    graph = scenes.dag(rows)
    nodes = set(graph["nodes"])
    if len(nodes) != len(graph["nodes"]):
        errors.append("duplicate scene id in DAG")
    for a, b in graph["edges"]:
        if a not in nodes or b not in nodes:
            errors.append(f"dangling edge {a} -> {b}")

    return {
        "scenes": len(rows),
        "chapters": cov,
        "edges": len(graph["edges"]),
        "errors": errors,
        "warnings": warnings,
        "rows": [scenes.narrate(s) for s in rows],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="scene catalogue lint")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    report = audit(canon.CanonBundle.load())
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"scenes {report['scenes']} · edges {report['edges']}")
        for version, count in report["chapters"].items():
            print(f"  {version}  {count}")
        print()
        print(f"  errors {len(report['errors'])}")
        for line in report["errors"][:30]:
            print(f"  ERROR {line}")
        print(f"  warnings {len(report['warnings'])}")
        for line in report["warnings"][:20]:
            print(f"  WARN  {line}")

    if report["errors"]:
        return 1
    if args.check:
        print()
        print("scenes ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
