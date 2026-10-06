#!/usr/bin/env python3
"""双轨等价：证明「条件投递」的退化形式与旧日程表**逐位等价**。

    python tools/dual_track.py                          # plot，2 万帧
    python tools/dual_track.py --preset nullify --frames 40000

做法 —— 同一个世界跑两遍：

  A 原样：投递条目只有声明帧（今天的行为）；
  B 双轨：给**每一条**投递加上退化条件 `when: frame >= <声明帧>`，并把谓词递给内核。

退化条件在声明帧当天即成立 ⇒ 两路的触发帧应当完全一样。
一样就证明「加 `when` 这件事本身没改语义」—— 之后放开读世界状态才有据可依。

比对的不是"看起来差不多"，而是**逐条事件 + 终局状态摘要（digest）+ 关键计数**。
退出码：一致 0，不一致 1。
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import BAR, ROOT, services               # noqa: E402

from engine.core import run                          # noqa: E402
from engine.loader import Config, DataSet            # noqa: E402
from engine.namer import Namer                       # noqa: E402


def run_once(preset, frames, seed, conditional):
    """跑一次。`conditional=True` 时把每条投递都改成退化条件形式并交内核求值。"""
    data = DataSet(ROOT, preset=preset)
    ctx = Config(ROOT, lex_overlay=data.preset.get("lexicon"))
    namer = Namer(ctx, data.anchors)
    kw = {}
    if conditional:
        from engine.conditions import evaluate

        for rec in data.disturbances:
            rec["when"] = f'frame >= {int(rec["frame"])}'
        # `conditioned` 是 DataSet 建索引时算好的，这里改了记录得重建（就这一行）
        data.conditioned = [r for r in data.disturbances if r.get("when")]
        kw["rules"] = evaluate
        print(f"  双轨：{len(data.conditioned)} 条投递改成退化条件"
              f"（when: frame >= <声明帧>）")
    traj = run(ctx, data, seed=seed, max_frames=frames, namer=namer,
               runtime=services(), **kw)
    return traj


def compare(a, b):
    """逐条比对。返回 (是否一致, 说明列表)。"""
    notes, ok = [], True

    notes.append(f"事件条数　A={len(a.records)}　B={len(b.records)}")
    if len(a.records) != len(b.records):
        ok = False
    else:
        for i, (ra, rb) in enumerate(zip(a.records, b.records)):
            if ra != rb:
                ok = False
                notes.append(f"首个不同在第 {i} 条：")
                notes.append(f"    A {ra}")
                notes.append(f"    B {rb}")
                break

    da, db = a.final.digest(), b.final.digest()
    notes.append(f"终局状态 digest　A={da[:16]}　B={db[:16]}"
                 + ("　（一致）" if da == db else "　（不同！）"))
    ok = ok and (da == db)

    for field in ("iterations", "skipped_frames", "reached_frame",
                  "verdict", "stop_reason", "deadlock"):
        va, vb = getattr(a, field), getattr(b, field)
        same = va == vb
        notes.append(f"{field:<14} A={va}　B={vb}" + ("" if same else "　（不同！）"))
        ok = ok and same
    notes.append(f"{'涌现角色数':<12} A={len(a.personas)}　B={len(b.personas)}")
    ok = ok and len(a.personas) == len(b.personas)
    return ok, notes


def main():
    ap = argparse.ArgumentParser(description="条件投递的退化形式 vs 旧日程表")
    ap.add_argument("--preset", default="plot")
    ap.add_argument("--frames", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()

    print(BAR)
    print(f"双轨等价：{args.preset} · {args.frames:,} 帧 · seed={args.seed}")
    print(BAR)
    print("  A 旧日程表（只有声明帧）")
    ta = run_once(args.preset, args.frames, args.seed, conditional=False)
    print("  B 退化条件（when: frame >= 声明帧）")
    tb = run_once(args.preset, args.frames, args.seed, conditional=True)
    print()

    ok, notes = compare(ta, tb)
    print(BAR)
    for line in notes:
        print(line)
    print(BAR)
    if ok:
        print("✓ 两路逐条一致：加 when（退化形式）没有改语义。")
        return 0
    print("✗ 两路不一致 —— 条件槽改动了语义，不能就此放开。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
