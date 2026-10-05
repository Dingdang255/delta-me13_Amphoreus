#!/usr/bin/env python3
"""判据 5：命名正交性。

把命名器整个换掉（换成哑命名器 / 换一套音位表），再跑一遍。
若 Trajectory 逐迭代摘要与角色【非名字】属性均不变 ⇒ 名字只是表层，不参与运算。

    python3 tools/naming_orthogonality.py [--frames 40000]
"""
from __future__ import annotations

import argparse
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import load, capture, diff_captures, persona_identity   # noqa: E402

from engine.namer import Namer                                        # noqa: E402


class SilentNamer:
    """完全不出名字的命名器：如果轨迹变了，说明名字偷偷参与了运算。"""

    def machine_name(self, fingerprint, serial, rank=-1, order=None):
        return "x"

    def persona_name(self, persona):
        return "", ""

    def title(self, locus):
        return "", ""

    def title_by_id(self, locus_id):
        return "", ""

    def export_anchors(self, personas):
        return []


def scrambled_namer(ctx, anchors):
    """换一套音位表（打乱 onsets / nuclei / codas / translit）。"""
    ctx2 = copy.deepcopy(ctx)
    ph = ctx2.phonology
    for key in ("onsets", "nuclei", "codas"):
        if ph.get(key):
            ph[key] = list(reversed(ph[key]))
    return Namer(ctx2, anchors)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=20000)
    ap.add_argument("--fast", nargs="?", type=int, const=100, default=0,
                    metavar="K", help="测试提速：时间刻度按 K 压缩（默认 100）")
    args = ap.parse_args()
    N = args.frames

    ctx, data, _ = load(fast=args.fast)
    traj_a, cap_a = capture(ctx, data, N)

    ctx_b, _, _ = load(fast=args.fast)
    traj_b, cap_b = capture(ctx_b, data, N, namer=SilentNamer())

    ctx_c, _, _ = load(fast=args.fast)
    traj_c, cap_c = capture(ctx_c, data, N, namer=scrambled_namer(ctx_c, data.anchors))

    ok = True
    for label, cap in (("哑命名器", cap_b), ("打乱音位表", cap_c)):
        bad = diff_captures(cap_a, cap)
        if bad is None:
            print(f"✓ {label}：逐迭代摘要与基准完全一致")
        else:
            ok = False
            print(f"✗ {label}：第 {bad[0]} 帧摘要不同 → 命名影响了演算")

    if persona_identity(traj_a) == persona_identity(traj_b) == persona_identity(traj_c):
        print(f"✓ 角色非名字属性一致（{len(traj_a.personas)} 位的 serial/承位/能力/指纹均不变）")
    else:
        ok = False
        print("✗ 角色非名字属性发生变化 → 命名与涌现不正交")

    # 反向证据：名字本身确实变了
    na = [traj_a.namer.persona_name(p) for p in traj_a.personas[:3]]
    nb = [traj_c.namer.persona_name(p) for p in traj_c.personas[:3]]
    print(f"  （对照）基准前三名 {na}  vs  打乱音位表前三名 {nb}")

    print("✓ 判据 5 通过：名字是 L5 表层，与演算正交。" if ok
          else "✗ 判据 5 失败。")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())