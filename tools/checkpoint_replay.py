#!/usr/bin/env python3
"""判据 4（动态部分）：帧截断复现。

先跑到第 k 帧存档，再从存档续跑到 N；与"从头跑到 N"逐迭代 diff。
完全一致 ⇒ 引擎确实是逐步推进的离散动力系统，不含隐藏解析步骤。

    python3 tools/checkpoint_replay.py [--frames 20000]
"""
from __future__ import annotations

import argparse
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import load, capture                   # noqa: E402

from engine.core import run                          # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=20000)
    ap.add_argument("--fast", nargs="?", type=int, const=100, default=0,
                    metavar="K", help="测试提速：时间刻度按 K 压缩（默认 100）")
    args = ap.parse_args()
    N = args.frames
    k = N // 2

    ctx, data, _ = load(fast=args.fast)
    _, cap_full = capture(ctx, data, N)

    ctx_k, _, _ = load(fast=args.fast)
    traj_k = run(ctx_k, data, max_frames=k, trace=False)
    st_k = copy.deepcopy(traj_k.final)                # 第 k 帧的存档

    ctx_r, _, _ = load(fast=args.fast)
    _, cap_resume = capture(ctx_r, data, N, start_state=st_k, start_frame=k)

    full_after = dict((n, d) for (n, d) in cap_full if n >= k)
    resume = dict(cap_resume)

    # 续跑从【存档那一刻】起步，故它会多访问存档帧本身；此后两者落在同一张
    # 事件网格上。所以判据是：全程访问过的帧，续跑必须都访问过且摘要相同。
    missing = [f for f in sorted(full_after) if f not in resume]
    bad = [(f, full_after[f], resume[f]) for f in sorted(full_after)
           if f in resume and full_after[f] != resume[f]]
    extra = [f for f in sorted(resume) if f not in full_after]

    print(f"帧预算 N={N:,}  存档点 k={k:,}  "
          f"续跑迭代 {len(cap_resume):,} 次（其中存档帧 {len(extra)} 个）")
    if not missing and not bad:
        print("✓ 判据 4 通过：从第 k 帧续跑，在全部共同访问的帧上与从头跑逐迭代一致。")
        return 0
    if bad:
        frame, a, b = bad[0]
        print(f"✗ 判据 4 失败：第 {frame} 帧摘要不一致\n   从头跑={a}\n   续  跑={b}")
    else:
        print(f"✗ 判据 4 失败：续跑漏掉了全程访问过的 {len(missing)} 帧，"
              f"例：{missing[:5]}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())