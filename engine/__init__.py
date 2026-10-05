"""δ-me13 离散演算引擎（通用内核）。

本包内的源码不应出现任何专有名词（见 tools/grep_forbidden.py）。
它只知道：位、寄存器、个体、算子、外部扰动。
"""
import sys as _sys

# 控制台输出统一按 UTF-8。本项目的报告 / 编年史 / 工具输出全是中文（连分隔线都是「─」），
# 而**英文 Windows 的默认 stdout 编码是 cp1252** —— 打印中文会 `UnicodeEncodeError` 直接崩
# （实测：GitHub 的 `windows-latest` runner 就是这么红掉的；zh-CN 机器是 cp936，能编码中文，
# 故本地不显）。`engine` 是每个入口（`run.py` 与各 `tools/`）都会最先导入的地方，故兜底放这里。
# stdio 不是文本流（如被测试捕获）时静默跳过。
for _stream in (_sys.stdout, _sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError):
        pass