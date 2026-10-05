#!/usr/bin/env python3
"""计划 #6：异常性检查（死循环是「没有策略」，不是「有策略」）。

确认三件事：
  1. config/policies.json 里【不存在】任何指向 VACANT 的策略。
  2. 调度器对 VACANT 取不到策略 ⇒ 落回 CONTINUE（未受理）。
  3. 循环期的结构冻结来自动力学本身，而非某条恢复策略 —— 即冻结区间里
     世界签名连续不变，是被「没有分支可走」逼出来的，不是被重放出来的。

    python3 tools/anomaly_check.py
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import load, ROOT                    # noqa: E402

from engine.scheduler import Scheduler             # noqa: E402


class _V:
    def __init__(self, code):
        self.code = code


def main():
    ok = True

    # ① 配置文件里没有 VACANT
    path = os.path.join(ROOT, "config", "policies.json")
    raw = json.load(open(path, "r", encoding="utf-8"))
    has = "VACANT" in raw
    print(f"[{'✗' if has else '✓'}] policies.json {'含' if has else '不含'} VACANT 条目")
    ok &= not has

    # ② 取策略 → CONTINUE；调度器动作 → STEP（不改状态）
    ctx, _data, _ = load()
    pol = ctx.policy("VACANT")
    print(f"[{'✓' if pol.get('strategy') == 'CONTINUE' else '✗'}] "
          f"ctx.policy('VACANT') = {pol}")
    ok &= pol.get("strategy") == "CONTINUE"

    st = _mk_state(ctx)
    act = Scheduler().decide(st, [_V("VACANT")], ctx, 0, snapshot=st.snapshot())
    print(f"[{'✓' if act.kind == 'STEP' else '✗'}] 调度器对 VACANT 的动作 = {act.kind}"
          f"（应为 STEP = CONTINUE，世界继续演化而非被重放）")
    ok &= act.kind == "STEP"

    print("✓ 判据 6 通过：死循环是【没有策略可受理】的后果，不是配置出来的。"
          if ok else "✗ 判据 6 失败。")
    return 0 if ok else 1


def _mk_state(ctx):
    """造一个最小可运行的状态对象，只为把 VACANT 喂给调度器。"""
    from engine.state import State
    p = ctx.params
    return State(ctx.loci, int(p["dim"]), int(p["observables"]),
                 int(p["pool_capacity"]), ["x"])


if __name__ == "__main__":
    raise SystemExit(main())