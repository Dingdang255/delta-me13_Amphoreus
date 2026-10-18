"""外部扰动。

扰动【不能指定某个内生角色】——它只能作用于环境，或通过一个谓词选择器作用于一个集合。
能力名与实现的对应关系是一张通用注册表，与"谁在做"无关。
"""
from __future__ import annotations

import numpy as np

from .operators import MEMORY_OWNER
from .selector import Selector


def _match(st, cond) -> bool:
    if not cond:
        return True
    return getattr(st, str(cond["field"]), None) == cond["equals"]


def dispatch(rec, st, ctx, frame):
    if not _match(st, rec.get("active_if")):
        return st, False
    cap = rec.get("capability")
    fn = CAPABILITIES.get(cap)
    if fn is None:
        raise KeyError(f"未注册的能力: {cap}")
    sel = rec.get("selector") or None
    targets = None
    if sel:
        domain = list(range(len(st.loci)))
        targets = Selector(str(sel["expr"])).eval(domain, st, ctx)
    payload = dict(rec.get("payload") or {})
    # 登记【剧情事件名】：机制化不该把可核对性丢掉。
    # 凡 payload 带 `event` 就记一条 `emitted_<event>` —— 于是「这条桥段有没有真的
    # 执行过」在【镜头（emit）】与【机制（evict_holder / suppress_slot / …）】两种形态下
    # 口径完全一致。`_emit` 自己已经登记，故这里只管其余能力，不重复写同一个键。
    if cap != "emit" and payload.get("event"):
        st.score["emitted_" + str(payload["event"])] = float(frame)
    fn(st, ctx, payload, targets, frame)
    st.add_score("disturb:" + str(cap))
    return st, True


# ---------------------------------------------------------------- 能力注册表
def _modify_operator(st, ctx, payload, targets, frame):
    if payload.get("enable"):
        st.gates.add(str(payload["enable"]))
    if payload.get("from") == st.solver and payload.get("to"):
        st.solver = str(payload["to"])


def _overwrite_operator(st, ctx, payload, targets, frame):
    if payload.get("to"):
        st.solver = str(payload["to"])
    if payload.get("clear_suppression"):
        st.suppressed.clear()


def _suppress_slot(st, ctx, payload, targets, frame):
    for i in (targets or []):
        st.suppressed.add(int(i))


def _release_slot(st, ctx, payload, targets, frame):
    for i in (targets or []):
        st.suppressed.discard(int(i))


def _raise_noise(st, ctx, payload, targets, frame):
    st.noise += float(payload.get("amplitude", 0.05))


def _mask_observer(st, ctx, payload, targets, frame):
    st.add_score("masked_observer")


def _plead(st, ctx, payload, targets, frame):
    """游说：陈说利害，指望对面自己交出手里的那一份。改不了世界一丝，只入账。"""
    st.add_score("pleaded")


def _barter(st, ctx, payload, targets, frame):
    """交易：以条件换一次让步。同样改不了世界一丝。"""
    st.add_score("bartered")


def _evict_holder(st, ctx, payload, targets, frame):
    """令选中的位【在位者离席】：那个体退出，席位空出来，下一帧再选人接手。

    与「压制」不同 —— 压制只是暂时封住这一席，解除后原主照旧回来；逐出是真的走人，
    所以席位会落到别人头上。它是「换人」而不是「改名」。

    **并记一笔权柄账本（`embers_taken`）**：这是「暴力夺取」与「和平归还」唯一的分别 ——
    `Promotion` 会拿它抬高再创世门槛：**被夺走的份数越多，这个世界越难走到终点**。

    为何**不**去削 `locus.capacity`：那看着像"位被破坏"，但实测 `locus.load` 中位 30.9
    而 `capacity` 中位 0.0148（还随再创世逐代乘 0.9 衰减）—— `load > capacity` **恒成立
    （100.00%）**，削它一遍遍地改一个恒真的判据，等于没改。真正有效的是上面那笔账。
    """
    for i in (targets or []):
        slot = st.register.slots[int(i)]
        if slot.owner is None:
            continue
        st.add_score("embers_taken")
        k = st.pool.index_of_serial(int(slot.owner))
        if k >= 0:
            st.bury(frame, int(k), "evicted", payload.get("actor"))
            st.pool.kill(int(k))
            st.death_events += 1
            st.add_score("evicted")
        slot.owner, slot.value = None, 0.0


def _parley(st, ctx, payload, targets, frame):
    """交涉：以条件换让步，指望对面**自愿**交出手里的那一份。

    与 `evict_holder` 是一对（和平 / 强硬地取得席位），区别在于**谈成时在位者自愿离席**
    —— `owner = None` 而**不 kill**：人还活着，只是不再守这一席。于是两条路的**伤亡账
    各自可核对**（`evicted` + 死亡计数 vs `parley_granted`）。

    为什么另起一个名字而不复用 `plead`：`plead` 已被【尝试阶梯】占用（`params.attempt_stages`），
    那条路径上的语义是刻意保留的**无能**（"仅凭陈说利害，什么都改变不了"，故不动世界一丝）。
    而这里的交涉是**真的让对方交出来** —— 两者语义相反，共用一个名字会让能力注册表
    "一个名字对应一种行为"的契约失效。

    成败**不掷骰子**，由该席此刻的处境决定（"对面愿不愿意给"本来就不是随机的）：

      · **手里越空越愿意给**：`slot.value <= tau_parley`；
      · **状态尚清才谈得拢**：`noise <= tau_noise_parley`（溢出压过这条线，无论手里多少都谈不成）。

    两条都过才成；缺一条即记 `parley_refused`。判据只用现成的量，**不新增 State 字段**。
    """
    p = ctx.params
    tau_v = float(p.get("tau_parley", 0.0))
    tau_nz = float(p.get("tau_noise_parley", float("inf")))
    for i in (targets or []):
        slot = st.register.slots[int(i)]
        if slot.owner is None:
            continue
        if float(st.noise) <= tau_nz and float(slot.value) <= tau_v:
            slot.owner, slot.value = None, 0.0
            st.add_score("parley_granted")
            st.add_score("embers_returned")   # 自愿交出：**不削权柄**（位仍完整）
        else:
            st.add_score("parley_refused")


def _freeze_privilege(st, ctx, payload, targets, frame):
    st.add_score("frozen_privilege", float(payload.get("ratio", 0.0)))


def _revise_protocol(st, ctx, payload, targets, frame):
    """凭【修改权限】覆写演算规则（账本语义，不随世界回滚）。

    执行者必须已登记；每条待改写的规则都须在它的权限表内，否则该条被拒 ——
    这就是「修改权限」的真实语义：有权限才改得动，没权限一个字都改不了。
    真写进覆盖表后，算子会据此换一条算法分支（见 operators.Promotion 的 mode）。
    """
    rec = st.actors.get(str(payload.get("actor", "")))
    if rec is None:
        st.add_score("protocol_denied")
        return
    grants = set(rec.get("grants") or ())
    changed, denied = [], []
    for r in (payload.get("rewrites") or []):
        rule, value = str(r.get("rule", "")), r.get("value")
        if rule not in grants:
            denied.append(rule)
            continue
        st.overrides[rule] = value          # 真写覆盖表
        changed.append(rule)
    if changed:
        st.add_score("protocol_rewritten", float(len(changed)))
        rec["state"]["rewrote"] = rec["state"].get("rewrote", 0) + len(changed)
        rec["state"]["last_rewrite_frame"] = float(frame)
    if denied:
        st.add_score("protocol_denied", float(len(denied)))


def _gaze(st, ctx, payload, targets, frame):
    """星神的目光：实体对演算施加一次真实作用 —— 打开一道机制，或拨动演算方向。

    与匿名的「改写算子」不同：这是【具名实体】的动作，必须先登记。
    """
    rec = st.actors.get(str(payload.get("actor", "")))
    if rec is None:
        st.add_score("gaze_unregistered")
        return
    eff = payload.get("effect") or {}
    if eff.get("gate"):
        st.gates.add(str(eff["gate"]))
    if eff.get("solver"):
        st.solver = str(eff["solver"])
    rec["state"]["gazes"] = rec["state"].get("gazes", 0) + 1
    rec["state"]["last_gaze_frame"] = float(frame)


def _interstice(st, ctx, payload, targets, frame):
    """狭间：实体在此做一件本地规则做不到的事 —— 把一席交给记忆承载，或窃走一段记忆。

    与「令其离席」不同：逐出只是空出来，还得等本因子的活人来补；狭间是【外部补位】，
    直接把这一席交给记忆（MEMORY_OWNER）—— 本地永远补不上的席位，只有这里补得动。
    """
    rec = st.actors.get(str(payload.get("actor", "")))
    if rec is None:
        st.add_score("interstice_unregistered")
        return
    eff = payload.get("effect") or {}
    if eff.get("hand_locus") is not None:
        i = int(eff["hand_locus"])
        slot = st.register.slots[i]
        slot.owner = MEMORY_OWNER
        slot.value = (float(st.memory_bank.mean(axis=0).max())
                      if st.memory_bank.shape[0] else 0.0)
        st.suppressed.discard(i)
        st.add_score("handed_to_memory")
        rec["state"]["handed"] = rec["state"].get("handed", 0) + 1
    if eff.get("steal_memory"):
        k = max(1, int(eff["steal_memory"]))
        st.memory_bank = (st.memory_bank[k:] if st.memory_bank.shape[0] > k
                          else st.memory_bank[:0])
        st.add_score("memory_stolen", float(k))
        rec["state"]["stolen"] = rec["state"].get("stolen", 0) + 1


def _write_memory(st, ctx, payload, targets, frame):
    idx = st.pool.index()
    if idx.size == 0:
        return
    vecs = st.pool.vec[idx].copy()
    st.memory_bank = vecs if st.memory_bank.shape[0] == 0 else np.concatenate(
        [st.memory_bank, vecs], axis=0
    )
    st.add_score("memory_written", float(idx.size))


def _emit(st, ctx, payload, targets, frame):
    st.score["emitted_" + str(payload.get("event", "?"))] = float(frame)


def _overwrite_conclusion(st, ctx, payload, targets, frame):
    """载入外生核心变量：改写【结论】。

    它不动世界一个比特 —— 改的是"实验得出什么答案"，不是"世界怎么走"。
    与 `overwrite_operator`（改写演算方向）分工不同：那个改动力学，这个改结论。
    """
    st.conclusion_override = str(payload.get("to", "overwritten"))
    st.add_score("conclusion_overwritten")
    if payload.get("variable"):
        st.score["core_variable"] = float(frame)


def _bind_participant(st, ctx, payload, targets, frame):
    """外部变量【接掌】选中的位：把一个带外编号的场外参与者直接放进那一席。

    与「令其离席」同性质（现任者若是在池活体，同样陨落、让位），但接手的不是本地
    补种出来的新人，而是预设登记过的场外参与者（编号 < 0，不进池）。于是这一席
    「本地永远补不上、也不被活体争夺」，却真的有人坐着 —— 这正是场外参与的意义。
    payload.participant = 那个带外编号（必须 < 0，否则拒收）。
    """
    serial = payload.get("participant")
    if serial is None or int(serial) >= 0:
        st.add_score("bind_denied")
        return
    for i in (targets or []):
        slot = st.register.slots[int(i)]
        if slot.owner is not None:                 # 现任者让位（在池者陨落，账目与逐出一致）
            k = st.pool.index_of_serial(int(slot.owner))
            if k >= 0:
                st.bury(frame, int(k), "displaced", payload.get("actor"))
                st.pool.kill(int(k))
                st.death_events += 1
                st.add_score("evicted")
        slot.owner = int(serial)                   # 带外编号：外生占位，不被活体抢占
        st.suppressed.discard(int(i))
        st.add_score("bound_participant")


CAPABILITIES = {
    "modify_operator": _modify_operator,
    "overwrite_operator": _overwrite_operator,
    "suppress_slot": _suppress_slot,
    "release_slot": _release_slot,
    "raise_noise": _raise_noise,
    "mask_observer": _mask_observer,
    "plead": _plead,
    "barter": _barter,
    "evict_holder": _evict_holder,
    "parley": _parley,
    "bind_participant": _bind_participant,
    "freeze_privilege": _freeze_privilege,
    "revise_protocol": _revise_protocol,
    "gaze": _gaze,
    "interstice": _interstice,
    "write_memory": _write_memory,
    "overwrite_conclusion": _overwrite_conclusion,
    "emit": _emit,
}