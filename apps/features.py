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
    }