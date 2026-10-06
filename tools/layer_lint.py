#!/usr/bin/env python3
"""红线 3：内核分层。

内核（kernel）只做演化与记账 —— 它认识的东西只有：
位 / 变量域 / 个体 / 算子 / 帧 / 外生扰动 / 账本。
**内核不许 import 服务层（service）或界面层（presentation）**：
一旦内核认识"命名 / 渲染 / 裁决 / 断言"，它就不再是那台"只认因子"的机器了。

    python3 tools/layer_lint.py        # 出现【基线之外】的新越界 → 退出码 1

口径：
  · 层次表与"已存在的越界"基线都写在本文件里 —— 规则和数据放在一起，评审时对照方便。
  · 基线是【棘轮】：**只许减，不许增**。清掉一条，就从 BASELINE 里删一条。
  · 基线里已经消失的条目会被报出来，提醒你顺手删掉。

已知局限：本工具按"行首是 from .x import"的形态识别内部依赖，
若某天有文档字符串里出现同样开头的句子，会被误判 —— 届时按基线机制处理即可。
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 打印中文前把 stdio 钉成 UTF-8（英文 Windows 默认 cp1252，打印会 UnicodeEncodeError）。
# 与 engine/__init__.py 的同一处兜底一致；本脚本刻意不 import engine，故自带一份。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError):
        pass


# ---- 分层 -------------------------------------------------------------------
# 内核：只认 位 / 变量域 / 个体 / 算子 / 帧 / 外生扰动 / 账本。零专名、不下结论。
KERNEL = ["core.py", "disturbance.py", "emergence.py", "loader.py",
          "operators.py", "scheduler.py", "selector.py", "state.py",
          "vocabulary.py"]
# 服务：有人在"向世界提问"（裁决 / 消融 / 断言 / 不变量 / 特征 / 时间线核对）。
SERVICE = ["ablation.py", "assertions.py", "conditions.py", "features.py",
           "invariants.py", "services.py", "timeline.py", "verdicts.py"]
# 界面：命名 / 渲染 / 看板。只读，不参与演算。
PRESENTATION = ["live.py", "namer.py", "render.py", "viz.py"]

LAYERS = {"kernel": KERNEL, "service": SERVICE, "presentation": PRESENTATION}
ORDER = {"kernel": 0, "service": 1, "presentation": 2}

# ---- 已存在的越界：P0 冻结基线（棘轮，只许减不许增）---------------------------
# 2026-10-05 首次扫描得 6 条；P1 清掉 emergence→namer；P4-0 把名字注册表下沉为内核侧的
# vocabulary.py，清掉 loader 的 2 条；P4-S1 把不变量检查倒置成 runtime.checks，清掉 1 条。
# 剩下 2 条要等 S2（消融探针）/ S3（裁决）倒置。
BASELINE = {
    ("core.py", "ablation.py"),
    ("core.py", "verdicts.py"),
}

_FROM_MOD = re.compile(r"^\s*from\s+\.(\w+)\s+import\b")
_FROM_PKG = re.compile(r"^\s*from\s+\.\s+import\s+(.+)$")


def layer_of(filename: str):
    for layer, names in LAYERS.items():
        if filename in names:
            return layer
    return None


def imported_modules(path: str):
    """该文件 import 了哪些【同包模块】（只认 `from .x import y` / `from . import a, b`）。"""
    mods = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            code = line.split("#", 1)[0]
            m = _FROM_MOD.match(code)
            if m:
                mods.append(m.group(1))
                continue
            m = _FROM_PKG.match(code)
            if m:
                for part in m.group(1).split(","):
                    name = part.strip().split(" as ")[0].strip()
                    if name.isidentifier():
                        mods.append(name)
    return mods


def violations(engine_dir: str):
    """返回 [(来源文件, 目标文件, 来源层, 目标层), …] —— 只列"往下依赖"的那些。"""
    out = []
    for name in sorted(os.listdir(engine_dir)):
        if not name.endswith(".py"):
            continue
        src = layer_of(name)
        if src is None:                       # __init__.py 之类不参与
            continue
        for mod in imported_modules(os.path.join(engine_dir, name)):
            tgt = mod + ".py"
            dst = layer_of(tgt)
            if dst is None or dst == src:
                continue
            if ORDER[dst] > ORDER[src]:
                out.append((name, tgt, src, dst))
    return out


def main():
    engine = os.path.join(ROOT, "engine")
    found = violations(engine)
    known = [v for v in found if (v[0], v[1]) in BASELINE]
    fresh = [v for v in found if (v[0], v[1]) not in BASELINE]
    alive = {(v[0], v[1]) for v in found}
    stale = sorted(BASELINE - alive)

    print(f"【内核分层】engine/ 共 {sum(len(v) for v in LAYERS.values())} 个模块："
          f"内核 {len(KERNEL)} · 服务 {len(SERVICE)} · 界面 {len(PRESENTATION)}")
    print()

    if known:
        print("台账（已登记、待清；棘轮只许减不许增）：")
        for src, tgt, sl, dl in known:
            print(f"  · {src} → {tgt}　（{sl} → {dl}）")
        print()
    if stale:
        print("⚠ 基线里这几条已经不存在了，请从 BASELINE 删掉：")
        for src, tgt in stale:
            print(f"  · {src} → {tgt}")
        print()

    if fresh:
        print("✗ 出现【基线之外】的新越界：内核只许往下依赖自己。")
        for src, tgt, sl, dl in fresh:
            print(f"  ✗ engine/{src} → engine/{tgt}　（{sl} → {dl}）")
        return 1

    if stale:
        print("✗ 基线需要维护（见上）。")
        return 1

    print(f"✓ engine/ 分层 lint 通过：没有新增越界（基线内 {len(known)} 条待清）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
