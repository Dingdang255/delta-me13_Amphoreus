#!/usr/bin/env python3
"""判据 1：重标定不变性（引擎不认名字，也不认编号）。

对十二席的 **id 做随机置换**（数据 / 顺序 / 耦合 / mapping 全不动）再跑一遍：
可观测量必须逐项不变 ⇒ 引擎里没有任何"看名字 / 看编号"的分支。

    python3 tools/shuffle_loci.py [--frames 20000] [--shuffles 3]

⚠ 为什么不"连数据一起旋转"（把耦合按同一置换重排、位序也换）：
   那个**更强的命题不成立**，且原因不在引擎的动力学，而在**初始条件** ——
   `engine/core.py` 逐位抽初始个体数是 `for locus in cfg.loci: rng.integers(…)`，
   即按【位置顺序】取同一条随机流；位序一换，每个位置拿到的个体数就变了，
   于是两次跑的根本不是同一个初始世界（实测：`iterations` 488 vs 489）。
   要让那个命题成立，得把初始播种改成"按内容寻址"（随置换一起动）——
   那会改掉所有世界的初始条件，属全量重标定的改动。
   故这里只钉真正成立、也真正重要的那一条：**改名/改编号不改世界**。
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import load, summary, rules   # noqa: E402


def relabelled(ctx, P):
    """只把十二席的 id 按置换 P 重标定 —— 数据 / 顺序 / 耦合 / mapping 一个字都不动。

    于是「世界是否变了」只可能来自引擎读了 id ⇒ 这正是要验的东西。
    """
    for j, locus in enumerate(ctx.loci):
        locus.id = f"L{int(P[j]):02d}"
    return ctx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=20000)
    ap.add_argument("--shuffles", type=int, default=3)
    args = ap.parse_args()

    ctx0, data, _ = load()
    from engine.core import run
    traj0 = run(ctx0, data, max_frames=args.frames, trace=False, rules=rules())
    base = summary(traj0, ctx0)

    print("基准（原始编号）：")
    for k, v in base.items():
        print(f"    {k:<18} {v}")

    ok = True
    for s in range(1, args.shuffles + 1):
        ctx, _, _ = load()
        P = np.random.default_rng(1000 + s).permutation(len(ctx.loci))
        relabelled(ctx, P)
        traj = run(ctx, data, max_frames=args.frames, trace=False, rules=rules())
        got = summary(traj, ctx)
        if got == base:
            print(f"✓ 重标定 #{s} P={list(P)}：可观测量完全一致")
        else:
            ok = False
            print(f"✗ 重标定 #{s}：可观测量变化")
            for k in base:
                if base[k] != got[k]:
                    print(f"      {k}: {base[k]} → {got[k]}")

    print("✓ 判据 1 通过：引擎对席的编号 / 名字不变。" if ok else "✗ 判据 1 失败。")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())