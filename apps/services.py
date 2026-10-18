"""应用层交给内核的【服务实现束】—— 内核启动时拿到的那张"驱动表"。

与 `namer`（不透明句柄）/ `rules`（不透明谓词）同一手法：内核**不 import、不解释**
这些实现，只按名调用。存在的意义是让内核不必 import 服务层（见 `tools/layer_lint.py`）。

**为什么必须显式交过来**：这几样（不变量检查 / 消融探针 / 裁决）不是"可选的增强"，
而是内核控制流的一部分 —— 缺了它们不是"行为略不同"，而是**跑不了**。
所以 `run()` 拿不到 `runtime=` 时会当场报错，而不是退回某个默认。

字段随"控制流倒置"的进度逐步补齐（见《P4-控制流倒置设计稿》）：

    checks        不变量检查  (st, ctx, frame) -> [Violation]   ← 调度器要读它的返回值
    probe         消融探针    (st, ctx, seed, gates, params) -> None   ← 只写 locus.progress*
    judge         裁决        (st, ctx, stalled) -> (裁决名|None, 是否升格)
    inner_verdict 兜底裁决    (st, ctx, stalled) -> (裁决名|None, 是否升格)

`judge` 与 `inner_verdict` 的分工同 `verdicts.evaluate` / `verdicts.inner_conclusion`：
前者套用外生改写（主循环每帧问），后者不套（预算耗尽的兜底问）。
"""
from __future__ import annotations


class Services:
    """内核认得的服务实现束。字段名就是内核对它们的全部认知。"""

    __slots__ = ("checks", "probe", "judge", "inner_verdict")

    def __init__(self, checks, probe, judge, inner_verdict):
        self.checks = checks
        self.probe = probe
        self.judge = judge
        self.inner_verdict = inner_verdict


def default():
    """本仓内置的那一套。**应用层/工具/测试都用它**，内核只按名调用。

    注意 `checks` 是"按运行时配置取检查名单"的：名单来自 `ctx.params`（每次运行自己的
    配置），所以调用点不需要额外传配置 —— 这也是它能做成无参工厂的原因。
    """
    from .ablation import solve
    from .invariants import collect
    from .verdicts import ascends_of, evaluate, inner_conclusion

    def checks(st, ctx, frame):
        return collect(ctx.invariant_names, st, ctx, frame)

    def probe(st, ctx, seed, gates, params):
        return solve(st, ctx, seed, gates, params)

    def judge(st, ctx, stalled):
        return evaluate(st, ctx, stalled)

    def inner_verdict(st, ctx, stalled):
        name = inner_conclusion(st, ctx, stalled)
        return name, ascends_of(ctx, name)

    return Services(checks=checks, probe=probe,
                    judge=judge, inner_verdict=inner_verdict)
