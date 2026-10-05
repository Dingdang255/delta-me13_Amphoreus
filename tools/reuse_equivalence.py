#!/usr/bin/env python3
"""计划 #5：等价性检查（真正演算的硬指标）。

死循环期沿参考轨道复用【跳帧】。复用成立的前提是：世界结构在那段区间里确实
不变。这里做一次对照 ——

  A 复用：生产路径，循环期不做逐帧重算，只在事件帧落点上前进。
  B 真跑：关掉复用（reuse_reference=False），循环期逐帧真算。

要求：A 走过的【每一帧】，其世界结构签名都等于 B 在同一帧的签名。
B 里循环区间的结构必须恒定（与 A 的 ref 一致）—— 否则复用就是在伪造状态。

    python3 tools/reuse_equivalence.py [--frames 120000]
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import load                                   # noqa: E402

from engine.core import run                                 # noqa: E402


def sweep(reuse: bool, frames: int, fast: int = 0):
    """跑一遍，逐【到访帧】记下世界结构签名；返回 (frame->sig, traj)。"""
    ctx, data, _ = load(fast=fast)
    ctx.params["reuse_reference"] = reuse
    seen = {}

    def watch(n, st, traj):
        seen[n] = st.world_signature()
        return True

    traj = run(ctx, data, max_frames=frames, trace=False, watch=watch)
    return seen, traj


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=120000)
    ap.add_argument("--fast", nargs="?", type=int, const=100, default=0,
                    metavar="K", help="测试提速：时间刻度按 K 压缩（默认 100）")
    args = ap.parse_args()
    N = args.frames

    a, ta = sweep(True, N, args.fast)      # 复用
    b, tb = sweep(False, N, args.fast)     # 逐帧真跑
    an_start = int(ta.spans[0][1]) if ta.spans else None

    print(f"帧预算 N={N:,}  循环起点={an_start}  到访帧 A={len(a):,}  B={len(b):,}")
    print(f"复用跳帧 {ta.skipped_frames:,}  真跑跳帧 {tb.skipped_frames:,}")

    # ① A 的每个到访帧，B 必须给出【相同】结构签名
    bad = [(f, a[f], b.get(f)) for f in a if b.get(f) != a[f]]

    # ② 与跳帧无关的口径：循环区间内世界走过的【结构态序列】必须一致。
    #    尝试落点每轮真实演算、留痕者提交进主轨道 —— 只要两侧去重后的结构态
    #    序列相同，就说明复用没有跳过任何一次真实改变，也没有凭空造出改变。
    seq_a = seq_b = None
    if an_start is not None:
        seq_a = _distinct_seq(a, an_start)
        seq_b = _distinct_seq(b, an_start)
        print(f"循环区间的结构态序列：复用 {len(seq_a)} 段  真跑 {len(seq_b)} 段"
              f"（应相等）")

    if bad:
        print(f"✗ 判据 5 失败：{len(bad)} 帧的复用签名与真跑不符，例：")
        for f, sa, sb in bad[:5]:
            print(f"    帧{f}: 复用={sa}  真跑={sb}")
        return 1
    if seq_a != seq_b:
        print(f"✗ 判据 5 失败：结构态序列不一致\n    复用={seq_a}\n    真跑={seq_b}")
        return 1
    print("✓ 判据 5 通过：复用未伪造任何状态 —— 到访帧结构与逐帧真跑逐一相同，"
          "循环区间的结构态序列一致（每次留痕都真实发生、且只在落点上）。")
    return 0


def _distinct_seq(seen, an_start):
    """某一侧在循环区间里走过的【去重且保序】结构签名序列。"""
    out = []
    for f in sorted(seen):
        if f < an_start:
            continue
        s = seen[f]
        if not out or out[-1] != s:
            out.append(s)
    return out


if __name__ == "__main__":
    raise SystemExit(main())
