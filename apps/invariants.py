"""L3：四类通用检查器。

每个 predicate 返回【全部违例】而不是 bool —— 全称量化被写进了类型里。
程序不知道缺的是哪一个位。
"""
from __future__ import annotations


class Violation:
    __slots__ = ("code", "locus_index", "magnitude", "frame")

    def __init__(self, code, locus_index, magnitude, frame):
        self.code = code
        self.locus_index = locus_index
        self.magnitude = float(magnitude)
        self.frame = int(frame)

    def __repr__(self):
        return f"<{self.code} @{self.locus_index} mag={self.magnitude:.3f}>"


class Invariant:
    name = "IV"

    def predicate(self, st, ctx, frame):    # pragma: no cover - 抽象
        raise NotImplementedError


class IntegrityCheck(Invariant):
    """∀ locus ∈ Loci : slot(l).filled()"""

    name = "IntegrityCheck"

    def predicate(self, st, ctx, frame):
        return [Violation("VACANT", i, 1.0, frame) for i in st.register.vacant()]


class ProgressCheck(Invariant):
    """∀ locus ∈ Loci : progress(l) ≥ τ —— 尚未被反证法证伪即为违例。

    progress 现在是【连续】量（消融熵 / 消融阈值），故违例程度 tau - progress
    真的量得出「还差多少」，而不是只有 0 / τ 两档。
    """

    name = "ProgressCheck"

    def predicate(self, st, ctx, frame):
        tau = ctx.params["tau_falsify"]
        return [
            Violation("UNSOLVED", i, tau - l.progress, frame)
            for i, l in enumerate(st.loci)
            if l.progress < tau
        ]


class CapacityCheck(Invariant):
    """∀ locus : 承载【份额】≤ capacity —— 某一席吃下过多承载，即生成乱码（噪声源头）。

    口径：`share_i = load_i / Σ_j load_j`（0～1，尺度无关；十二席均分时 = 1/12 ≈ 0.083）
    对比 `capacity_i`（`config/loci.json`，现为 share 上限 0.1955～0.2530）。

    ⚠ 历史：此前它比的是 `load > capacity` 的**绝对量** —— 而 `load` 是"该位上所有个体
    的分量之和"（量级 1.7～6.5）、`capacity` 是每位的标量上限（起始 ~1 且随再创世逐代
    ×0.9 衰减到 6e-5），两者量纲不一致 ⇒ 判据**恒真**（实测 12 席 × 每帧 = 100%），
    于是 `OVERFLOW` 常驻、调度层每帧按 `EMIT_VISUAL_NOISE` 加固定噪声，`noise` 停在
    常数平衡点 0.7083（= 0.085 / (1 − 0.88)）。那让噪声成为一个**恒压**，`CapacityCheck`
    与 `OVERFLOW` 都失去区分度。现改为份额口径 ⇒ 它**只在某席真的失衡时才触发**（实测约
    1% 的帧），`noise` 随之成为**会涨落、且能越过 `tau_noise_parley` 的真信号**。
    """

    name = "CapacityCheck"

    def predicate(self, st, ctx, frame):
        total = sum(l.load for l in st.loci)
        if total <= 0.0:
            return []
        return [
            Violation("OVERFLOW", i, l.load / total - l.capacity, frame)
            for i, l in enumerate(st.loci)
            if l.load / total > l.capacity
        ]


class ConservationCheck(Invariant):
    """∀ locus ∈ Loci : 承载量守恒 —— 有量却无人承载即为异常。"""

    name = "ConservationCheck"

    def predicate(self, st, ctx, frame):
        return [
            Violation("UNCONSERVED", i, slot.value, frame)
            for i, slot in enumerate(st.register.slots)
            if slot.value > 1e-6 and slot.owner is None
        ]


INVARIANTS = {
    "IntegrityCheck": IntegrityCheck,
    "ProgressCheck": ProgressCheck,
    "CapacityCheck": CapacityCheck,
    "ConservationCheck": ConservationCheck,
}


def collect(names, st, ctx, frame):
    out = []
    for n in names:
        out.extend(INVARIANTS[n]().predicate(st, ctx, frame))
    return out