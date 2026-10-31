#!/usr/bin/env python3
"""Audit the trend spec and demo the evaluator.

    python tools/trend_audit.py            # coverage + validation
    python tools/trend_audit.py --check    # exit 1 on any spec error
    python tools/trend_audit.py --demo     # run one synthetic view through it
    python tools/trend_audit.py --json
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

from apps import trends  # noqa: E402

CONFIDENCE = {"A", "B", "C", "D", "E", "UNKNOWN"}

DEMO_VIEW = {
    "cycle_count": 33550336,
    "embers_taken": 402604032,
    "memory_rows": 12,
    "entropy": 1.65,
    "noise": 0.71,
}


def validate(spec):
    errors = []
    known_drivers = set(spec.get("drivers", []))
    known_targets = set(spec.get("targets", []))
    for trend_id, trend in spec.get("trends", {}).items():
        status = trend.get("status")
        if status == "unwired":
            if not trend.get("reason"):
                errors.append(f"{trend_id}: unwired without reason")
            continue
        if status != "wired":
            errors.append(f"{trend_id}: unknown status {status!r}")
            continue
        channels = trend.get("channels") or []
        if not channels:
            errors.append(f"{trend_id}: wired without channels")
        seen = set()
        for ch in channels:
            cid = ch.get("id", "?")
            for field in ("id", "type", "target", "kind", "driver", "source", "confidence"):
                if not ch.get(field):
                    errors.append(f"{trend_id}/{cid}: missing {field}")
            if cid in seen:
                errors.append(f"{trend_id}: duplicate channel id {cid}")
            seen.add(cid)
            if ch.get("driver") and ch["driver"] not in known_drivers:
                errors.append(f"{trend_id}/{cid}: driver {ch['driver']!r} not declared")
            if ch.get("target") and ch["target"] not in known_targets:
                errors.append(f"{trend_id}/{cid}: target {ch['target']!r} not declared")
            if ch.get("kind") and ch["kind"] not in trends.KINDS:
                errors.append(f"{trend_id}/{cid}: kind {ch['kind']!r} not supported")
            if ch.get("confidence") and ch["confidence"] not in CONFIDENCE:
                errors.append(f"{trend_id}/{cid}: bad confidence {ch['confidence']!r}")
            kind = ch.get("kind")
            if kind == "saturating" and "rate" not in ch:
                errors.append(f"{trend_id}/{cid}: saturating needs rate")
            if kind == "threshold" and ("threshold" not in ch or "ceiling" not in ch):
                errors.append(f"{trend_id}/{cid}: threshold needs threshold + ceiling")
            if kind == "linear_capped" and "rate" not in ch:
                errors.append(f"{trend_id}/{cid}: linear_capped needs rate")
    return errors


def main(argv=None):
    ap = argparse.ArgumentParser(description="trend spec audit")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    spec = trends.load_spec()
    errors = validate(spec)
    cov = trends.coverage(spec)
    rows = trends.evaluate_all(spec, DEMO_VIEW) if args.demo else []

    if args.json:
        print(json.dumps({"coverage": cov, "errors": errors,
                          "demo": rows}, ensure_ascii=False, indent=2))
    else:
        print(f"trends {cov['trends']} · wired {len(cov['wired'])}"
              f" · channels {cov['channels']} · unwired {len(cov['unwired'])}")
        for trend_id, reason in cov["unwired"].items():
            print(f"  - {trend_id:<10} {reason}")
        print()
        if args.demo:
            print(f"  {'trend':<10}{'channel':<12}{'value':>7}  {'active':<7}target")
            for row in rows:
                print(f"  {row['trend']:<10}{row['channel']:<12}{row['value']:>7.3f}"
                      f"  {str(row['active']):<7}{row['target']}")
            summary = trends.summarize(rows)
            print()
            print(f"  channels {summary['channels']} · active {summary['active']}"
                  f" · strongest {summary['strongest']}")
        print()
        print(f"  errors {len(errors)}")
        for line in errors:
            print(f"  ERROR {line}")

    if errors:
        return 1
    if args.check:
        print()
        print("trend spec ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
