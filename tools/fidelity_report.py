#!/usr/bin/env python3
"""Skeleton of the fidelity report (P0), scores land in P7.

Right now it only proves two things:
  * `lore/canon/` loads through `apps.canon.CanonBundle` (hash-verified);
  * each of the eight collection dimensions has at least one record and can be
    counted without touching the engine.

    python tools/fidelity_report.py            # table
    python tools/fidelity_report.py --json     # machine readable
    python tools/fidelity_report.py --check    # exits 2: scoring not implemented

The `--check` exit code is deliberately non-zero so this cannot be mistaken for
the real gate before P7 defines the weights in `config/fidelity.json`.
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

DIMENSIONS = {
    "D1_seed": ("worldgen",),
    "D2_trends": ("trend", "micro_event", "causal"),
    "D3_plot": ("plot", "wiki_claim", "gap"),
    "D4_dialogue": ("dialogue", "scene"),
    "D5_loops": ("loop", "anchor"),
    "D6_terminal": ("terminal", "multilingual"),
    "D7_community": ("fragment", "crosscheck", "debunked"),
    "D8_characters": ("character", "scenario", "guard", "relation"),
}

#: the P0 skeleton only asserts "non-empty"; P7 replaces this with weights
MIN_ENTRIES = {dim: 1 for dim in DIMENSIONS}


def collect():
    from apps import canon  # imported here so --help works without a bundle

    try:
        bundle = canon.CanonBundle.load()
    except canon.CanonError as exc:
        return {"ok": False, "error": str(exc), "dimensions": {}}

    rows = {}
    for dim, kinds in DIMENSIONS.items():
        counts = {kind: len(bundle.ids_of_kind(kind)) for kind in kinds}
        total = sum(counts.values())
        coverage = 1.0 if total >= MIN_ENTRIES[dim] else 0.0
        rows[dim] = {
            "counts": counts,
            "entries": total,
            "coverage": coverage,
            "score": None,
        }
    return {
        "ok": True,
        "manifest": {
            "schema_version": bundle.manifest.get("schema_version"),
            "entry_count": bundle.manifest.get("entry_count"),
            "source_digest": bundle.manifest.get("source_digest"),
        },
        "dimensions": rows,
        "weighted_score": None,
        "note": "weights and scoring are defined in P7 (config/fidelity.json)",
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="fidelity report (skeleton)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)

    report = collect()

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        if not report["ok"]:
            print(f"no usable bundle: {report['error']}")
        else:
            manifest = report["manifest"]
            print(f"bundle {manifest['schema_version']} · {manifest['entry_count']} entries"
                  f" · {manifest['source_digest'][:12]}")
            print()
            print(f"  {'dimension':<14}{'entries':>8}{'coverage':>10}  kinds")
            for dim, row in report["dimensions"].items():
                kinds = ", ".join(f"{k}={v}" for k, v in row["counts"].items())
                print(f"  {dim:<14}{row['entries']:>8}{row['coverage']:>10.2f}  {kinds}")
            print()
            print(f"  weighted score: {report['weighted_score']}  ({report['note']})")

    if args.check:
        print()
        print("fidelity --check is not implemented yet: scoring lands in P7.")
        return 2
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
