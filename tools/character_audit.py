#!/usr/bin/env python3
"""Audit agent cards and replay every scenario through the decision step.

    python tools/character_audit.py
    python tools/character_audit.py --check
    python tools/character_audit.py --json
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

from apps import agents  # noqa: E402

SCENARIOS = os.path.join(ROOT, "lore", "D8_characters", "scenarios.jsonl")
MIN_RULES = 3
MIN_PASS_RATE = 0.90


def load_scenarios(path=SCENARIOS):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def audit(cards, scenarios):
    errors = []
    warnings = []
    for cid, card in cards.items():
        if len(card.rules) < MIN_RULES:
            errors.append(f"{cid}: {len(card.rules)} decision_rules (<{MIN_RULES})")
        seen = set()
        for rule in card.rules:
            if not rule.id:
                errors.append(f"{cid}: rule without id")
            elif rule.id in seen:
                errors.append(f"{cid}: duplicate rule id {rule.id}")
            seen.add(rule.id)
            if not rule.source:
                errors.append(f"{cid}/{rule.id}: no source")
            if not rule.then:
                errors.append(f"{cid}/{rule.id}: empty then")
        if not card.guards:
            warnings.append(f"{cid}: no ooc_guards")
        if not card.speech:
            warnings.append(f"{cid}: no speech profile")

    counts = {"pass": 0, "mismatch": 0, "unknown": 0, "no_rule": 0}
    rows = []
    for scenario in scenarios:
        cid = scenario.get("character")
        card = cards.get(cid)
        if card is None:
            errors.append(f"{scenario.get('id')}: unknown character {cid}")
            continue
        result = agents.scenario_check(card, scenario)
        counts[result["status"]] = counts.get(result["status"], 0) + 1
        result["official_scene"] = bool(scenario.get("official_scene"))
        rows.append(result)
        if result["status"] == "mismatch":
            errors.append(
                f"{result['scenario']}: expected {result['expected']} got {result['got']}"
                f" (candidates {result.get('candidates')})"
            )

    executable = counts["pass"] + counts["mismatch"]
    pass_rate = (counts["pass"] / executable) if executable else 0.0
    if executable and pass_rate < MIN_PASS_RATE:
        errors.append(f"pass rate {pass_rate:.2%} below {MIN_PASS_RATE:.0%}")

    ambiguous = [r for r in rows if r.get("ambiguous")]
    return {
        "cards": len(cards),
        "rules": sum(len(c.rules) for c in cards.values()),
        "executable_rules": sum(len(c.executable_rules) for c in cards.values()),
        "scenarios": len(scenarios),
        "counts": counts,
        "pass_rate": round(pass_rate, 4),
        "ambiguous": len(ambiguous),
        "errors": errors,
        "warnings": warnings,
        "rows": rows,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="agent card audit")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    cards = agents.load_cards()
    scenarios = load_scenarios()
    report = audit(cards, scenarios)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"cards {report['cards']} · rules {report['rules']}"
              f" · executable {report['executable_rules']}")
        print(f"scenarios {report['scenarios']} · " +
              " · ".join(f"{k} {v}" for k, v in report["counts"].items()))
        print(f"pass rate {report['pass_rate']:.2%} · ambiguous {report['ambiguous']}")
        if report["warnings"]:
            print()
            for line in report["warnings"][:12]:
                print(f"  WARN  {line}")
        print()
        print(f"  errors {len(report['errors'])}")
        for line in report["errors"][:40]:
            print(f"  ERROR {line}")

    if report["errors"]:
        return 1
    if args.check:
        print()
        print("character cards ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
