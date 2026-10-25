"""外部扰动。

扰动【不能指定某个内生角色】——它只能作用于环境，或通过一个谓词选择器作用于一个集合。
能力名与实现的对应关系是一张通用注册表，与"谁在做"无关。
"""
from __future__ import annotations

import numpy as np

from .operators import (GATE_NAMES, MEMORY_OWNER, external_slots,
                       mean_seat_vector, meta_indices, pick_candidate, seat_index)
from .selector import Selector
from .state import MemoryFragment


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
        st.score["emitted_seat_seized"] = float(frame)
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
    if eff.get("origin"):
        # 目光落到【第十三席】身上：到这帧为止原初的自我分量被抬高，并当场苏醒。
        o = st.origin
        o.gaze_until = int(frame) + int(eff.get("duration", 512))
        o.awake = True
        o.form = max(int(o.form), 1)
        st.score["emitted_origin_gazed"] = float(frame)
        st.add_score("origin_gazed")
    actor = str(payload.get("actor", ""))
    if eff.get("authority"):
        # 这次目光同时把某条命途的管辖权交给这个实体（星神的权柄不是一次性动作）。
        ids = eff["authority"]
        if isinstance(ids, str):
            ids = [ids]
        st.authorities.setdefault(actor, set()).update(str(x) for x in ids)
        st.add_score("authority_granted")
    if eff.get("grant"):
        # 令使：只有【已经有管辖权】的实体才授得出去。
        g = eff["grant"] or {}
        path_id = str(g.get("path") or "")
        serial = g.get("serial")
        if serial is None or path_id not in st.authorities.get(actor, set()):
            st.add_score("grant_denied")
        else:
            st.grants[int(serial)] = {"path": path_id, "by": actor,
                                      "frame": int(frame)}
            st.score["emitted_emanator_granted"] = float(frame)
            st.add_score("emanator_granted")
    if eff.get("revoke") is not None:
        serial = int(eff["revoke"])
        if serial in st.grants:
            del st.grants[serial]
            st.score["emitted_path_revoked"] = float(frame)
            st.add_score("path_revoked")
            # 反噬：被收回权柄的人支持度受损（场外参与者不在池里，故只在池内生效）。
            k = st.pool.index_of_serial(serial)
            if k >= 0:
                st.pool.support[k] = max(
                    0.0, float(st.pool.support[k])
                    - float(eff.get("penalty", 5.0)))
    if eff.get("rollback"):
        # 真实的「本轮重来」：目光落到那个漏洞上，世界退回 checkpoint 存下的位置。
        # 只搬世界，账本（score / 轮次 / 个体史）不回退 —— 与 copy_world_from 同义。
        if getattr(st, "rewind_state", None) is None:
            st.add_score("rollback_refused")
        else:
            st.rewind_to = True
            st.add_score("rollback_requested")
    if eff.get("anchor_past"):
        # 浮黎把「已经走过的这一段」锚进记忆：把此刻十二席的样子写成记忆的最后一块。
        # 过去自此不可再改写（永劫回归不再重读）；这是一次真实写入，不只是记账。
        rows = [np.asarray(s.vector, dtype=np.float32)
                for s in st.register.slots if s.owner is not None]
        if rows:
            snap = np.stack(rows)
            st.memory_bank = (snap if st.memory_bank.shape[0] == 0
                              else np.concatenate([st.memory_bank, snap], axis=0))
        st.score["emitted_fuli_anchor_past"] = float(frame)
        st.add_score("fuli_anchor_past")
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
        row = _memory_row(st, i)
        slot.owner = MEMORY_OWNER
        slot.vector = row.copy()
        slot.value = float(row.max()) if row.size else 0.0
        # 交给记忆的那一席要登记为【记忆承载席】：否则下一帧 Occupy 会把它
        # 当成「外生占位但不是记忆席」清掉，末尾就出现莫名其妙的空缺。
        st.memory_seats.add(int(i))
        st.suppressed.discard(i)
        st.add_score("handed_to_memory")
        rec["state"]["handed"] = rec["state"].get("handed", 0) + 1
    if eff.get("steal_memory"):
        k = max(1, int(eff["steal_memory"]))
        st.memory_bank = (st.memory_bank[k:] if st.memory_bank.shape[0] > k
                          else st.memory_bank[:0])
        st.origin.factor_rows = min(int(st.origin.factor_rows),
                                    int(st.memory_bank.shape[0]))
        st.memory_seats = {i for i in st.memory_seats
                           if int(i) < int(st.origin.factor_rows)}
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


def _checkpoint(st, ctx, payload, targets, frame):
    """把此刻的【世界】存一份，供 `gaze.rollback` 真的退回这里。

    `to` 是回退后帧钟要落回的位置（缺省 = 存档这一帧）。它只存世界，不存账本：
    真正的回退走 `State.copy_world_from`，score / 轮次 / 个体史都留在外面。
    """
    st.rewind_state = st.clone()
    st.rewind_frame = int(payload.get("to", frame))
    st.add_score("checkpointed")


def _name_factor(st, ctx, payload, targets, frame):
    """给【演算自己长出来的】因子登记一个叙事名字（只记账，不改世界）。

    它不是「造一个人」：候选必须已经在池里。优先取选中席位上的在位者；
    没有在位者时，按 `factor` 取该因子里适应度最高的那一个。
    `role` 是数据层给的叙事名（如「甲」「乙」），内核不认识它，只把它
    原样记进账本 —— 于是报告能说「这两个名字是演算自己长出来的」。
    """
    role = str(payload.get("role") or "")
    if not role:
        st.add_score("factor_unnamed")
        return
    serial = None
    for i in (targets or ()):
        slot = st.register.slots[int(i)]
        if slot.owner is not None and int(slot.owner) >= 0:
            serial = int(slot.owner)
            break
    if serial is None:
        idx = st.pool.index()
        factor = payload.get("factor")
        if factor is not None:
            idx = idx[st.pool.factor[idx] == int(factor)]
        if idx.size:
            k = int(idx[np.argmax(st.pool.fitness[idx])])
            serial = int(st.pool.serial[k])
    if serial is None:
        st.add_score("factor_unnamed")
        return
    st.score["factor_" + role] = float(serial)
    # 账本：这个具名因子此后「知道了什么、有多确定」都在这里累积（不回滚）。
    st.factor_ledger[role] = {"serial": int(serial), "certainty": 0.0,
                             "knowledge": dict(payload.get("knowledge") or {})}
    st.add_score("factor_named")


def _hint(st, ctx, payload, targets, frame):
    """一句提示：只改具名因子【知道什么 / 有多确定】，不直接改世界。

    外部实体的一句提示就是这一手 —— 它不会替因子制造漏洞；它只把「还有别的
    星神在注视」这条信息交给他们。真正的决定由 `OP_DECIDE` 读 certainty 后自己做。
    """
    gain = float(payload.get("certainty", 0.5))
    roles = payload.get("roles")
    for role, rec in st.factor_ledger.items():
        if roles and role not in roles:
            continue
        rec.setdefault("knowledge", {})["other_aeons"] = True
        rec["certainty"] = min(1.0, float(rec.get("certainty", 0.0)) + gain)
    st.add_score("hint_given", float(len(st.factor_ledger)))


def _entry(st, ctx, payload, targets, frame):
    """权杖入口的防火墙：锁上 / 打开。打开之后，场外参与者才进得来。"""
    st.entry_locked = bool(payload.get("locked", True))
    st.add_score("entry_locked" if st.entry_locked else "entry_unlocked")


def _recreate(st, ctx, payload, targets, frame):
    """最后一次再创世：解除全部封印，把空缺的十二席补满。

    它不是「换人」的借口：只在**空席**上补人，已在位者不动；补的是池子里
    还没被占用的个体，按该席的适配度选。于是「再创世之后还剩三个空位」这种
    事故不会发生 —— 十二席在这一次之后必须是满的。
    """
    st.suppressed.clear()
    idx = st.pool.index()
    filled = 0
    for i, slot in enumerate(st.register.slots):
        if getattr(slot, "meta", False) or slot.filled():
            continue
        cand = [k for k in idx if not st.pool.held[k]]
        if not cand:
            break
        k = max(cand, key=lambda k: (float(st.pool.vec[k, i])
                                     * float(st.pool.fitness[k])))
        slot.owner = int(st.pool.serial[k])
        slot.vector = st.pool.vec[k].copy()
        slot.value = float(st.pool.vec[k, i] * st.pool.fitness[k])
        st.pool.held[k] = True
        st.pool.seated_clock[k] = st.world_clock
        filled += 1
    st.score["emitted_final_recreation"] = float(frame)
    st.add_score("final_recreation", float(filled))
    # 故事到此收束：十二席定席。此后不再有新的承位 / 涌现 / 死亡换手，
    # 只允许脚本里那几手「外部接掌」改座位（它们走 disturbance，不经过算子）。
    st.seats_frozen = True


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
    if getattr(st, "entry_locked", False) and not payload.get("force"):
        # 权杖防火墙：普通手段进不来，连找都找不到 —— 先由外部把入口打开。
        st.add_score("entry_denied")
        return
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
        # 外部变量可以带自己的【属性向量】：既可直接写在 payload.vector，
        # 也可由预设的 actors.json 按 actor id 查表（更干净的「角色属性表」）。
        # 不带 vector 时保持原行为（不改既有世界）。
        vec = payload.get("vector")
        if vec is None and payload.get("actor"):
            rec = st.actors.get(str(payload["actor"]))
            if rec is not None:
                vec = rec.get("vector")
        if vec is not None:
            v = np.asarray(vec, dtype=np.float32)
            if v.ndim == 1 and v.shape[0] == int(st.dim):
                total = float(v.sum())
                if total > 0.0:
                    v = (v / total).astype(np.float32)
                    slot.vector = v
                    slot.value = float(v.max())
        st.suppressed.discard(int(i))
        st.add_score("bound_participant")


def _memory_row(st, i):
    """第 i 席该用哪一行记忆：十二因子数据齐全时【逐席用自己的那一行】。

    这就是「十二行记忆决定可补哪一席」的落点：补第 i 席时读 memory_bank[i]，
    而不是所有记忆的平均。没有因子数据时才退回整体均值。
    """
    i = int(i)
    rows = int(getattr(st.origin, "factor_rows", 0))
    if rows > 0 and st.memory_bank.shape[0] >= rows and 0 <= i < rows:
        return np.asarray(st.memory_bank[i], dtype=np.float32)
    if st.memory_bank.shape[0]:
        return st.memory_bank.mean(axis=0).astype(np.float32)
    return mean_seat_vector(st, exclude=(i,))


def _hand_to_memory(st, i, frame, by=None, row=None):
    """把第 i 席交给记忆承载：现任活体让位（记 displaced），席位交给 MEMORY_OWNER。"""
    slot = st.register.slots[int(i)]
    if slot.owner is not None and int(slot.owner) >= 0:
        k = st.pool.index_of_serial(int(slot.owner))
        if k >= 0:
            st.bury(frame, int(k), "displaced", by)
            st.pool.kill(int(k))
            st.death_events += 1
            st.add_score("evicted")
    mean = _memory_row(st, i) if row is None else np.asarray(row, dtype=np.float32)
    slot.owner = MEMORY_OWNER
    slot.vector = mean.copy()
    slot.value = float(slot.vector.max()) if slot.vector.size else 0.0
    st.suppressed.discard(int(i))


def _origin_anchor(st, ctx, payload, targets, frame):
    """回望锚点：原初带着未来的记忆，在【重演的过去节点】上补一手。

    它是普通外生投递（exact frame），不是内核预读未来 —— 每一遍仍严格单向。
    动作只在原初已成形且能量足够时生效（唯一的例外是 `wake_origin`：它就是唤醒
    原初本身，故可在尚未成形时用）。借还各记一笔：投出去的算「借」，真正补上的算「还」。
    """
    o = st.origin
    action = str(payload.get("action") or "")
    cost = float(payload.get("cost", 1.0))
    seat_id = payload.get("seat")
    gate = payload.get("gate")

    if action == "wake_origin":
        meta = meta_indices(st)
        if meta:
            mi = int(meta[0])
            slot = st.register.slots[mi]
            if not slot.filled():
                mean_vec = mean_seat_vector(st, exclude=(mi,))
                k = pick_candidate(st, mi, mean_vec)
                if k >= 0:
                    slot.owner = int(st.pool.serial[k])
                    slot.value = float(st.pool.vec[k, mi] * st.pool.fitness[k])
                    slot.vector = st.pool.vec[k].copy()
                    st.pool.held[k] = True
                    st.pool.seated_clock[k] = st.world_clock
                    o.awake = True
                    o.form = max(int(o.form), 1)
                    o.ever = True
                    o.filled = True
                    o.energy = max(float(o.energy), cost)
                    o.borrowed += 1
                    o.repaid += 1
                    st.add_score("origin_wake")
                    return
            elif not o.ever and int(slot.owner) >= 0:
                # 席位有人、但原初分量还没越过阈值：把在位者的向量真的抬过线。
                # （下一帧 OP_OCCUPY 会从池里重新读向量，故必须改池中那一份。）
                k = st.pool.index_of_serial(int(slot.owner))
                if k >= 0:
                    target = max(float(ctx.params.get("tau_origin", 0.12)) * 1.5, 0.2)
                    v = st.pool.vec[k].copy()
                    rest = v.copy()
                    rest[mi] = 0.0
                    need = target / (1.0 - target) * float(rest.sum())
                    if float(v[mi]) < need:
                        v[mi] = need
                        v /= float(v.sum())
                        st.pool.vec[k] = v
                        slot.vector = v.copy()
                    o.selfhood = target
                    o.awake = True
                    o.form = max(int(o.form), 1)
                    o.ever = True
                    o.filled = True
                    o.energy = max(float(o.energy), cost)
                    o.borrowed += 1
                    o.repaid += 1
                    st.add_score("origin_wake")
                    return
            if o.ever:
                o.awake = True
                o.form = max(int(o.form), 1)
                o.borrowed += 1
                o.repaid += 1
                st.add_score("origin_wake")
                return
        st.add_score("origin_anchor_refused")
        return

    # 其余动作都要求原初已成形、且能量足够 —— 否则这一手落不下去。
    o.borrowed += 1
    if not o.ever or float(o.energy) < cost:
        st.add_score("origin_anchor_refused")
        return

    ok = False
    if action == "bind_memory":
        i = seat_index(st, seat_id) if seat_id is not None else -1
        if i < 0:
            i = next((k for k, s in enumerate(st.register.slots)
                      if not s.meta and not s.filled()), -1)
        if i >= 0 and not st.register.slots[int(i)].meta:
            _hand_to_memory(st, int(i), frame, payload.get("node"),
                            row=_memory_row(st, i))
            # 只有【用对了那一行】的补席才登记为记忆承载席：它此后抵抗封印、
            # 空了还能由同一行补回。没有因子数据时只算临时交给记忆。
            if (int(st.origin.factor_rows) > 0
                    and int(i) < int(st.origin.factor_rows)
                    and st.memory_bank.shape[0] >= int(st.origin.factor_rows)):
                st.memory_seats.add(int(i))
            ok = True
            st.add_score("origin_bind_memory")
    elif action == "seed_memory":
        idx = st.pool.index()
        mode = str(payload.get("mode") or "")
        if mode == "savior":
            # 「救世主记忆」：回望时收下的一段真实记忆内容。优先取共鸣中的外部
            # 变量的属性向量；没有外部变量时退回原初/记忆均值。
            vec = None
            ext = external_slots(st)
            if ext:
                _i, _s = max(ext, key=lambda t: float(t[1].value))
                vec = np.asarray(_s.vector, dtype=np.float32).copy()
            elif st.memory_bank.shape[0]:
                vec = st.memory_bank.mean(axis=0).astype(np.float32)
            else:
                meta = meta_indices(st)
                if meta and st.register.slots[meta[0]].filled():
                    vec = np.asarray(st.register.slots[meta[0]].vector,
                                     dtype=np.float32).copy()
            mem = payload.get("memory") or {}
            mv = mem.get("vector")
            if mv is not None:
                v2 = np.asarray(mv, dtype=np.float32)
                if v2.ndim == 1 and v2.shape[0] == int(st.dim):
                    vec = v2
            if vec is not None:
                total = float(vec.sum())
                if total > 0.0:
                    vec = (vec / total).astype(np.float32)
                    st.origin.savior_vector = vec.copy()
                    st.origin.savior_active = True
                    st.memory_bank = (
                        vec.reshape(1, -1) if st.memory_bank.shape[0] == 0
                        else np.concatenate([st.memory_bank, vec.reshape(1, -1)],
                                            axis=0))
                    duration = int(mem.get("duration", 0) or 0)
                    frag = MemoryFragment(
                        mem.get("id") or "savior",
                        mem.get("label") or "",
                        vec,
                        mem.get("effect") or "fitness",
                        float(mem.get("magnitude", 0.0) or 0.0),
                        (int(frame) + duration) if duration > 0 else 0,
                        bool(mem.get("sustain", False)),
                        float(mem.get("rate", 0.0) or 0.0),
                        phases=mem.get("phases"))
                    st.origin.memory_fragments = [
                        f for f in st.origin.memory_fragments
                        if str(f.id) != str(frag.id)]
                    st.origin.memory_fragments.append(frag)
                    st.add_score("memory_written", 1.0)
                    st.add_score("origin_savior")
                    st.add_score("origin_memory_fragment")
        elif mode == "factor_basis":
            # 「载入十二因子数据」：每个非 meta 因子一行（取该因子池内均值；
            # 没有活体时退回一维基向量）。这是对记忆库的真实写入，不是渲染。
            rows = []
            for i, locus in enumerate(st.loci):
                if getattr(locus, "meta", False):
                    continue
                same = (idx[st.pool.factor[idx] == i] if idx.size else idx)
                if same.size:
                    rows.append(st.pool.vec[same].mean(axis=0))
                else:
                    v = np.zeros(int(st.dim), dtype=np.float32)
                    v[i] = 1.0
                    rows.append(v)
            if rows:
                st.memory_bank = np.stack(rows).astype(np.float32)
                st.origin.factor_rows = int(len(rows))
                st.add_score("memory_written", float(len(rows)))
        elif idx.size:
            vecs = st.pool.vec[idx].copy()
            st.memory_bank = (vecs if st.memory_bank.shape[0] == 0
                              else np.concatenate([st.memory_bank, vecs], axis=0))
            st.add_score("memory_written", float(idx.size))
        i = seat_index(st, seat_id) if seat_id is not None else -1
        if i >= 0 and not st.register.slots[int(i)].meta:
            _hand_to_memory(st, int(i), frame, payload.get("node"),
                            row=_memory_row(st, i))
            if (int(st.origin.factor_rows) > 0
                    and int(i) < int(st.origin.factor_rows)
                    and st.memory_bank.shape[0] >= int(st.origin.factor_rows)):
                st.memory_seats.add(int(i))
        ok = st.memory_bank.shape[0] > 0
        if ok:
            st.add_score("origin_seed_memory")
    elif action == "open_gate":
        if gate in GATE_NAMES:
            st.gates.add(str(gate))
            ok = True
            st.add_score("origin_open_gate")

    if ok:
        o.repaid += 1
        o.energy = max(0.0, float(o.energy) - cost)
        # 某些锚点会【带来一件事】（例如「救世主记忆」）：只有真的落下去才记事件。
        ev = payload.get("emit_event")
        if ev is not None:
            st.score["emitted_" + str(ev)] = float(frame)
    else:
        st.add_score("origin_anchor_refused")


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
    "checkpoint": _checkpoint,
    "name_factor": _name_factor,
    "hint": _hint,
    "entry": _entry,
    "recreate": _recreate,
    "overwrite_conclusion": _overwrite_conclusion,
    "origin_anchor": _origin_anchor,
    "emit": _emit,
}