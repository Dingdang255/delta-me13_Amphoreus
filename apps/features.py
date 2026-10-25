"""可观测特征：把一次演算压成一个扁平的特征字典。

这里是【量出来】而不是【判出来】：不认识任何专有名词，也不下任何结论。
它只服务于两件事 —— 预设时间线的核对，以及种子检索时的要素约束。
"""
from __future__ import annotations

import hashlib

DEFAULT_COLS = ["seed", "promotion_count", "deadlock_count",
                "deadlock_total_frames", "vacancy_first_frame",
                "black_tide_first_frame", "persona_count", "converged",
                "verdict", "conclusion"]


def _first_frames(traj):
    first, vfirst = {}, {}
    for f, kind, payload in traj.records:
        first.setdefault(kind, f)
        if kind == "VIOLATION_STATE":
            for c in payload.get("codes", ()):
                vfirst.setdefault(c, f)
    return first, vfirst


def _last_frame(traj, kind):
    out = None
    for f, k, _p in traj.records:
        if k == kind:
            out = f
    return out


def extract(traj, ctx) -> dict:
    """把一次演算压成特征向量。"""
    st = traj.final
    first, vfirst = _first_frames(traj)
    spans = traj.spans
    er_total = int(sum(e - s for _k, s, e in spans))
    personas = traj.personas
    names = [traj.namer.persona_name(p) for p in personas]
    caps = sorted({c for p in personas for c in p.capabilities})
    style = traj.namer.style

    return {
        "seed": int(ctx.seed),
        # —— 进程 ——
        "iterations": traj.iterations,
        "skipped_frames": traj.skipped_frames,
        "reached_frame": traj.reached_frame,
        "round": int(st.round),
        "truncated": bool(traj.truncated),
        "final_entropy": round(float(st.entropy), 6),
        "final_noise": round(float(st.noise), 6),
        "population_final": len(st.pool),
        # —— 初始变量域 ——
        "domain_index": int(st.domain_index),
        "domains_exhausted": bool(st.domains_exhausted),
        "domain_exhausted_frame": first.get("DOMAINS_EXHAUSTED"),
        # —— 迭代（跃迁） ——
        "promotion_count": int(st.promotions),
        "promotion_first_frame": first.get("PROMOTION"),
        "promotion_last_frame": _last_frame(traj, "PROMOTION"),
        # —— 死循环（结构长期不推进） ——
        "deadlock": bool(traj.deadlock),
        "deadlock_count": len(spans),
        "deadlock_total_frames": er_total,
        "deadlock_first_frame": spans[0][1] if spans else None,
        "deadlock_longest": max((e - s for _k, s, e in spans), default=None),
        # —— 空缺 / 超载 ——
        "vacancy_ever": bool(vfirst.get("VACANT") is not None),
        "vacancy_first_frame": vfirst.get("VACANT"),
        "vacancy_frames": int(traj.violation_counts.get("VACANT", 0)),
        "black_tide_ever": bool(traj.violation_counts.get("OVERFLOW", 0) > 0),
        "black_tide_first_frame": vfirst.get("OVERFLOW"),
        "black_tide_frames": int(traj.violation_counts.get("OVERFLOW", 0)),
        # —— 改写 / 收束 ——
        "solver_changes": sum(1 for _f, k, _p in traj.records if k == "SOLVER_CHANGED"),
        "solver_final": st.solver,
        "converged": bool(traj.converged),
        "converged_frame": first.get("CONVERGED"),
        # —— 裁决 ——
        "verdict": traj.verdict,
        "verdict_frame": traj.verdict_frame,
        "stop_reason": traj.stop_reason,
        "conclusion": traj.conclusion["id"],
        "destruction_ever": any(c == "destruction" for _f, c in traj.conclusion_trail),
        "conclusion_trail_len": len(traj.conclusion_trail),
        "conclusion_seen_final": (traj.conclusion_trail[-1][1]
                                  if traj.conclusion_trail else None),
        "ascended": bool(traj.ascended),
        # —— 规则覆写 / 记忆再造 / 尝试阶段（剧情机制是否真的跑起来的硬指标） ——
        "protocol_rewritten": sum(1 for _f, k, _p in traj.records
                                  if k == "PROTOCOL_REWRITTEN"),
        "override_rules": ",".join(sorted(st.overrides)),
        "promotion_mode": st.overrides.get("promotion.mode", "in_place_upgrade"),
        # —— 外生剧情事件是否【真的投递过】——
        # emit 只往账本记一个读数（不改动力学），故这里量的是「剧本有没有跑到」，
        # 不是「世界有没有变」。剧情因此从纯文案变成可核对的要素。
        "emitted_events": ",".join(sorted(
            k[len("emitted_"):] for k in st.score if k.startswith("emitted_"))),
        # —— 外生扰动的【真执行】账本 ——
        # `emitted_*` 只记「emit 这条镜头跑到过」；一旦某条桥段被升级成 L2 真机制
        # （evict_holder / suppress_slot / …），它就不再走 emit 通道，`emitted_*` 便查不到它。
        # `dispatch` 对每次真实投递都会 `add_score("disturb:<能力名>")`，故这里量的是
        # 「哪种能力真的执行过、执行了几次」—— 机制化的剧情靠这份账本才核得动。
        "disturb_capabilities": ",".join(sorted(
            k[len("disturb:"):] for k in st.score if k.startswith("disturb:"))),
        "disturb_total": int(sum(float(v) for k, v in st.score.items()
                                 if k.startswith("disturb:"))),
        # —— 耗尽维度（结论表里 annihilation 那条的驱动量）——
        "destruction_events": int(st.destruction_events),
        "deaths_competitive": int(st.score.get("deaths_competitive", 0.0)),
        "memory_repaired": int(st.score.get("memory_repaired", 0.0)),
        "attempt_stages_seen": ",".join(sorted({
            pl.get("stage") for _f, k, pl in traj.records
            if k in ("ATTEMPT_VAIN", "ATTEMPT_TRACE") and pl.get("stage")})),
        # —— 角色（全由演算涌现） ——
        "persona_count": len(personas),
        "persona_first_frame": min((p.surfaced_frame for p in personas), default=None),
        "persona_last_frame": max((p.surfaced_frame for p in personas), default=None),
        "persona_capabilities": ",".join(caps),
        "cap_suppress_slot": int("suppress_slot" in caps),
        "cap_write_memory": int("write_memory" in caps),
        "cap_overwrite_operator": int("overwrite_operator" in caps),
        # —— 命名（渲染层，随种子而变，不影响轨迹） ——
        "first_name_latin": names[0][0] if names else "",
        "first_name_hanzi": names[0][1] if names else "",
        "name_signature": hashlib.blake2b(
            "|".join(n[0] for n in names).encode("utf-8"), digest_size=6).hexdigest(),
        "style_syllables_max": style["syllables"][1],
        "style_coda_tilt": round(style["coda_tilt"], 3),
        "style_onset_tilt": round(style["onset_tilt"], 3),
        # —— 原初（第十三席）的真实读数 ——
        # 全由 `State.origin` 与回望驱动写下的 `traj.origin` 汇总给出；canonical 世界
        # 从不驱动它，故这里恒是「未成形 / 0 / 无在位者」。
        **_origin_features(st, traj),
    }


def _origin_features(st, traj) -> dict:
    o = getattr(st, "origin", None)
    meta = [i for i, l in enumerate(getattr(st, "loci", ()))
            if getattr(l, "meta", False)]
    occ = (st.register.slots[meta[0]].owner if meta else None)
    summ = getattr(traj, "origin", None) or {}
    return {
        "origin_ever": bool(o.ever) if o is not None else False,
        "origin_selfhood": round(float(o.selfhood), 6) if o is not None else 0.0,
        "origin_closure": int(o.closure) if o is not None else 0,
        "origin_borrowed": int(o.borrowed) if o is not None else 0,
        "origin_repaid": int(o.repaid) if o is not None else 0,
        "origin_occupant": occ,
        "origin_anchors": int(summ.get("anchors", getattr(o, "borrowed", 0) if o else 0)),
        "origin_missing": int(summ.get("missing", 0)),
        "origin_awake": bool(getattr(o, "awake", False)),
        "origin_create": int(st.score.get("origin_create", 0.0)),
        "origin_love": int(st.score.get("origin_love", 0.0)),
        "origin_trailblaze": int(st.score.get("origin_trailblaze", 0.0)),
        "origin_dissolved": int(st.score.get("origin_dissolved", 0.0)),
        "origin_form": int(getattr(o, "form", 0)) if o is not None else 0,
        "origin_coverage": round(float(getattr(o, "coverage", 0.0)), 6),
        "origin_factor_rows": int(getattr(o, "factor_rows", 0)) if o is not None else 0,
        "origin_companion": int(st.score.get("origin_companion", 0.0)),
        "origin_companion_alive": bool(
            int(getattr(o, "companion_serial", -1)) >= 0
            and st.pool.index_of_serial(int(getattr(o, "companion_serial", -1))) >= 0),
        "origin_companion_serial": int(getattr(o, "companion_serial", -1))
        if o is not None else -1,
        "origin_companion_spawn": int(st.score.get("origin_companion_spawn", 0.0)),
        "origin_companion_host": int(getattr(o, "companion_host", -1))
        if o is not None else -1,
        "origin_companion_stage": int(getattr(o, "companion_stage", 0))
        if o is not None else 0,
        "origin_companion_age": int(getattr(o, "companion_age", 0))
        if o is not None else 0,
        "origin_companion_carry": int(getattr(o, "companion_carry", 0))
        if o is not None else 0,
        "origin_companion_bond": int(getattr(o, "companion_bond", 0))
        if o is not None else 0,
        "origin_companion_grow": int(st.score.get("origin_companion_grow", 0.0)),
        "origin_companion_rebind": int(st.score.get("origin_companion_rebind", 0.0)),
        "origin_companion_rebond": int(st.score.get("origin_companion_rebond", 0.0)),
        "origin_companion_seat": int(st.score.get("origin_companion_seat", 0.0)),
        "origin_companion_eminence": int(
            "emitted_origin_companion_eminence" in st.score),
        "origin_attach": int(st.score.get("origin_attach", 0.0)),
        "origin_memory_seats": len(getattr(st, "memory_seats", ())),
        "origin_rebind": int(st.score.get("origin_rebind", 0.0)),
        "origin_resonance": int(st.score.get("origin_resonance", 0.0)),
        "origin_resonance_value": round(float(getattr(o, "resonance", 0.0)), 6)
        if o is not None else 0.0,
        "origin_resonance_host": int(getattr(o, "resonance_host", -1))
        if o is not None else -1,
        "origin_resonance_wake": int(st.score.get("origin_resonance_wake", 0.0)),
        "origin_savior": int(st.score.get("origin_savior", 0.0)),
        "origin_savior_active": bool(getattr(o, "savior_active", False))
        if o is not None else False,
        "origin_savior_transfer": int(st.score.get("origin_savior_transfer", 0.0)),
        "origin_memory_fragment": int(st.score.get("origin_memory_fragment", 0.0)),
        "origin_memory_transfer": int(st.score.get("origin_memory_transfer", 0.0)),
        "origin_memory_coupling": round(
            float(getattr(o, "memory_coupling_gain", 0.0)), 6) if o is not None else 0.0,
        "origin_memory_mutation": round(
            float(getattr(o, "memory_mutation_damp", 0.0)), 6) if o is not None else 0.0,
        "origin_memory_tick": int(st.score.get("origin_memory_tick", 0.0)),
        "origin_memory_phase": int(st.score.get("origin_memory_phase", 0.0)),
        "origin_gazed": int("emitted_origin_gazed" in st.score),
        "origin_seat_seized": int("emitted_seat_seized" in st.score),
        "origin_seat_reclaimed": int("emitted_origin_seat_reclaimed" in st.score),
        # —— 权柄层：命途 ——（canonical 世界恒为空）
        "path_joined": int(st.score.get("path_joined", 0.0)),
        "path_defected": int(st.score.get("path_defected", 0.0)),
        "path_members": len(getattr(st, "paths", {})),
        "path_emanators": len(getattr(st, "grants", {})),
        "path_revoked": int(st.score.get("path_revoked", 0.0)),
        "path_authorities": len(getattr(st, "authorities", {})),
        "path_affinity": round(max((float(v.get("affinity", 0.0))
                                    for v in getattr(st, "paths", {}).values()),
                                   default=0.0), 6),
        # —— 剧情接线的读数：全部来自真实状态，不是事件标签 ——
        "memory_rows": int(getattr(st, "memory_bank").shape[0]),
        "suppressed_slots": len(getattr(st, "suppressed", ())),
        "embers_taken": int(st.score.get("embers_taken", 0.0)),
        "external_seats": sum(
            1 for s in st.register.slots
            if s.owner is not None and int(s.owner) < 0 and int(s.owner) != -1),
        # 真实回退：checkpoint → gaze.rollback，世界真的退回本轮起点。
        "origin_rewinds": int(getattr(traj, "rewinds", 0)),
        "origin_rollbacks": int(st.score.get("rollbacks", 0.0)),
        # 具名因子：名字只是叙事标签，候选必须是池里真的长出来的个体。
        "factor_named": int(st.score.get("factor_named", 0.0)),
        # 决策：知道多少 → 决定 → 漏洞；入口：权杖防火墙。
        "factor_certainty": round(max(
            (float(v.get("certainty", 0.0))
             for v in getattr(st, "factor_ledger", {}).values()), default=0.0), 6),
        "factor_decided": int(st.score.get("factor_decided", 0.0)),
        "years_loophole": int(st.score.get("years_loophole", 0.0)),
        "entry_locked": int(bool(getattr(st, "entry_locked", False))),
        "entry_unlocked": int("entry_unlocked" in st.score),
        "final_recreation": int(st.score.get("final_recreation", 0.0)),
        # 浮黎锚定过去：把已经走过的那一段写进记忆（真实写入，不只是标签）。
        "fuli_anchor_past": int(st.score.get("fuli_anchor_past", 0.0)),
    }