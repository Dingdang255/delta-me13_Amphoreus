#!/usr/bin/env python3
"""涌现审计（人工比对用）。

列出全部涌現人格体及其中枢属性，供人工比对原作。
不判断对错，只呈现"引擎自己长出了谁"。

    python3 tools/emergence_audit.py [--frames 40000] [--seed 0]
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import load   # noqa: E402

from engine.render import Renderer   # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()

    from engine.core import run
    ctx, data, _ = load()
    traj = run(ctx, data, seed=args.seed, max_frames=args.frames, trace=False)
    R = Renderer(ctx)

    print(f"命题 {data.genesis['proposition']['id']}  帧预算 {args.frames:,}  "
          f"世界种子 {ctx.seed}  涌现 {len(traj.personas)} 位")
    print(f"{'序号':>4} {'涌现帧':>9} {'承位':<8}{'世界名':<12}{'拉丁名':<14}能力")
    cap_count = Counter()
    for i, p in enumerate(traj.personas, 1):
        latin, hanzi = traj.namer.persona_name(p)
        loc = R.region(ctx.loci[p.locus_order].id) if p.locus_order is not None else "未承位"
        caps = ",".join(sorted(p.capabilities)) or "—"
        for c in p.capabilities:
            cap_count[c] += 1
        print(f"{i:>4} {p.surfaced_frame:>9,} {loc:<8}{hanzi:<12}{latin:<14}{caps}")
    print("\n能力分布：", dict(cap_count))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())