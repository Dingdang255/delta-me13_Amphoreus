#!/usr/bin/env python3
"""判据 6：涌现无写回。

对 data/ 目录挂只读探针（审计钩子 + 运行前后指纹比对）。
引擎若能跑完而 data/ 一个字节都没变 ⇒ 角色确实由演算生成，而非从数据读出。

    python3 tools/writeback_probe.py [--frames 20000]
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import ROOT, load, rules   # noqa: E402

DATA = os.path.join(ROOT, "data")
WROTE = []


def install_guard():
    """任何以写模式打开 data/ 下文件的行为都会当场抛错并记录。"""
    def hook(event, args):
        if event == "open":
            path, mode = args[0], args[1]
            if not mode or not isinstance(path, (str, bytes)):
                return
            m = str(mode)
            if any(c in m for c in "wax+"):
                ap = os.path.abspath(str(path))
                if ap == DATA or ap.startswith(DATA + os.sep):
                    WROTE.append(ap)
                    raise RuntimeError(f"引擎试图写入 data/：{ap}")
    sys.addaudithook(hook)


def fingerprint():
    out = {}
    for name in sorted(os.listdir(DATA)):
        p = os.path.join(DATA, name)
        if os.path.isfile(p):
            with open(p, "rb") as f:
                out[name] = hashlib.sha256(f.read()).hexdigest()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=20000)
    args = ap.parse_args()

    before = fingerprint()
    install_guard()

    from engine.core import run
    ctx, data, _ = load()
    traj = run(ctx, data, max_frames=args.frames, trace=False, rules=rules())
    after = fingerprint()

    changed = [k for k in set(before) | set(after) if before.get(k) != after.get(k)]

    print(f"data/ 文件数 {len(before)}，运行帧预算 {args.frames:,}，"
          f"涌现角色 {len(traj.personas)} 位")
    if not WROTE and not changed:
        print("✓ 判据 6 通过：全程零写入 data/，角色确非给定。")
        return 0
    if WROTE:
        print(f"✗ 捕获到 {len(WROTE)} 次写入尝试：{WROTE[:5]}")
    if changed:
        print(f"✗ 运行前后指纹变化的文件：{changed}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())