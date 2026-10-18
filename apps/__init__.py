"""用户态：应用与系统服务。

内核（`kernel/`）只做演化与记账，它不认识"裁决 / 断言 / 消融 / 命名 / 渲染"。
这些东西住在这一层 —— 内核**一行 import 都不往这里来**（见 `tools/layer_lint.py`）。

分两类，都在这一个包里（层与目录不必一一对应，见 `docs/adr/0001`）：

  · **系统服务**（有人在向世界提问）：裁决 / 不变量 / 消融 / 断言 / 时间线 / 特征 / 条件。
  · **界面**（只读渲染）：命名 / 渲染 / 看板 / 可视化。

依赖方向：`apps → kernel`，只能这一个方向。`apps` 内部可以互相依赖
（服务与界面之间不设墙 —— 界面的取词本来就要问服务要读数）。
"""
import sys as _sys

# 与 kernel/__init__.py 同一处兜底：控制台统一 UTF-8（英文 Windows 的 cp1252 会崩中文）。
# 本包可能先于 kernel 被导入（如某个工具只取渲染器），故自带一份。
for _stream in (_sys.stdout, _sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError):
        pass