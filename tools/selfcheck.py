#!/usr/bin/env python3
"""一次跑完全部自检 —— CI 与提交前的统一入口。

    python tools/selfcheck.py            # 快档（默认，几十秒量级）
    python tools/selfcheck.py --full     # 连 plot / nullify 的全量演算一起跑
    python tools/selfcheck.py --list     # 只列出会跑哪些步骤

每一步都是一个独立进程、独立退出码；这里只负责按顺序跑完、汇总成一张表。
任一步失败即整体失败（退出码 1）。

快档为什么不含 plot / nullify：它们的验收要跑满三千多万帧（各数分钟），
不适合每次提交都跑 —— 那是 --full 的事。快档保住的是「机制连通 + 红线 + 单测」。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
GOLDEN = os.path.join(ROOT, "tests", "golden_fingerprints.json")

# 打印中文前把 stdio 钉成 UTF-8（英文 Windows 默认 cp1252，打印会 UnicodeEncodeError）。
# 与 engine/__init__.py 的同一处兜底一致；本脚本只在 `_fingerprint_args()` 里【延迟】导入
# engine，走不到那条路时就没有兜底，故自带一份。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError):
        pass


def _step(title, args):
    return (title, [PY] + args)


def _fingerprint_args():
    """指纹步骤的参数：与参考环境不一致时自动降级为「只比结构层」。

    digest 是量化 float32 的哈希，只在**参考环境**（OS / CPU 架构 / Python / numpy
    四项全同）上逐位可比 —— 判定复用 `tools/snapshot.py::digest_comparable`，不在这里
    重写一遍。不一致时只比结构层（整数 / 枚举 / 席位编号），它跨平台成立，仍能抓到真回归。
    """
    base = ["tools/snapshot.py", "--fast"]
    try:
        with open(GOLDEN, encoding="utf-8") as f:
            ref = json.load(f).get("_reference_platform")
    except (OSError, ValueError):
        return base
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    from snapshot import digest_comparable            # noqa: E402
    ok, _why = digest_comparable(ref)
    return base if ok else base + ["--structural"]


# 快档：红线 → 判据 → 单元测试 → 世界连通
QUICK = [
    _step("红线 1：引擎零专有名词", ["tools/grep_forbidden.py"]),
    _step("红线 2：逐步推进 lint（禁止解析求解 / 预读未来）", ["tools/stepwise_lint.py"]),
    _step("红线 3：内核分层（内核不许 import 服务 / 界面）", ["tools/layer_lint.py"]),
    _step("环境自检（解释器 / 依赖 / 数据）", ["tools/export.py", "--check-only"]),
    _step("单元测试", ["-m", "unittest", "discover", "-s", "tests"]),
    _step("判据 3：数据替换（替代世界）", ["tools/alt_world/run_alt.py"]),
    _step("判据 6：涌现无写回（data/ 只读）", ["tools/writeback_probe.py"]),
    _step("世界：tide（耗尽结论的可达世界）", ["run.py", "--preset", "tide"]),
]

# 全量档：四个世界的完整验收（各含断言与时间线核对）+ 复用等价（判据 5）
FULL = [
    _step("世界：emergent（涌现版）", ["run.py", "--preset", "emergent"]),
    _step("世界：plot（剧情锚定版）", ["run.py", "--preset", "plot"]),
    _step("世界：nullify（否定版）", ["run.py", "--preset", "nullify"]),
    # 「证伪」的演示世界：自带 genesis（探针永不达标）+ 结构冻结；它的裁决只在
    # 3355 万帧跑满、外生穷尽那一刻才被接受，故**必须在这里跑**（短指纹抓不到）。
    _step("世界：refuted（证伪结论的可达世界）", ["run.py", "--preset", "refuted"]),
    # 判据 5：复用参考轨道【没有伪造世界状态】。它跑两遍（复用 / 逐帧真跑），
    # 默认预算要四分钟；这里压一档（时间刻度 ×1/100、帧 6 万）—— 被验证的性质
    # （到访帧签名逐一相同 + 结构态序列一致）与时间刻度无关，而 attempt_period
    # 不被压缩，故循环期仍有真实的尝试落点。
    _step("判据 5：复用等价（复用 vs 逐帧真跑）",
          ["tools/reuse_equivalence.py", "--fast", "--frames", "60000"]),
    # 判据 4 的动态部分：**存档点必须落在死循环/复用区间之内**才有意义（否则只是
    # 验了常规帧）。故带 --fast 跑 60000 帧、在 k=30000 处存档 —— 提速后死循环早
    # 已开始，续跑一定会走「重建循环 + 沿参考轨道复用」这条路径，正是要验的那条。
    _step("判据 4：帧截断复现（存档点落在复用区间内）",
          ["tools/checkpoint_replay.py", "--fast", "--frames", "60000"]),
]

#: 轨迹指纹：改动引擎后，帧号 / 裁决 / 角色数有没有动过（快档只核对快条目）
SNAPSHOT = [_step("轨迹指纹（改了引擎就看这里）", _fingerprint_args())]


def run_step(title, argv):
    print(f"\n=== {title} ===")
    print("  $ python " + " ".join(argv[1:]))
    t0 = time.time()
    proc = subprocess.run(argv, cwd=ROOT)
    return proc.returncode == 0, time.time() - t0


def main():
    ap = argparse.ArgumentParser(description="一次跑完全部自检")
    ap.add_argument("--full", action="store_true",
                    help="连 plot / nullify 的全量演算一起跑（数分钟）")
    ap.add_argument("--no-snapshot", action="store_true",
                    help="跳过轨迹指纹核对")
    ap.add_argument("--list", action="store_true", help="只列出会跑哪些步骤")
    args = ap.parse_args()

    steps = list(QUICK)
    if not args.no_snapshot:
        steps += SNAPSHOT
    if args.full:
        steps += FULL

    if args.list:
        print("自检步骤（按顺序）：")
        for title, _argv in steps:
            print("  · " + title)
        return 0

    print("δ-me13 自检" + ("（全量档）" if args.full else "（快档）"))
    results = []
    for title, argv in steps:
        ok, dt = run_step(title, argv)
        results.append((title, ok, dt))

    print("\n" + "=" * 72)
    print("  自检汇总")
    print("=" * 72)
    for title, ok, dt in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {title:<34} {dt:>7.1f}s")
    bad = [t for t, ok, _ in results if not ok]
    print("-" * 72)
    if bad:
        print(f"  未通过 {len(bad)}/{len(results)}：" + "、".join(bad))
        return 1
    print(f"  全部通过（{len(results)} 步，合计 {sum(d for _t, _o, d in results):.1f}s）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
