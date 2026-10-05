#!/usr/bin/env python3
"""判据 4（静态部分）：逐步推进 lint。

禁止任何"一眼看到未来 / 直接跳到不动点"的写法：
    state[n+k]、traj.final 读取、events.peek()、solve_fixed_point()、matrix_power()、lookahead …

    python3 tools/stepwise_lint.py        # 命中则退出码 1
"""
from __future__ import annotations

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BANNED = [
    (r"\bmatrix_power\b", "矩阵幂加速：等价于解析求解"),
    (r"\bsolve_fixed_point\b", "直接求不动点"),
    (r"\bfixed_point\s*\(", "直接求不动点"),
    (r"\bpeek\s*\(", "预读未来事件"),
    (r"\blookahead\b", "预读未来"),
    (r"\bconverge_to\s*\(", "直接跳到收敛态"),
    (r"\bstate\s*\[\s*\w*\s*n\s*\+", "按帧号索引未来状态"),
    (r"\bstate\s*\[\s*n\s*\+", "按帧号索引未来状态"),
    (r"\bfuture_events\b", "预读未来事件"),
    (r"\.final_state_before\b", "预读最终态"),
]

# 这些是 L5 / 事后核对 / 只读渲染层：它们在演算【结束后】读取结果，属于合法读者。
# （viz.py 是 A2–A7 的只读看板：席位卡、曲线右端、摘要卡都要读终局 —— 与 render.py 同性质。）
POST_HOC = {"assertions.py", "render.py", "namer.py", "loader.py", "features.py",
            "viz.py"}
TRAJ_FINAL = (r"traj\.final(?!\s*=[^=])", "读取最终态作为捷径")


def rules_for(name: str):
    """该文件该套哪些规则。`POST_HOC`（L5 / 事后核对 / 只读渲染层）豁免 `traj.final`。"""
    rules = list(BANNED)
    if os.path.basename(name) not in POST_HOC:
        rules.append(TRAJ_FINAL)
    return rules


def scan_file(path: str):
    """扫一个文件，返回 [(行号, 规则, 说明, 原行), …]。只看代码、忽略注释。

    口径与 `grep_forbidden.scan_file` 同形，便于单测直接调它（`tests/test_stepwise_lint.py`）。
    """
    hits = []
    with open(path, "r", encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            code = line.split("#", 1)[0]          # 只看代码，忽略注释
            for pat, why in rules_for(path):
                if re.search(pat, code):
                    hits.append((ln, pat, why, line.rstrip("\n")))
    return hits


def main():
    engine = os.path.join(ROOT, "engine")
    total = 0
    for name in sorted(os.listdir(engine)):
        if not name.endswith(".py"):
            continue
        for ln, pat, why, line in scan_file(os.path.join(engine, name)):
            print(f"✗ engine/{name}:L{ln}  «{pat}»  → {why}")
            print(f"      {line.strip()[:72]}")
            total += 1
    if total == 0:
        print("✓ engine/ 逐步推进 lint 通过：没有解析求解 / 预读未来")
        return 0
    print(f"\n命中 {total} 处：引擎出现了非逐步的写法。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())