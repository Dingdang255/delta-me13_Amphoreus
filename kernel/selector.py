"""谓词选择器。

扰动不能点名某个位、某个个体——只能给一个【谓词】，让它对集合求值。
"""
from __future__ import annotations


class Selector:
    """对一个候选集合求值，返回被选中的子集。程序不认位置、不认名字。"""

    def __init__(self, expr: str):
        self.expr = expr

    def eval(self, candidates, state, ctx):
        if not candidates:
            return []
        if self.expr.startswith("order:"):        # 按位次的【数值】选，仍不看名字
            want = int(self.expr.split(":", 1)[1])
            return [i for i in candidates if state.loci[i].order == want]
        fn = _EXPRS.get(self.expr)
        if fn is None:
            raise KeyError(f"未知的选择器表达式: {self.expr}")
        return fn(candidates, state, ctx)


# 每个表达式都是通用的：它只看数值，不看 id / 名字。
_EXPRS = {
    "all":      lambda c, st, ctx: list(c),
    "any":      lambda c, st, ctx: [c[0]],
    "min_progress": lambda c, st, ctx: [min(c, key=lambda i: st.loci[i].progress)],
    "max_progress": lambda c, st, ctx: [max(c, key=lambda i: st.loci[i].progress)],
    "min_slot_value": lambda c, st, ctx: [
        min(c, key=lambda i: (st.register.slots[i].value, st.loci[i].order))
    ],
    "unowned_and_newest": lambda c, st, ctx: [
        max([i for i in c if not st.register.slots[i].filled()] or c,
            key=lambda i: st.loci[i].order)
    ],
    "unowned_and_oldest": lambda c, st, ctx: [
        min([i for i in c if not st.register.slots[i].filled()] or c,
            key=lambda i: st.loci[i].order)
    ],
    "lowest_load": lambda c, st, ctx: [min(c, key=lambda i: st.loci[i].load)],
    "highest_load": lambda c, st, ctx: [max(c, key=lambda i: st.loci[i].load)],
}


def known(expr: str) -> bool:
    """这个表达式引擎认不认识（含 `order:<n>` 形式）。给配置校验用。"""
    if not isinstance(expr, str) or not expr:
        return False
    if expr.startswith("order:"):
        try:
            int(expr.split(":", 1)[1])
            return True
        except ValueError:
            return False
    return expr in _EXPRS