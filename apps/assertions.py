"""断言核对。

剧情在这里，但它是【断言】，不是输入。
跑不出来 = 引擎错了，而不是回来改数据。

断言的种类集中在下面这张表里：它既是求值入口，也是**权威名单** ——
配置校验（kernel/loader.py）拿它核对预设里写的断言名，于是「名字写错、
永远记 FAIL」这类事在启动时就会报出来，而不是等到报告里看见一行怪东西。
"""
from __future__ import annotations

from kernel.vocabulary import (ASSERTION_KINDS, SUFFIX_OPS,  # noqa: F401
                               know_assertion, split_kind)


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
    "skipped_frames":       lambda e: int(e.traj.skipped_frames),
    "iterations":           lambda e: int(e.traj.iterations),
    "emitted_events":       lambda e: ",".join(sorted(
        k[len("emitted_"):] for k in e.st.score if k.startswith("emitted_"))),
    # —— 原初（第十三席）的真实读数 ——（全部只读；canonical 世界恒为未成形）
    "origin_ever":          lambda e: bool(getattr(e.st.origin, "ever", False)),
    "origin_selfhood":      lambda e: float(getattr(e.st.origin, "selfhood", 0.0)),
    "origin_closure":       lambda e: int(getattr(e.st.origin, "closure", 0)),
    "origin_borrowed":      lambda e: int(getattr(e.st.origin, "borrowed", 0)),
    "origin_repaid":        lambda e: int(getattr(e.st.origin, "repaid", 0)),
    "origin_occupant":      lambda e: next(
        (s.owner for s in e.st.register.slots if getattr(s, "meta", False)), None),
    "origin_anchors":       lambda e: int(
        (getattr(e.traj, "origin", None) or {}).get(
            "anchors", getattr(e.st.origin, "borrowed", 0))),
    "origin_missing":       lambda e: int(
        (getattr(e.traj, "origin", None) or {}).get("missing", 0)),
    "origin_awake":         lambda e: bool(getattr(e.st.origin, "awake", False)),
    "origin_create":        lambda e: int(e.st.score.get("origin_create", 0.0)),
    "origin_love":          lambda e: int(e.st.score.get("origin_love", 0.0)),
    "origin_trailblaze":    lambda e: int(e.st.score.get("origin_trailblaze", 0.0)),
    "origin_dissolved":     lambda e: int(e.st.score.get("origin_dissolved", 0.0)),
    "origin_form":          lambda e: int(getattr(e.st.origin, "form", 0)),
    "origin_coverage":      lambda e: float(getattr(e.st.origin, "coverage", 0.0)),
    "origin_factor_rows":   lambda e: int(getattr(e.st.origin, "factor_rows", 0)),
    # —— 大墓账本 / 两次回望 ——（canonical 世界恒为 0）
    "origin_tomb_cycles":   lambda e: int(getattr(e.st.origin, "tomb_cycles", 0)),
    "origin_tomb_rows":     lambda e: int(getattr(e.st.origin, "tomb_rows", 0)),
    "origin_tomb_volume":   lambda e: float(getattr(e.st.origin, "tomb_volume", 0.0)),
    "origin_memory_reserve": lambda e: float(
        getattr(e.st.origin, "memory_reserve", 0.0)),
    "origin_cause_closed":  lambda e: int(
        getattr(e.st.origin, "cause_closed", False)),
    "origin_philia_successor": lambda e: int(
        getattr(e.st.origin, "philia_successor", -1)),
    "origin_philia_generation": lambda e: int(
        getattr(e.st.origin, "philia_generation", 0)),
    "origin_final_form":    lambda e: int(e.st.score.get("origin_final_form", 0.0)),
    "origin_dream":         lambda e: int(e.st.score.get("origin_dream", 0.0)),
    "origin_oracle":        lambda e: int(e.st.score.get("origin_oracle", 0.0)),
    "origin_skill":         lambda e: int(e.st.score.get("origin_skill", 0.0)),
    "origin_sos":           lambda e: int(e.st.score.get("origin_sos", 0.0)),
    "origin_sword":         lambda e: int(e.st.score.get("origin_sword", 0.0)),
    "origin_self_split":    lambda e: int(e.st.score.get("origin_self_split", 0.0)),
    "origin_companion":     lambda e: int(e.st.score.get("origin_companion", 0.0)),
    "origin_companion_alive": lambda e: bool(
        int(getattr(e.st.origin, "companion_serial", -1)) >= 0
        and e.st.pool.index_of_serial(
            int(getattr(e.st.origin, "companion_serial", -1))) >= 0),
    "origin_companion_serial": lambda e: int(
        getattr(e.st.origin, "companion_serial", -1)),
    "origin_companion_spawn": lambda e: int(
        e.st.score.get("origin_companion_spawn", 0.0)),
    "origin_companion_host": lambda e: int(
        getattr(e.st.origin, "companion_host", -1)),
    "origin_companion_stage": lambda e: int(
        getattr(e.st.origin, "companion_stage", 0)),
    "origin_companion_age": lambda e: int(
        getattr(e.st.origin, "companion_age", 0)),
    "origin_companion_carry": lambda e: int(
        getattr(e.st.origin, "companion_carry", 0)),
    "origin_companion_bond": lambda e: int(
        getattr(e.st.origin, "companion_bond", 0)),
    "origin_companion_grow": lambda e: int(
        e.st.score.get("origin_companion_grow", 0.0)),
    "origin_companion_rebind": lambda e: int(
        e.st.score.get("origin_companion_rebind", 0.0)),
    "origin_companion_rebond": lambda e: int(
        e.st.score.get("origin_companion_rebond", 0.0)),
    "origin_companion_seat": lambda e: int(
        e.st.score.get("origin_companion_seat", 0.0)),
    "origin_companion_eminence": lambda e: int(
        "emitted_origin_companion_eminence" in e.st.score),
    "origin_attach": lambda e: int(e.st.score.get("origin_attach", 0.0)),
    "origin_memory_seats": lambda e: len(getattr(e.st, "memory_seats", ())),
    "origin_rebind": lambda e: int(e.st.score.get("origin_rebind", 0.0)),
    "origin_resonance": lambda e: int(e.st.score.get("origin_resonance", 0.0)),
    "origin_resonance_value": lambda e: float(
        getattr(e.st.origin, "resonance", 0.0)),
    "origin_resonance_host": lambda e: int(
        getattr(e.st.origin, "resonance_host", -1)),
    "origin_resonance_wake": lambda e: int(
        e.st.score.get("origin_resonance_wake", 0.0)),
    "origin_savior": lambda e: int(e.st.score.get("origin_savior", 0.0)),
    "origin_savior_active": lambda e: bool(
        getattr(e.st.origin, "savior_active", False)),
    "origin_savior_transfer": lambda e: int(
        e.st.score.get("origin_savior_transfer", 0.0)),
    "origin_memory_fragment": lambda e: int(
        e.st.score.get("origin_memory_fragment", 0.0)),
    "origin_memory_transfer": lambda e: int(
        e.st.score.get("origin_memory_transfer", 0.0)),
    "origin_memory_coupling": lambda e: float(
        getattr(e.st.origin, "memory_coupling_gain", 0.0)),
    "origin_memory_mutation": lambda e: float(
        getattr(e.st.origin, "memory_mutation_damp", 0.0)),
    "origin_memory_tick": lambda e: int(
        e.st.score.get("origin_memory_tick", 0.0)),
    "origin_memory_phase": lambda e: int(
        e.st.score.get("origin_memory_phase", 0.0)),
    "origin_gazed": lambda e: int("emitted_origin_gazed" in e.st.score),
    "origin_seat_seized": lambda e: int("emitted_seat_seized" in e.st.score),
    "origin_seat_reclaimed": lambda e: int(
        "emitted_origin_seat_reclaimed" in e.st.score),
    # —— 权柄层：命途 ——（canonical 世界恒为空）
    "path_joined": lambda e: int(e.st.score.get("path_joined", 0.0)),
    "path_defected": lambda e: int(e.st.score.get("path_defected", 0.0)),
    "path_members": lambda e: len(getattr(e.st, "paths", {})),
    "path_emanators": lambda e: len(getattr(e.st, "grants", {})),
    "path_revoked": lambda e: int(e.st.score.get("path_revoked", 0.0)),
    "path_authorities": lambda e: len(getattr(e.st, "authorities", {})),
    "path_affinity": lambda e: max(
        (float(v.get("affinity", 0.0)) for v in getattr(e.st, "paths", {}).values()),
        default=0.0),
    # —— 剧情接线的读数：全部读真实状态（事件标签不算证明） ——
    "memory_rows": lambda e: int(getattr(e.st, "memory_bank").shape[0]),
    "suppressed_slots": lambda e: len(getattr(e.st, "suppressed", ())),
    "embers_taken": lambda e: int(e.st.score.get("embers_taken", 0.0)),
    "external_seats": lambda e: sum(
        1 for s in e.st.register.slots
        if s.owner is not None and int(s.owner) < 0 and int(s.owner) != -1),
    "override_rules": lambda e: ",".join(sorted(getattr(e.st, "overrides", {}))),
    # —— 真实回退（世界退回本轮起点） ——
    "origin_rewinds": lambda e: int(getattr(e.traj, "rewinds", 0)),
    "origin_rollbacks": lambda e: int(e.st.score.get("rollbacks", 0.0)),
    # —— 具名因子（候选必须已经在池里） ——
    "factor_named": lambda e: int(e.st.score.get("factor_named", 0.0)),
    # —— 因子的决策 / 权杖入口 ——
    "factor_certainty": lambda e: max(
        (float(v.get("certainty", 0.0))
         for v in getattr(e.st, "factor_ledger", {}).values()), default=0.0),
    "factor_decided": lambda e: int(e.st.score.get("factor_decided", 0.0)),
    "years_loophole": lambda e: int(e.st.score.get("years_loophole", 0.0)),
    "entry_locked": lambda e: int(bool(getattr(e.st, "entry_locked", False))),
    "entry_unlocked": lambda e: int("entry_unlocked" in e.st.score),
    "final_recreation": lambda e: int(e.st.score.get("final_recreation", 0.0)),
    "fuli_anchor_past": lambda e: int(e.st.score.get("fuli_anchor_past", 0.0)),
}

#: 引擎认得的所有断言名（不含 `_at_least` / `_at_most` 后缀）。
#: 名字表的【唯一来源】在内核侧的 `kernel/vocabulary.py`。
KINDS = frozenset(_KINDS)

# 核对：实现与内核侧登记的名字必须一一对应（加了实现忘了登记名字会当场报错）。
assert KINDS == ASSERTION_KINDS, "断言的实现与 vocabulary.ASSERTION_KINDS 不一致"


def known(kind: str) -> bool:
    """这个名字引擎认不认识（校验配置用）。"""
    return know_assertion(kind)


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