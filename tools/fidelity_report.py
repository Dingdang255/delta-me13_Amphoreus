#!/usr/bin/env python3
"""Fidelity gate: score the compiled corpus against ``config/fidelity.json``.

    python tools/fidelity_report.py            # table
    python tools/fidelity_report.py --json     # machine readable
    python tools/fidelity_report.py --md       # markdown table
    python tools/fidelity_report.py --check    # exit 1 when below threshold

The gate is read-only: it loads ``lore/canon/`` through ``apps.canon``, scores
the eight dimensions in ``apps.fidelity`` and prints the result. Weights,
thresholds, coverage marks and gap rules all live in the config file; this
script never adds a score of its own.

``--check`` exits non-zero when the weighted score is below the threshold, when
a single dimension falls under the floor, or when the bundle cannot be loaded.
Gap records are never removed to raise a score -- they are reported, and their
penalty is part of the number.
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

from apps import fidelity  # noqa: E402


def _fmt(value, digits=2):
    return "—" if value is None else f"{value:.{digits}f}"


def markdown(report: dict) -> str:
    if not report.get("ok"):
        return f"**语料不可用**：{report.get('error')}"
    out = [
        f"加权保真分 **{report['weighted_score']:.4f}**"
        f" · 阈值 {report['threshold']:.2f}"
        f" · {'通过' if report['pass'] else '未通过'}",
        "",
        "| 维度 | 条数 | 覆盖 | 可追溯 | 逐字 | 一致性 | 缺口 | 得分 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, row in report["dimensions"].items():
        m = row["metrics"]
        out.append(f"| {name} | {row['entries']} | {_fmt(m['coverage'])} | "
                   f"{_fmt(m['traceability'])} | {_fmt(m['verbatim'])} | "
                   f"{_fmt(m['consistency'])} | {row['penalty']:.2f} | "
                   f"{row['score']:.2f} |")
    gaps = [(name, p) for name, row in report["dimensions"].items()
            for p in row["penalties"]]
    if gaps:
        out.extend(["", "缺口（计入扣分，条目未删除）：", ""])
        for name, p in gaps:
            out.append(f"- `{p['id']}`（{name}）：{p['count']}/{p['denominator']}"
                       f" × {p['cap']:.2f} = −{p['amount']:.4f}")
    if report.get("unassigned_unknowns"):
        out.extend(["", "跨维未知（不计入维度分）：" +
                    "、".join(report["unassigned_unknowns"])])
    if report.get("failures"):
        out.extend(["", "未通过项："])
        out.extend(f"- {line}" for line in report["failures"])
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="fidelity gate")
    ap.add_argument("--json", action="store_true", help="print the full report as JSON")
    ap.add_argument("--md", action="store_true", help="print a markdown table")
    ap.add_argument("--check", action="store_true", help="exit 1 when below threshold")
    args = ap.parse_args(argv)

    report = fidelity.evaluate()

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    elif args.md:
        print(markdown(report))
    else:
        print("\n".join(fidelity.render(report)))

    if not report.get("ok"):
        return 1
    if args.check and not report["pass"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
