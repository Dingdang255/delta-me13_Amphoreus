"""δ-me13 离散演算引擎 —— 纯逻辑内核。

本包内的源码不应出现任何专有名词（见 tools/grep_forbidden.py）。
它只知道：位、寄存器、个体、算子、外部扰动，以及一个账本。
它**不下结论、不认识名字、不认识"裁决 / 断言 / 消融 / 渲染"** ——
那些东西住在 `apps/`，内核一行 import 都不往那边去（见 tools/layer_lint.py）。

对外的**系统调用冻结为 8 个，带版本号 `v1`**（见 kernel/api.py 与 docs/adr/）：

    load(machine_spec) -> Session      用机器规格建一个世界
    Session.step(n) -> FrameReport     推进 n 帧
    Session.snapshot() / restore(h)    存档 / 读档
    Session.inject(disturbance)        投递外生扰动（唯一能打破闭环的入口）
    Session.observe() -> Metrics       只读指标快照
    Session.events() -> EventStream    事件流（一切对外可见之物都只能走这里）
    Session.capabilities() -> dict     声明可用算子 / 权限
    version() -> str                   内核接口版本

内核的主体仍是 `core`（主循环 / 状态 / 算子装配）与 `loader`（读 config 与
presets）；`api` 只是把一次运行包成可寻址的会话，语义一个比特都不加。
"""
import sys as _sys

# 控制台输出统一按 UTF-8。本项目的报告 / 编年史 / 工具输出全是中文（连分隔线都是「─」），
# 而**英文 Windows 的默认 stdout 编码是 cp1252** —— 打印中文会 `UnicodeEncodeError` 直接崩
# （实测：GitHub 的 `windows-latest` runner 就是这么红掉的；zh-CN 机器是 cp936，能编码中文，
# 故本地不显）。`kernel` 是每个入口（`run.py` 与各 `tools/`）都会最先导入的地方，故兜底放这里。
# stdio 不是文本流（如被测试捕获）时静默跳过。
for _stream in (_sys.stdout, _sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError):
        pass

# 系统调用从这里出去。放在编码兜底【之后】—— 万一它自己的 import 链里有打印也没关系。
from .api import API_VERSION, EventStream, Session, load, version  # noqa: E402,F401