"""断言核对。

剧情在这里，但它是【断言】，不是输入。
跑不出来 = 引擎错了，而不是回来改数据。

断言的种类集中在下面这张表里：它既是求值入口，也是**权威名单** ——
配置校验（engine/loader.py）拿它核对预设里写的断言名，于是「名字写错、
永远记 FAIL」这类事在启动时就会报出来，而不是等到报告里看见一行怪东西。
"""
from __future__ import annotations


class Result:
    __slots__ = ("name", "ok", "expect", "got", "where")

    def __init__(self, name, ok, expect, got, where=None):
        self.name = name
        self.ok = ok
        self.expect = expect
        self.got = got
        self.where = where or {}

    def __repr__(self):
        mark = "PASS" if self.ok else "FAIL"
        return f"[{mark}] {self.name}  expect={self.expect!r} got={self.got!r}"


class _Env:
    """断言求值的只读上下文。一条 lambda 只吃它，避免每条都闭包一堆局部量。"""

    __slots__ = ("where", "st", "traj", "ctx", "personas")

    def __init__(self, where, st, traj, ctx):
        self.where = where
        self.st = st
        self.traj = traj
        self.ctx = ctx
        self.personas = traj.personas


_KINDS = {
    "domains_exhausted":    lambda e: bool(e.st.domains_exhausted),
    "black_tide_ever":      lambda e: e.traj.violation_counts["OVERFLOW"] > 0,
    "vacancy_ever":         lambda e: e.traj.violation_counts["VACANT"] > 0,
    "promotion_count":      lambda e: int(e.st.promotions),
    "persona_count":        lambda e: len(e.personas),
    "persona_with_capability": lambda e: any(
        e.where.get("capability") in p.capabilities for p in e.personas),
    "persona_named":        lambda e: all(
        bool(e.traj.namer.persona_name(p)[0]) for p in e.personas),
    "deadlock_ever":        lambda e: bool(e.traj.deadlock),
    "deadlock_length":      lambda e: int(sum(x - s for _, s, x in e.traj.spans)),
    "converged":            lambda e: bool(e.traj.converged),
    "verdict":              lambda e: e.traj.verdict,
    "stop_reason":          lambda e: e.traj.stop_reason,
    "verdict_frame":        lambda e: e.traj.verdict_frame,
    "conclusion":           lambda e: e.traj.conclusion["id"],
    "solver_changed":       lambda e: bool(e.st.solver != "OP_SOLVE_ENTROPY"),
    "population_final":     lambda e: len(e.st.pool),
    "destruction_ever":     lambda e: any(
        c == "destruction" for _f, c in e.traj.conclusion_trail),
    "conclusion_reached":   lambda e: bool(e.traj.conclusion_trail),
    "ascended":             lambda e: bool(e.traj.ascended),
    "protocol_rewritten":   lambda e: any(
        k == "PROTOCOL_REWRITTEN" for _f, k, _p in e.traj.records),
    "promotion_mode":       lambda e: e.st.overrides.get("promotion.mode",
                                                         "in_place_upgrade"),
    "memory_repaired":      lambda e: int(e.st.score.get("memory_repaired", 0.0)),
    "destruction_events":   lambda e: int(e.st.destruction_events),
    "emitted_events":       lambda e: ",".join(sorted(
        k[len("emitted_"):] for k in e.st.score if k.startswith("emitted_"))),
}

#: 引擎认得的所有断言名（不含 `_at_least` / `_at_most` 后缀）。
KINDS = frozenset(_KINDS)

#: 断言名允许的比较后缀 → 比较方式。
SUFFIX_OPS = (("_at_least", "ge"), ("_at_most", "le"))


def split_kind(kind: str):
    """`xx_at_least` → ("xx", "ge")；`xx` → ("xx", "eq")。"""
    for suffix, op in SUFFIX_OPS:
        if kind.endswith(suffix):
            return kind[: -len(suffix)], op
    return kind, "eq"


def known(kind: str) -> bool:
    """这个名字引擎认不认识（校验配置用）。"""
    return split_kind(str(kind))[0] in _KINDS


def _value(kind, where, st, traj, ctx):
    fn = _KINDS.get(kind)
    if fn is None:
        raise KeyError(kind)          # 调用方会把它记成「未实现的断言类型」
    return fn(_Env(where, st, traj, ctx))


class AssertionRunner:
    def __init__(self, ctx, data):
        self.ctx = ctx
        self.data = data

    def run(self, traj):
        out = []
        for a in self.data.assertions:
            kind = str(a["assert"])
            base, op = split_kind(kind)
            where = a.get("where") or {}
            try:
                got = _value(base, where, traj.final, traj, self.ctx)
            except (KeyError, TypeError):
                out.append(Result(kind, False, a["expect"], "<未实现的断言类型>", where))
                continue
            exp = a["expect"]
            if op == "ge":
                ok = got >= exp
            elif op == "le":
                ok = got <= exp
            else:
                ok = got == exp
            out.append(Result(kind, bool(ok), exp, got, where))
        return out