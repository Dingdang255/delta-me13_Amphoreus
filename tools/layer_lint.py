#!/usr/bin/env python3
"""红线 3：内核分层（跨包版）。

自 §3.1 起，分层不再是"同一目录里打标签"，而是**两个物理包**：

    kernel/   纯逻辑内核：位 / 变量域 / 个体 / 算子 / 帧 / 外生扰动 / 账本。
    apps/     用户态：系统服务（向世界提问）+ 界面（只读渲染）。

依赖方向只有一条：**apps → kernel**。内核里出现一行 `from apps…` 即越界
（反向不算 —— 界面本来就要问服务要读数，应用内部不设墙）。

    python3 tools/layer_lint.py        # 出现【基线之外】的新越界 → 退出码 1

口径：
  · 两张模块表写在本文件里 —— 规则和数据放在一起，评审时对照方便。
  · 表同时是【登记簿】：`kernel/` 或 `apps/` 里冒出一个没登记的 `.py` 也要报出来。
    内核的"少而稳"是硬指标（§2：接口 ≤ 8、模块一个萝卜一个坑），
    新模块必须先在这里登记 —— 逼一次显式决定，而不是让它悄悄长出来。
  · 基线是【棘轮】：只许减，不许增。清掉一条，就从 BASELINE 里删一条。
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 打印中文前把 stdio 钉成 UTF-8（英文 Windows 默认 cp1252，打印会 UnicodeEncodeError）。
# 与 kernel/__init__.py 的同一处兜底一致；本脚本刻意不 import kernel，故自带一份。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError):
        pass


# ---- 登记簿 -----------------------------------------------------------------
# 内核：只认 位 / 变量域 / 个体 / 算子 / 帧 / 外生扰动 / 账本。零专名、不下结论。
# `api.py` 是那道【系统调用门】：8 个调用、带 `v1` 版本号，只做"把一次运行包成
# 可寻址的会话"，语义一个比特都不加（见 docs/adr/0001）。
KERNEL = ["api.py", "core.py", "disturbance.py", "emergence.py", "loader.py",
          "operators.py", "scheduler.py", "selector.py", "state.py",
          "vocabulary.py"]
# 用户态：服务（裁决 / 消融 / 断言 / 不变量 / 特征 / 时间线 / 条件 / 服务束）
#         + 界面（命名 / 渲染 / 看板 / 可视化）
#         + 应用模型（`script.py`：声明式订阅与响应，§D2）
#         + 只读叙事层（`terminal.py` 按帧回放预设的系统消息 / `archive.py` 渲染档案 /
#           `terminal_bridge.py` 与 `terminal_window.py` 负责独立 CLI 窗口的 socket 通道）。
#         + 只读语料层（`canon.py`：读 `lore/canon/` 的编译产物，只认 id 与种类）。
APPS = ["ablation.py", "archive.py", "assertions.py", "canon.py", "conditions.py",
        "features.py",
        "invariants.py", "live.py", "namer.py", "origin.py", "origin_loop.py",
        "render.py", "script.py",
        "services.py", "terminal.py", "terminal_bridge.py", "terminal_window.py",
        "timeline.py", "verdicts.py", "viz.py"]

PACKAGES = {"kernel": KERNEL, "apps": APPS}

# ---- 已存在的越界：棘轮，只许减不许增 ----------------------------------------
# 2026-10-05 首次扫描得 6 条；P1 清掉 emergence→namer；P4-0 把名字注册表下沉为内核侧的
# vocabulary.py，清掉 loader 的 2 条；P4-S1/S2/S3 把不变量 / 消融 / 裁决倒置成
# runtime.checks / .probe / .judge，各清 1 条 ⇒ 归零。
# 2026-10-07 §3.1 把这条防线从"同目录标签"升级为"跨包方向检查"，仍是 0。
BASELINE = set()

_APP_IMPORT = re.compile(
    r"^\s*(?:from\s+apps(?:\.\w+)?\s+import\b|import\s+apps(?:\.\w+)?\s*(?:$|,))")
_REL_IMPORT = re.compile(r"^\s*from\s+\.(\w+)\s+import\b")


def _modules(d):
    return sorted(n for n in os.listdir(d) if n.endswith(".py"))


def _lines(path):
    with open(path, "r", encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            yield ln, line.split("#", 1)[0]


def violations(root: str):
    """返回 [(来源, 目标, 说明), …]。空列表 = 分层干净。"""
    out = []
    for pkg, registered in PACKAGES.items():
        d = os.path.join(root, pkg)
        present = _modules(d)
        for name in present:
            if name != "__init__.py" and name not in registered:
                out.append((f"{pkg}/{name}", "—",
                            f"没在 layer_lint 的登记簿里：{pkg}/ 的模块要一个一个登记"))
        if pkg != "kernel":
            continue
        # 内核不许往上依赖：任何 `from apps…` / `import apps…` 都是越界。
        for name in present:
            for ln, code in _lines(os.path.join(d, name)):
                if _APP_IMPORT.match(code):
                    out.append((f"kernel/{name}:L{ln}", "apps",
                                "内核只许往下依赖自己（apps → kernel 是唯一方向）"))
                m = _REL_IMPORT.match(code)
                if m and m.group(1) + ".py" not in present:
                    out.append((f"kernel/{name}:L{ln}", m.group(1) + ".py",
                                "内核引用了内核里不存在的同包模块"
                                "（服务层的东西已经搬到 apps/ 了）"))
    return out


def main():
    found = violations(ROOT)
    known = [v for v in found if (v[0], v[1]) in BASELINE]
    fresh = [v for v in found if (v[0], v[1]) not in BASELINE]
    alive = {(v[0], v[1]) for v in found}
    stale = sorted(BASELINE - alive)

    print(f"【内核分层】kernel/ {len(KERNEL)} 个模块 · apps/ {len(APPS)} 个模块"
          f"（依赖方向：apps → kernel，单向）")
    print()

    if known:
        print("台账（已登记、待清；棘轮只许减不许增）：")
        for src, tgt, why in known:
            print(f"  · {src} → {tgt}　（{why}）")
        print()
    if stale:
        print("⚠ 基线里这几条已经不存在了，请从 BASELINE 删掉：")
        for src, tgt in stale:
            print(f"  · {src} → {tgt}")
        print()

    if fresh:
        print("✗ 出现【基线之外】的新越界：")
        for src, tgt, why in fresh:
            print(f"  ✗ {src} → {tgt}　（{why}）")
        return 1

    if stale:
        print("✗ 基线需要维护（见上）。")
        return 1

    print(f"✓ 分层 lint 通过：没有新增越界（基线内 {len(known)} 条待清）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())