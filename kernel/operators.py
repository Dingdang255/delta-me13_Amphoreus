"""L2：通用算子。

每个算子只做【一帧】的转移；没有任何 per-locus 分支，没有任何专有名词。
位的语义完全由【数值】决定，不由代码决定。
"""
from __future__ import annotations

import numpy as np

from .state import SOLVER_NAMES

MEMORY_OWNER = -1   # 由记忆承载的位：不会被活体重新争夺


def is_external_owner(owner) -> bool:
    """这一席的承载者是不是【外生】的（编号 < 0）—— 不从池子里长出来的场外参与者。

    带外编号构成一族：`MEMORY_OWNER`（由记忆承载）只是其中一员；预设登记的场外参与者
    （`bind_participant` 投进来的那些）用别的负号。判据只看【编号的符号】这个状态标志，
    不看名字 —— 于是换词表 / 换命名器都不改轨迹（命名正交）。外生占位一律：
    不被活体抢占 / 不被逐火驱逐 / 不被竞争淘汰 / 不计入涌现。
    """
    return owner is not None and int(owner) < 0


def holds_memory(st, owner) -> bool:
    """这一席是不是【记忆一方】在守：记忆本身（-1），或走到「忆者」的忆灵。

    忆者是一个真实的池中个体（编号 ≥ 0），但它持有的是记忆承载席 —— 因此它和
    `MEMORY_OWNER` 一样抵抗封印、不被活体抢占。canonical 世界既没有忆灵也没有
    `memory_seats`，故这条判断在那一边从不成立。
    """
    if owner is None:
        return False
    s = int(owner)
    if s == MEMORY_OWNER:
        return True
    if s < 0:
        return False
    k = st.pool.index_of_serial(s)
    return k >= 0 and "origin_companion" in st.pool.tags[k]


#: `overrides` 里 `renewal.mode` 的这个取值 = 「换代时规则由决策账本给出」（主动更替）。
#: 与 `promotion.mode` 同处一张覆盖表：那条改的是**怎么换代**（原位升格 / 记忆再造），
#: 这条改的是**规则从哪来**（席位向量 / 决策账本）。
DECISION_LEDGER = "decision_ledger"

#: 机制门名 —— 会被算子【读取】的那些。加一个门 = 在这里补一项，并在读它的算子里引用。
#: 配置里（阶段装配的 on / 扰动 payload）只允许出现登记过的门名：写错过去只是静默失效
#: （门开了，却没有任何算子在读它）。
MEMORY_INHERIT_GATE = "OP_MEMORY_INHERIT"


class Operator:
    name = "OP_X"

    def apply(self, st, ctx, rng, frame):    # pragma: no cover - 抽象
        raise NotImplementedError


class Drift(Operator):
    """向量漂移：位与位之间的耦合牵引 + 逐帧变异。"""

    name = "OP_DRIFT"

    def apply(self, st, ctx, rng, frame):
        p = ctx.params
        idx = st.pool.index()
        if idx.size == 0:
            return st
        old = st.pool.vec[idx]
        v = old.copy()
        gain = float(p["coupling_gain"])
        sigma_base = float(p["mutation"])
        # 「爱」：原初在能量足够时打开一个短时间窗，让耦合变紧、变异变小。
        # canonical 世界的 origin 从不驱动（love_until 恒 0）⇒ 下面这一支不进，
        # 两个乘数都是 1.0 的原路径 ⇒ 逐位不变。
        _o = getattr(st, "origin", None)
        if _o is not None and int(_o.love_until) > int(frame):
            gain *= (1.0 + float(p.get("origin_love_coupling", 0.0)))
            sigma_base *= max(0.0, 1.0 - float(p.get("origin_love_damp", 0.0)))
        # 记忆片段转印后的短时作用窗（coupling / mutation）。
        if _o is not None:
            if int(getattr(_o, "memory_coupling_until", 0)) > int(frame):
                gain *= (1.0 + float(getattr(_o, "memory_coupling_gain", 0.0)))
            if int(getattr(_o, "memory_mutation_until", 0)) > int(frame):
                sigma_base *= max(
                    0.0, 1.0 - float(getattr(_o, "memory_mutation_damp", 0.0)))
        push = (v @ ctx.coupling) * gain
        sigma = sigma_base * (1.0 + p["noise_to_mutation"] * st.noise)
        v = v + push + rng.normal(0.0, sigma, size=v.shape).astype(np.float32)
        np.clip(v, 0.0, None, out=v)
        s = v.sum(axis=1, keepdims=True)
        s[s <= 0] = 1.0
        new = (v / s).astype(np.float32)
        st.pool.vec[idx] = new

        # 定型（P2）：轨迹进入吸引子 —— 逐帧位移小于阈值则累加，否则清零。
        # 这是「自我相似度」的逐步形式，对全体个体统一求值，不点名。
        step = np.linalg.norm(new - old, axis=1)
        eps = float(p["stability_eps"])
        st.pool.stable[idx] = np.where(step < eps, st.pool.stable[idx] + 1, 0)
        return st


class Interact(Operator):
    """相互作用：相似者相吸、相斥者相背 —— 势力/派系由此自发形成。"""

    name = "OP_INTERACT"

    def apply(self, st, ctx, rng, frame):
        p = ctx.params
        idx = st.pool.index()
        m = idx.size
        if m < 2:
            return st
        v = st.pool.vec[idx]
        # 池向量恒是【非负的归一化分布】⇒ 余弦相似度必非负：
        #   pos = clip(sim, 0, None) 逐位就是 sim 本身；
        #   neg = clip(-sim, 0, None) 逐位恒为 0（于是 rival = 0 / (0 + 1e-8) = 0）。
        # 据此省掉一次全矩阵 clip、一次全矩阵求和与一次 (n,n)@(n,d) 乘。
        #
        # 结合律改写：`(v@vᵀ)@v` 与 `v@(vᵀ@v)` 恒等（矩阵乘法结合律），但前者要先
        # 拉起一个 **m×m** 的相似度矩阵（m = 池中人数），代价 ∝ m²d；后者只拉起
        # **d×d**（d = 12 固定），代价 ∝ md²。池子一大就差 m/d 倍。
        # `support`（行和、对角线归零）同样绕开全矩阵：行和 = `v @ (v 的列和)`，
        # 再减掉对角线 `v_i·v_i`。
        # ⚠ float32 不满足结合律 ⇒ 逐位结果改变（会动轨迹，须重测指纹与全部期望）。
        colsum = v.sum(axis=0)                         # (d,)
        self_sim = np.einsum("ij,ij->i", v, v)         # 对角线 v_i·v_i
        gram = v.T @ v                                 # (d,d)
        support = v @ colsum - self_sim                # 行和（对角线已减）
        ally = (v @ gram - self_sim[:, None] * v) / (support[:, None] + 1e-8)
        g, r = p["interact_gain"], p["interact_repel"]
        v = v + g * (ally - v) + r * v          # 原式 - r * (rival - v)，rival 恒 0
        np.clip(v, 0.0, None, out=v)
        s = v.sum(axis=1, keepdims=True)
        s[s <= 0] = 1.0
        # 原地归一化：池向量本是 float32，`(v / s).astype(np.float32)` 那一步只是
        # 同 dtype 的白复制 —— 去掉它，写回的值逐位不变。
        v /= s
        st.pool.vec[idx] = v
        st.pool.support[idx] = support
        return st


class Occupy(Operator):
    """承位：每一席只由【同因子】的个体来担，不是谁强谁占。

    候选池远多于席位，但命定只看因子对不对得上：因子不符者不来争夺。
    同一因子内，仍由当前最能承载它的那一个承位（可换手，也可空着）。
    """

    name = "OP_OCCUPY"

    def apply(self, st, ctx, rng, frame):
        if getattr(st, "seats_frozen", False):
            return st
        idx = st.pool.index()
        if idx.size == 0:
            return st
        v = st.pool.vec[idx]
        fit = st.pool.fitness[idx]
        serials = st.pool.serial[idx]
        home = st.pool.factor[idx]

        for i, locus in enumerate(st.loci):
            st.loci[i].load = float(v[:, i].sum())
            slot = st.register.slots[i]

            if i in st.suppressed:                       # 被外部压制的位
                # 由十二因子数据补上的席位【抵抗封印】：记忆（或忆者）守着它，不被清空。
                # canonical 世界 memory_seats 恒为空 ⇒ 这一支不进，行为不变。
                if not (i in st.memory_seats and holds_memory(st, slot.owner)):
                    slot.owner, slot.value = None, 0.0
                else:
                    st.score["emitted_origin_memory_seal_resisted"] = float(frame)
                continue
            if is_external_owner(slot.owner):            # 外生占位（记忆承载 / 场外参与者），不被活体抢占
                continue

            if slot.owner is not None:                   # 命定：一旦承位，只要还活着就不动
                if st.pool.index_of_serial(slot.owner) < 0:
                    slot.owner = None

            if slot.owner is None:
                same = np.flatnonzero(home == i)         # 命定：只有同因子者能担这一席
                if same.size == 0:
                    continue
                # 席位归其因子：只要该因子还有人，就由其中最强的那个担（不是谁强谁占）。
                score = v[same, i] * fit[same]
                j = int(np.argmax(score))
                slot.owner = int(serials[same[j]])
                slot.value = float(score[j]) * (1.0 - locus.decay)
                slot.vector = v[same[j]].copy()
                st.pool.held[idx[same[j]]] = True
                st.pool.seated_clock[idx[same[j]]] = st.world_clock
            else:
                k = st.pool.index_of_serial(slot.owner)
                if k >= 0:
                    slot.value = float(st.pool.vec[k, i] * st.pool.fitness[k]) * (1.0 - locus.decay)
                    slot.vector = st.pool.vec[k].copy()
        return st


class Compete(Operator):
    """淘汰：被孤立者死亡、衰老死亡。死亡计数就是「失序倾向」的原始信号。

    「孤立」用【平均相似度】度量 —— 即该个体与池中其他个体的余弦相似度均值，
    尺度无关（0～1）：人多人少都可比。阈值是 params.tau_support。

    世界一旦【溢出】（noise 越过 params.tau_noise_annihilation），淘汰门槛就换了对象：
    不再看孤立，而是看谁【被同化得最深】—— 平均相似度越过 params.tau_homogenized
    者视为已经融进溢出里，当场被吞没。这些死亡都计入 destruction_events，
    它就是「万物被自身耗尽」那条结论的驱动量。

    量值参照（seed 0，实测）：plot / nullify / emergent 的个体平均相似度在
    0.066～0.071 之间，且分布极窄（p5 与最小值几乎重合）—— 也就是说，既有世界里
    没有「被孤立者」这个类别，tau_support=0.02 对它们从不成立，故逐帧不变；
    淹没世界（tide）反过来被均值 0.20 的同化压过 tau_homogenized=0.15。
    """

    name = "OP_COMPETE"

    def apply(self, st, ctx, rng, frame):
        if getattr(st, "seats_frozen", False):
            return st
        p = ctx.params
        idx = st.pool.index()
        if idx.size == 0:
            return st
        sup = st.pool.support[idx]
        rel = sup / max(1, idx.size - 1)      # 平均相似度：与人数无关
        age = frame - st.pool.born[idx]
        serials = st.pool.serial[idx]
        owners = {s.owner for s in st.register.slots if s.owner is not None}

        if st.noise >= float(p.get("tau_noise_annihilation", float("inf"))):
            doomed = np.flatnonzero(rel >= float(p.get("tau_homogenized", 1.0)))
            cause = "homogenized"          # 已被同化进溢出里，当场被吞没
        else:
            doomed = np.flatnonzero(
                (rel < float(p["tau_support"])) & (age > p["tau_age"]))
            cause = "isolated"             # 被孤立
        for k in doomed:
            s = int(serials[k])
            if s in owners:
                continue
            st.bury(frame, int(idx[k]), cause)
            st.pool.kill(int(idx[k]))
            st.death_events += 1
            st.destruction_events += 1
            st.add_score("deaths_competitive")

        # 嵌合协议若已生效（见 Annex），非嵌合因子的个体更早退出演算 —
        # 协议是账本、跨轮回不回滚，于是它真的「成为后续的默认值」。
        span = np.full(idx.size, float(p["life_span"]), dtype=np.float64)
        annex = st.overrides.get("annex.factor")
        if annex is not None:
            ratio = float(st.overrides.get("annex.span_ratio", 1.0))
            span[st.pool.factor[idx] != int(annex)] = float(p["life_span"]) * ratio
        # 忆灵不随普通电信号一起老去：它由原初维持，寿命另算一条。
        # canonical 世界没有 `origin_companion_span` ⇒ 整段不执行，寿命表逐位不变。
        comp_span = p.get("origin_companion_span")
        if comp_span is not None:
            for k, i in enumerate(idx):
                if "origin_companion" in st.pool.tags[int(i)]:
                    span[k] = float(comp_span)
        old = np.flatnonzero(age > span)
        for k in old:
            st.bury(frame, int(idx[k]), "aged")
            st.pool.kill(int(idx[k]))
            st.death_events += 1
            st.add_score("deaths_natural")
        return st


class Annex(Operator):
    """嵌合协议：某一支因子强势到能改写协议时，把【它的决策逻辑写成协议内容】。

    考据（biligame）：第 1480 行「为提升迭代速率，开放因子自内部嵌合协议的权限。
    **特定电信号的决策逻辑将转化为协议内容**，以辅助权杖优化实验结构。」
    第 19,522,113 次循环（阶段三区间内）：据考据，该循环里有一支因子即以此
    「将其余因子**从演算中剔除**…被标记为**嵌合行为的默认值**，在后续循环中应用」
    （具体编号留在 `docs/wiki/biligame.md`，引擎侧只写循环次第）。

    引擎里的落法（**有界、不碰席位**）：
      · 主导者 = 当下【人丁最盛】的那一支因子（纯统计，不点名）；
      · 协议内容 = `annex.factor` + `annex.span_ratio`，写进 `st.overrides` —— 那是【账本】，
        跨轮回不回滚，于是它真的「成为后续的默认值」；
      · 后果 = 非嵌合因子的个体寿命上限被压到 `life_span × span_ratio`：它们更早退出演算
        （「从演算中剔除」），世界因此更靠近 `OP_SOLVE_DESTRUCTION` 那一侧；
      · **只嵌合一次**：协议写定便不再改 —— 与"成为默认值"同义。

    刻意**不碰** `st.suppressed`：压制席位会让「十二席都有人」永远差一步，
    而那正是 plot 在 42000 帧刻意制造的永劫回归 —— 见设计稿 §D2 的冲突分析。
    """

    name = "OP_ANNEX"

    def apply(self, st, ctx, rng, frame):
        if not st.gate(self.name):
            return st
        if "annex.factor" in st.overrides:          # 只嵌合一次
            return st
        idx = st.pool.index()
        if idx.size == 0:
            return st
        counts = np.bincount(st.pool.factor[idx], minlength=st.dim)
        st.overrides["annex.factor"] = int(np.argmax(counts))
        st.overrides["annex.span_ratio"] = float(
            ctx.params.get("annex_span_ratio", 0.8))
        st.add_score("embedded_protocol")
        return st


class Repopulate(Operator):
    """补种：十二因子是结构性的，世界持续为每一支产出候选，不让任何一支断绝。

    未开启记忆继承时是随机新生；开启后由上一代的记忆衍生。
    无论哪种，新生都归入【人丁最单薄的那一支因子】—— 于是每一席永远有本因子的人可担。
    """

    name = "OP_REPOPULATE"

    def apply(self, st, ctx, rng, frame):
        p = ctx.params
        dim = st.dim
        alive = st.pool.index()
        alive_f = (np.bincount(st.pool.factor[alive], minlength=dim).astype(int)
                   if alive.size else np.zeros(dim, dtype=int))
        floor = int(p.get("min_factor_cohort", 2))
        need = max(int(p["min_population"]) - len(st.pool),
                   int((alive_f < floor).sum()))
        if need <= 0:
            return st
        ever = np.flatnonzero(st.pool.born > 0)
        dead = [i for i in ever if not st.pool.alive[i]]
        inherit = st.gate(MEMORY_INHERIT_GATE)

        for _ in range(need):
            i = st.pool.alloc()
            if i < 0:
                break
            st.pool.born[i] = frame
            f = int(np.argmin(alive_f))                  # 先顾人丁最单薄的那一支
            kin = [k for k in dead if int(st.pool.factor[k]) == f]
            if inherit and kin:
                parent = int(kin[int(rng.integers(len(kin)))])
                base = st.pool.mem[parent] if st.pool.has_mem[parent] else st.pool.vec[parent]
                v = base + rng.normal(0.0, p["inherit_mutation"], dim).astype(np.float32)
                st.pool.mem[i] = base.copy()
                st.pool.has_mem[i] = True
                st.add_score("born_inherited")
            else:
                alpha = np.full(dim, float(ctx.seeding["alpha"]), dtype=np.float32)
                alpha[f] = 6.0                           # 本支的样本天然偏向自己的因子
                v = rng.dirichlet(alpha).astype(np.float32)
                st.add_score("born_random")
            np.clip(v, 0.0, None, out=v)
            total = float(v.sum()) or 1.0
            st.pool.vec[i] = (v / total).astype(np.float32)
            st.pool.factor[i] = f
            st.born(frame, i)
            alive_f[f] += 1
        return st


class Bifurcate(Operator):
    """分化：保证每个位都同时存在「拥趸」与「对抗者」。通用遍历，不点名。"""

    name = "OP_BIFURCATE"

    def apply(self, st, ctx, rng, frame):
        if not st.gate(self.name):
            return st
        dim = st.dim
        idx = st.pool.index()
        if idx.size == 0:
            return st
        v = st.pool.vec[idx]
        home = st.pool.factor[idx]          # 原生因子（出生即定），不用当场的最强维
        away = np.argmin(v, axis=1)
        for i in range(dim):
            if not np.any(home == i):
                _spawn_biased(st, ctx, rng, frame, i, +1.0)
                st.add_score("bifurcated_for")
            if not np.any(away == i):
                _spawn_biased(st, ctx, rng, frame, i, -1.0)
                st.add_score("bifurcated_against")
        return st


def _spawn_biased(st, ctx, rng, frame, dim_index, sign):
    i = st.pool.alloc()
    if i < 0:
        return
    dim = st.dim
    alpha = np.full(dim, 0.12, dtype=np.float32)
    alpha[dim_index] = 6.0 if sign > 0 else 0.02
    v = rng.dirichlet(alpha).astype(np.float32)
    st.pool.vec[i] = (v / float(v.sum())).astype(np.float32)
    st.pool.factor[i] = int(np.argmax(st.pool.vec[i]))
    st.pool.born[i] = frame
    st.born(frame, i)
    st.add_score("spawned_biased")


class Capability(Operator):
    """能力涌现：任何个体的倾向长期极端化，就会凝结成「能力」。"""

    name = "OP_CAPABILITY"

    def apply(self, st, ctx, rng, frame):
        p = ctx.params
        names = p["capability_names"]
        idx = st.pool.index()
        if idx.size == 0:
            return st
        v = st.pool.vec[idx]
        # 一次算完全体的越阈掩码，只对通过的 (个体, 维) 逐对登记 —— 原先每一维各扫
        # 一遍（12 次 flatnonzero），等价但把整个池多扫了十几遍。集合登记与计数都与
        # 遍历次序无关（每个键加的都是整数次 1.0），故逐位不变。
        rows, dims = np.nonzero(v >= p["tau_capability"])
        for r, dim in zip(rows.tolist(), dims.tolist()):
            cname = names[dim]
            if not cname:
                continue
            pi = int(idx[r])
            tag = "capability:" + cname
            if tag not in st.pool.tags[pi]:
                st.pool.tags[pi].add(tag)
                st.add_score("cap_" + cname)
        return st


class Entropy(Operator):
    """熵：由噪声、死亡与分歧共同驱动。溢出噪声会在这里完成反馈。"""

    name = "OP_ENTROPY"

    def apply(self, st, ctx, rng, frame):
        p = ctx.params
        n = max(len(st.pool), 1)
        rate = st.death_events / n
        idx = st.pool.index()
        disp = 0.0
        if idx.size > 1:
            v = st.pool.vec[idx]
            disp = float(np.mean(np.std(v, axis=0))) / 0.15
        target = st.noise * 2.0 + rate + 0.4 * min(disp, 2.0) + float(p.get("disorder", 0.0))
        a = p["entropy_mix"]
        st.entropy = (1.0 - a) * st.entropy + a * target
        st.noise *= p["noise_decay"]
        st.death_events = 0
        st.add_score("entropy_sum", st.entropy)
        return st


class Domain(Operator):
    """初始变量的推进：每一档【跑满自己的帧预算】才换下一档。

    这正是「无机 → 有机 → 人类」的来源——枚举域上的取值推进，不是剧本。
    预算由 `domain_dwell` 给出，且可**逐档覆盖**（写进 `stages[i].params`，
    经 `StageCtx` 生效）——于是「阶段三远长于阶段一」这类口径只需配置表达。

    历史上这里还有第二条通路「该取值已被证伪 ⇒ 立刻换档」。它的后果是：探针一旦
    提前证伪，阶段就提前收尾 —— 实测中阶段二只跑了 301 帧、阶段三只跑了 **1 帧**，
    机制根本来不及起作用（"人类演算期"成了一个瞬时事件）。故改为**按预算**：
    每档跑满才换，与 wiki「各阶段跑到它的循环数才结束」一致。
    `progress` / `tau_falsify` 回到它本来的岗位 —— 只判裁决，不管换档
    （见 apps/verdicts.py 的 `all_falsified`）。
    """

    name = "OP_DOMAIN"

    def apply(self, st, ctx, rng, frame):
        p = ctx.params
        if st.domains_exhausted:
            return st
        st.domain_dwell += 1
        if st.domain_dwell < p["domain_dwell"]:
            return st                                  # 这一档的预算还没跑满
        st.domain_dwell = 0
        if st.domain_index < len(st.domain) - 1:
            st.domain_index += 1
            st.add_score("domain_advance")
        else:
            st.domains_exhausted = True
            st.add_score("domains_exhausted")
        return st


def _pilgrimage(st, frame):
    """逐火：世代之内的夺席 —— 本世的承位者顶掉上一世留下的那些在位者。

    只夺【上一世留下的】那几席 —— 判据是承位那一刻的 world_clock：若现任本就是本世
    承的位，他就是本世的承位者，不必再夺（末次再创世前那十二位正属此列）。
    夺席【不清空】：退位者陨落，接手者当场落座，故不会出现「失位、被留在空缺上」。
    接手者取【本因子中尚未承过位的最强者】—— 逐火之旅换的是新人，不是同一批人。
    被外部压制的席不在此列：那是轮回的开口。

    这里也是引擎里**唯一**真实的「传承关系」来源：退位者陨落（墓碑记 `dethroned`），
    接手者记下自己是从谁手里接的这一席（`inherit`）。
    """
    idx = st.pool.index()
    if idx.size == 0:
        return
    v = st.pool.vec[idx]
    fit = st.pool.fitness[idx]
    serials = st.pool.serial[idx]
    home = st.pool.factor[idx]
    held = st.pool.held[idx]
    for i, slot in enumerate(st.register.slots):
        if slot.owner is None or i in st.suppressed:
            continue
        k = st.pool.index_of_serial(int(slot.owner))
        if k < 0:
            continue
        if int(st.pool.seated_clock[k]) == st.world_clock:
            continue                       # 本世已承位 —— 他就是本世的承位者
        same = np.flatnonzero((home == i) & (~held))      # 同因子、且从未承过位者
        if same.size == 0:
            continue
        score = v[same, i] * fit[same]
        j = int(np.argmax(score))
        st.pool.kill(k)                                    # 弑：退位者陨落
        st.bury(frame, k, "dethroned")
        st.death_events += 1
        st.add_score("deaths_slain")
        st.inherit(int(serials[same[j]]), int(slot.owner))
        slot.owner = int(serials[same[j]])
        slot.value = float(score[j])
        slot.vector = v[same[j]].copy()
        st.pool.held[idx[same[j]]] = True
        # 记【承位这一刻所在的那一世】（world_clock 随即 +1）：于是他在下一世登位，
        # 而「本世已承位」的判据只护他这一轮 —— 此后每世都会再换一批新人。
        st.pool.seated_clock[idx[same[j]]] = st.world_clock
        st.add_score("pilgrimage")


def _rule_source(st, slot):
    """主动更替的规则来源：**决策账本**。

    取主导支（写下协议那支）在当前池中的集体形态，按共识占比 `renewal.share` 与
    席位向量加权：共识越高，下一世的规则越由"电信号的决策"给出；占比很低（或池空、
    或那支已散尽）时退回席位向量 —— 也就是退回自动更替的老路。

    它写进 `rule_matrix` / `observables_vec`（世界规则与观测量），**不参与演化** ——
    故这道改造不改变轨迹，效果在报告与看板的「世界规则 · 观测量」里看。
    """
    idx = st.pool.index()
    factor = st.overrides.get("renewal.factor")
    share = float(st.overrides.get("renewal.share", 0.0) or 0.0)
    if idx.size == 0 or factor is None or share <= 0.0:
        return slot.vector
    same = idx[st.pool.factor[idx] == int(factor)]
    if same.size == 0:
        return slot.vector
    mean = st.pool.vec[same].mean(axis=0)
    return (share * mean + (1.0 - share) * slot.vector).astype(np.float32)


def consensus(st):
    """决策共识：主导支在池内占住多少。**只读**，不改一个比特。

    `共识 = 主导支池内占比` ∈ [0,1] —— 池子越聚在一支上，共识越高。它是「主动更替」
    的换代门槛：主动更替不再只看"十二席齐备"，还要这份决策共识到位
    （见 `Promotion.apply`）。报告与看板也拿它当读数。

    初版还乘了一个「主导支平均稳定度 / tau_stable」的因子，但实测那个因子对世界
    **高度敏感**：高噪声的淹没那么世界里个体几乎从不连续稳定 ⇒ 因子恒≈0 ⇒ 共识恒≈0
    ⇒ 阶段三之后换代被彻底按死、连死循环都提前。故只保留占比这一维 —— 门槛才在不同
    世界之间可比（各世界的占比分布都在 0.09～0.14）。
    """
    idx = st.pool.index()
    if idx.size == 0:
        return 0.0
    counts = np.bincount(st.pool.factor[idx], minlength=st.dim)
    return float(counts.max()) / float(idx.size)


class Promotion(Operator):
    """世代更迭（**自动**更替循环）：寄存器齐全时，把每个槽位升格为下一轮的世界规则。

    它是【世界的基础动力学】，**自始常开**、不受阶段门控 —— 十二席齐备即换代，
    个体不"决定"任何事。考据（biligame 第 564 行）：第 19110218 次循环「基于
    **决策数据**，将**自动更替循环**修改为电信号**主动**更替，进行「再创世」」
    —— 也就是说**更替循环自始就有（就是本算子）**，「再创世」是阶段三把它改成
    "主动"之后的说法。那道"主动"的改造由 `ActiveRenewal` 落地。

    换代条件分两层（这正是"自动 / 主动"的分界）：
      · **自动**（阶段一 / 二，`renewal.mode` 未写）：十二席齐备 + `promotion_dwell`
        帧稳定，即换代；
      · **主动**（阶段三起，`active`）：在此之上还要**决策共识**达成 ——
        `consensus(st)` ≥ `renewal_consensus`。共识不到位就继续等，本世的更替延后。
        但【外部】把再创世的逻辑整个覆写掉（`promotion.mode` → `memory_converge`）
        之后，换代归那套新逻辑管，这道内部共识门不再适用。

    死循环不是它被关掉造成的，而是某个位【永远填不满】造成的。
    """

    name = "OP_PROMOTION"

    def apply(self, st, ctx, rng, frame):
        if getattr(st, "seats_frozen", False):
            return st
        p = ctx.params
        if st.promotion_cooldown > 0:
            st.promotion_cooldown -= 1
            return st

        # 规则覆盖表：再创世的逻辑可被覆写。默认是【原位升格】；
        # 被覆写成 memory_converge 后，空缺的席不再等本世的人来补，
        # 而是【以记忆再造】—— 并解除那一席身上的压制（记忆覆写了压制）。
        mode = str(st.overrides.get("promotion.mode", "in_place_upgrade"))
        if mode == "memory_converge" and st.memory_bank.shape[0]:
            for i in st.register.vacant():
                mean_vec = st.memory_bank.mean(axis=0)
                st.register.slots[i].vector = mean_vec.copy()
                st.register.slots[i].value = float(mean_vec.max())
                st.register.slots[i].owner = MEMORY_OWNER
                st.suppressed.discard(i)
                st.add_score("memory_repaired")

        if not st.register.complete():
            st.promotion_dwell = 0
            return st

        # 主动更替的触发门：换代还要【决策共识】达成（主导支在池内占住多数）。
        # 自动更替（阶段一 / 二）不看这道门 —— 它自始就是"十二席齐备即换代"。
        #
        # 门只管【原位升格】那套换代。再创世的逻辑一旦被【外部】协议整个覆写
        # （`promotion.mode` → `memory_converge`），换代就归那套新逻辑管了 ——
        # 它由记忆补席、不等池内共识。共识门是"主动更替"这套内部逻辑的产物，
        # 被覆写之后不再适用（否则那道外生覆写会被自己的门槛挡在门外）。
        active = (str(st.overrides.get("renewal.mode", "")) == DECISION_LEDGER
                  and mode == "in_place_upgrade")
        if active and consensus(st) < float(p["renewal_consensus"]):
            st.promotion_dwell = 0
            return st

        # 权柄账本：被外生力量夺走权柄的世界**更难走到终点** —— 每被夺一次，再创世
        # 就要多等 `ember_delay` 帧。没有逐出类投递的世界（如 plot）该值为 0，
        # 故**逐帧不变**；只有「血战」式的世界会真的被推远。
        need = float(p["promotion_dwell"]) + float(p.get("ember_delay", 0.0)) \
            * float(st.score.get("embers_taken", 0.0))
        st.promotion_dwell += 1
        if st.promotion_dwell < need:
            return st

        # 逐火：本世的承位者自【上一世留下的在位者】手里夺席（先夺席，才谈再创世）。
        _pilgrimage(st, frame)

        # 原位升格：现任的位格【保留席位】，只把这一世的规则与容量升格给下一世。
        # 本世的在位者本就是上一世的承位者升上来的，不该先被清空、再让别人来顶。
        #
        # 规则【从哪来】分两种（这正是"自动 / 主动"的分界，故这里只有这一个分支）：
        #   自动 ⇒ 席位向量（`slot.vector`）
        #   主动 ⇒ 决策账本（见 `_rule_source`：主导支的集体形态 × 共识占比）
        for i, slot in enumerate(st.register.slots):          # 遍历，不点名
            src = _rule_source(st, slot) if active else slot.vector
            st.rule_matrix[i] = src * p["promotion_gain"]
            st.observables_vec = st.observables_vec + st.rule_matrix[i] @ ctx.mapping
            st.loci[i].capacity *= p["capacity_inherit"]

        st.round += 1
        st.promotions += 1
        st.world_clock += 1
        st.promotion_dwell = 0
        st.promotion_cooldown = int(p["promotion_cooldown"])
        # 常规轮：本世十二位齐备即为「满」—— 账本回到满值。
        # 死循环期不再有再创世，这个值便只增不减（见 core 的尝试落点）。
        st.seeds = len(st.register.slots)
        st.add_score("promotion")
        if mode == "memory_converge" or st.solver == "OP_MEMORY_CONVERGE":
            st.converged = True
            st.add_score("converged")
        return st


class ActiveRenewal(Operator):
    """主动更替（再创世）：把换代的【规则来源】从席位向量改成【决策账本】。

    考据（biligame 第 564 行）：第 19110218 次循环「基于**决策数据**，将**自动更替
    循环**修改为电信号**主动**更替，进行「再创世」」—— 该次循环正落在**阶段三**
    区间内，故本机制由阶段三装配（`genesis.domain.stages[2].on`）。

    与 `Promotion` 的分工：
      · `Promotion` = **自动**更替循环（十二席齐备即换代），自始常开；
      · 本算子 = 那道"**改成主动**"的改造 —— 它只把「换代时把什么当成下一世的规则」
        从席位向量换成决策账本（见 `_rule_source`）。
        写下的四条都是**标量**，进 `overrides` 账本（不回滚）：`renewal.mode` /
        `renewal.factor`（主导支）/ `renewal.share`（共识占比）/ `renewal.ledger_size`
        （写下时账本里已有多少条协议）。

    **它不改动力学**：`rule_matrix` / `observables_vec` 不参与演化，也不进
    `digest()` / `world_signature()` ⇒ 轨迹与指纹一个都不动；这道改造要在报告与看板
    的「世界规则 · 观测量」里看。
    """

    name = "OP_ACTIVE_RENEWAL"

    def apply(self, st, ctx, rng, frame):
        if not st.gate(self.name):
            return st
        if "renewal.mode" in st.overrides:          # 只确立一次（账本不回滚）
            return st
        idx = st.pool.index()
        if idx.size == 0:
            return st
        counts = np.bincount(st.pool.factor[idx], minlength=st.dim)
        lead = int(np.argmax(counts))
        st.overrides["renewal.mode"] = DECISION_LEDGER
        st.overrides["renewal.factor"] = lead
        st.overrides["renewal.share"] = float(counts[lead]) / float(idx.size)
        st.overrides["renewal.ledger_size"] = len(st.overrides)
        st.add_score("active_renewal")
        return st


def meta_indices(st) -> list:
    """结构上标了 meta 的席位（通常只有一位）。canonical 世界为空。"""
    return [i for i, l in enumerate(st.loci) if getattr(l, "meta", False)]


def seat_index(st, locus_id) -> int:
    """位名 → 位次。认不出来返回 -1（不猜）。"""
    for i, l in enumerate(st.loci):
        if str(l.id) == str(locus_id):
            return i
    return -1


def _seat_holders(st) -> set:
    """当前由【池内活体】占着的编号。外生占位（负号）不算候选。"""
    return {int(s.owner) for s in st.register.slots
            if s.owner is not None and int(s.owner) >= 0}


def mean_seat_vector(st, exclude=()) -> np.ndarray:
    """非 meta、已填充席位的均值向量。没有可用席位时返回零向量。"""
    vecs = [np.asarray(s.vector, dtype=np.float32)
            for i, s in enumerate(st.register.slots)
            if s.filled() and not s.meta and i not in exclude]
    if not vecs:
        return np.zeros(int(st.dim), dtype=np.float32)
    return np.stack(vecs).mean(axis=0).astype(np.float32)


def memory_row_vec(st, i: int) -> np.ndarray:
    """第 i 席该用的那行记忆：十二因子数据齐全时用自己的行，否则退回均值。"""
    i = int(i)
    rows = int(getattr(st.origin, "factor_rows", 0))
    if rows > 0 and st.memory_bank.shape[0] >= rows and 0 <= i < rows:
        return np.asarray(st.memory_bank[i], dtype=np.float32)
    if st.memory_bank.shape[0]:
        return st.memory_bank.mean(axis=0).astype(np.float32)
    return mean_seat_vector(st, exclude=(i,))


def external_slots(st):
    """场上由【外部变量】（负编号的场外参与者）占着的席位。记忆承载（-1）不算。"""
    return [(i, s) for i, s in enumerate(st.register.slots)
            if s.owner is not None and int(s.owner) < 0
            and int(s.owner) != MEMORY_OWNER]


def host_slot(st, serial) -> int:
    """某个编号（可以是池外的负编号）此刻占着哪一席；没有则 -1。

    `MEMORY_OWNER`（-1）是「无人 / 由记忆承载」的哨兵，不算一个宿主。
    """
    if serial is None:
        return -1
    s = int(serial)
    if s >= 0 or s == MEMORY_OWNER:
        return -1
    for i, slot in enumerate(st.register.slots):
        if slot.owner is not None and int(slot.owner) == s:
            return int(i)
    return -1


def host_present(st, serial) -> bool:
    if serial is None:
        return False
    s = int(serial)
    if s == MEMORY_OWNER:
        return False
    if s >= 0:
        return st.pool.index_of_serial(s) >= 0
    return host_slot(st, s) >= 0


def held_slot(st, serial) -> int:
    """池内编号此刻占着哪一席；没有则 -1。"""
    if serial is None or int(serial) < 0:
        return -1
    s = int(serial)
    for i, slot in enumerate(st.register.slots):
        if slot.owner is not None and int(slot.owner) == s:
            return int(i)
    return -1


def lift_selfhood(st, mi: int, magnitude: float) -> bool:
    """把原初在位者的原初分量抬高一点（记忆片段 effect=selfhood 的真实作用）。"""
    mi = int(mi)
    if mi < 0 or mi >= len(st.register.slots):
        return False
    slot = st.register.slots[mi]
    if not slot.filled():
        return False
    owner = int(slot.owner)
    if owner >= 0:
        k = st.pool.index_of_serial(owner)
        if k < 0:
            return False
        v = st.pool.vec[k].copy()
        v[mi] = min(0.95, float(v[mi]) + float(magnitude))
        total = float(v.sum())
        if total <= 0.0:
            return False
        v = (v / total).astype(np.float32)
        st.pool.vec[k] = v
        slot.vector = v.copy()
        slot.value = float(st.pool.vec[k, mi] * st.pool.fitness[k])
        return True
    v = np.asarray(slot.vector, dtype=np.float32).copy()
    v[mi] = min(0.95, float(v[mi]) + float(magnitude))
    total = float(v.sum())
    if total <= 0.0:
        return False
    v = (v / total).astype(np.float32)
    slot.vector = v
    slot.value = float(v.max())
    return True


def apply_memory_effect(st, o, effect, mag, hk, hi, mi, frame, params, cap) -> bool:
    """把一段记忆 effect 真实作用到世界（宿主 / 原初 / 全局窗口）。"""
    effect = str(effect)
    mag = float(mag)
    if effect in ("fitness", "support"):
        if hk >= 0:
            st.pool.fitness[hk] = min(10.0, float(st.pool.fitness[hk]) + mag)
            return True
        if hi >= 0:
            slot_h = st.register.slots[hi]
            slot_h.value = min(10.0, float(slot_h.value) + mag)
            return True
        return False
    if effect == "energy":
        o.energy = min(cap, o.energy + mag)
        return True
    if effect == "selfhood":
        return lift_selfhood(st, mi, mag)
    if effect == "coupling":
        until = int(frame) + int(params.get("origin_memory_window", 256))
        o.memory_coupling_until = max(int(o.memory_coupling_until), until)
        o.memory_coupling_gain = max(float(o.memory_coupling_gain), mag)
        return True
    if effect == "mutation":
        until = int(frame) + int(params.get("origin_memory_window", 256))
        o.memory_mutation_until = max(int(o.memory_mutation_until), until)
        o.memory_mutation_damp = max(float(o.memory_mutation_damp), mag)
        return True
    if effect in ("memory_seat", "rebind"):
        seat = hi if hi >= 0 else held_slot(st, int(o.companion_host))
        if seat >= 0:
            st.memory_seats.add(int(seat))
            return True
    return False


def pick_host(st, exclude_serial=-1) -> int:
    """忆灵的依附对象：非 meta 席上承载量最高的在位者（确定性，平手按编号）。

    外部变量（负编号）也可以成为依附对象 —— 「伴生体依附外部变量」就靠这一条。
    """
    best, best_val = -1, float("-inf")
    for slot in st.register.slots:
        if getattr(slot, "meta", False) or not slot.filled():
            continue
        owner = int(slot.owner)
        if owner == MEMORY_OWNER or owner == int(exclude_serial):
            continue
        val = float(slot.value)
        if val > best_val or (val == best_val and (best == -1 or owner < best)):
            best, best_val = owner, val
    return best


class Paths(Operator):
    """命途：个体走上一条持久的相性轴，漂移、代价与背离都真的发生。

    数据来自 `config/paths.json`（可选的权柄层）：
      · `axis` 是这条命途占哪几席的因子；`affinity` = 个体向量在这几席上的份额。
      · 越过 `join_threshold` 就走上去；跌到 `leave_threshold` 以下连续
        `defect_dwell` 次即背离。
      · 走上之后每 `period` 帧结算一次：漂移朝这条轴偏一点（`bias`），
        并付一次行路代价（扣支持度 `price`）。

    canonical 世界没有 `paths.json`，pipeline 里也没有这个算子 —— 行为逐位不变。
    """

    name = "OP_PATH"

    def apply(self, st, ctx, rng, frame):
        conf = getattr(ctx, "paths", None)
        if not conf or not conf.get("enabled", False):
            return st
        period = max(1, int(conf.get("period", 16)))
        if int(frame) % period != 0:
            return st
        plist = conf.get("paths") or []
        if not plist:
            return st
        idx = st.pool.index()
        if idx.size == 0:
            return st
        axes = [np.asarray([int(i) for i in (p.get("axis") or [])],
                           dtype=np.int64) for p in plist]
        ids = [str(p.get("id")) for p in plist]
        V = st.pool.vec[idx]
        shares = np.stack([V[:, ax].sum(axis=1) for ax in axes], axis=1)
        best = shares.argmax(axis=1)
        bestv = shares.max(axis=1)
        serials = st.pool.serial[idx]
        join = float(conf.get("join_threshold", 0.45))
        leave = float(conf.get("leave_threshold", 0.30))
        dwell = max(1, int(conf.get("defect_dwell", 4)))
        bias = float(conf.get("bias", 0.04))
        price = float(conf.get("price", 0.15))

        # 1) 走上命途
        for k in np.flatnonzero(bestv >= join):
            s = int(serials[k])
            if s in st.paths:
                continue
            st.paths[s] = {"id": ids[int(best[k])],
                           "affinity": float(bestv[k]),
                           "joined": int(frame), "low": 0}
            st.add_score("path_joined")
            st.score["emitted_path_joined"] = float(frame)

        # 2) 亲和更新 / 背离判定（只有成员进这段）
        #    亲和只看【它自己那条命途】的份额 —— 换一条更强的轴不等于背离，
        #    但也不许悄悄改换门庭。
        pid_index = {pid: j for j, pid in enumerate(ids)}
        members, member_paths, member_serials, member_ids = [], [], [], []
        for k in range(idx.size):
            s = int(serials[k])
            cur = st.paths.get(s)
            if cur is None:
                continue
            pj = pid_index.get(str(cur.get("id")), -1)
            aff = float(shares[k, pj]) if pj >= 0 else 0.0
            a = dict(cur)
            a["affinity"] = aff
            if aff < leave:
                a["low"] = int(a.get("low", 0)) + 1
                if a["low"] >= dwell:
                    del st.paths[s]
                    st.add_score("path_defected")
                    st.score["emitted_path_defected"] = float(frame)
                    # 背离命途的令使会被当场收回权柄。
                    g = st.grants.get(s)
                    if g and str(g.get("path")) == str(cur.get("id")):
                        del st.grants[s]
                        st.score["emitted_path_revoked"] = float(frame)
                        st.add_score("path_revoked")
                    continue
            else:
                a["low"] = 0
            st.paths[s] = a
            members.append(int(idx[k]))
            member_paths.append(pj if pj >= 0 else int(best[k]))
            member_serials.append(s)
            member_ids.append(str(cur.get("id")))

        # 3) 行路：把分量朝这条轴【聚拢】（不是摊平）+ 付一次代价
        if members:
            mk = np.asarray(members, dtype=np.int64)
            mp = np.asarray(member_paths, dtype=np.int64)
            mask = np.zeros((len(plist), int(st.dim)), dtype=bool)
            for j, ax in enumerate(axes):
                mask[j, ax] = True
            # 令使走得更稳：聚拢加倍、行路代价减半。
            grants = getattr(st, "grants", {}) or {}
            boost = np.ones(len(members), dtype=np.float32)
            for j, s in enumerate(member_serials):
                g = grants.get(int(s))
                if g and str(g.get("path")) == member_ids[j]:
                    boost[j] = 2.0
            v = np.array(st.pool.vec[mk], dtype=np.float32)
            inside = v * mask[mp]
            total_in = inside.sum(axis=1, keepdims=True)
            total_in[total_in <= 0.0] = 1.0
            b = (bias * boost)[:, None]
            v = (1.0 - b) * v + b * (inside / total_in)
            total = v.sum(axis=1, keepdims=True)
            total[total <= 0.0] = 1.0
            st.pool.vec[mk] = (v / total).astype(np.float32)
            st.pool.support[mk] = np.maximum(
                0.0, st.pool.support[mk] - price / boost)

        # 3b) 场外令使：它坐着的那一席也随命途聚拢（每结算一次，幅度是一半）
        grants = getattr(st, "grants", {}) or {}
        for s, g in list(grants.items()):
            if int(s) >= 0:
                continue
            hi = host_slot(st, int(s))
            pj = pid_index.get(str(g.get("path")), -1)
            if hi < 0 or pj < 0:
                continue
            slot = st.register.slots[hi]
            v = np.asarray(slot.vector, dtype=np.float32)
            m = np.zeros(int(st.dim), dtype=bool)
            m[axes[pj]] = True
            inside = v * m
            total_in = float(inside.sum())
            if float(v.sum()) <= 0.0 or total_in <= 0.0:
                continue
            b = bias * 0.5
            v2 = (1.0 - b) * v + b * (inside / total_in)
            v2 = v2 / max(float(v2.sum()), 1e-9)
            slot.vector = v2.astype(np.float32)

        # 4) 死者留下的命途 / 令使记录清掉（槽位会被复用，编号不会）
        live = {int(s) for s in serials}
        for s in [s for s in st.paths if s not in live]:
            del st.paths[s]
        for s in [s for s in grants if int(s) >= 0 and int(s) not in live]:
            del grants[s]
        return st


def pick_candidate(st, seat: int, mean_vec) -> int:
    """为某一席挑一个真实个体：优先同因子，再取向量最接近席位均值者。

    纯函数式选择（距离 → 编号），不掷骰子 —— 同状态必然挑到同一个体。
    返回池中下标；找不到返回 -1。
    """
    idx = st.pool.index()
    if idx.size == 0:
        return -1
    busy = _seat_holders(st)
    free = [int(k) for k in idx if int(st.pool.serial[k]) not in busy]
    if not free:
        return -1
    same = [k for k in free if int(st.pool.factor[k]) == int(seat)]
    pool = same or free
    vecs = st.pool.vec[pool]
    d = np.linalg.norm(vecs - mean_vec.reshape(1, -1), axis=1)
    # 先按距离、再按编号：距离相同（或极近）时也有确定次序。
    order = sorted(range(len(pool)),
                   key=lambda j: (round(float(d[j]), 12),
                                  int(st.pool.serial[pool[j]])))
    return int(pool[order[0]])


class Decide(Operator):
    """具名因子的决定：知道得够多之后，他们自己动手制造那个漏洞。

    它只读【账本】里的 `factor_ledger`（谁、知道什么、有多确定），写【世界】里的
    `factor_intent` 并压住配置指定的那一席。外部的提示只提高 certainty；
    真正的决定发生在这里 —— 所以「他说了几句话，世界就变了」是可拆开验证的。

    没配 `decision.json`（canonical / origin 的其它预设）⇒ 整个算子一步不走。
    """

    name = "OP_DECIDE"

    def apply(self, st, ctx, rng, frame):
        conf = getattr(ctx, "decision", None)
        if not conf or not conf.get("enabled", False):
            return st
        # 知道得早，不等于当场动手：真相轮的那个时刻才做决定。
        if int(frame) < int(conf.get("decision_frame", 0)):
            return st
        th = float(conf.get("certainty_threshold", 0.5))
        seat = conf.get("loophole_seat")
        for role, rec in st.factor_ledger.items():
            if float(rec.get("certainty", 0.0)) < th:
                continue
            if st.factor_intent.get(role) != "prevent_recreation":
                st.factor_intent[role] = "prevent_recreation"
                st.score["emitted_factor_decision"] = float(frame)
                st.add_score("factor_decided")
            if seat is not None and int(seat) not in st.suppressed:
                st.suppressed.add(int(seat))
                st.score["emitted_years_loophole"] = float(frame)
                st.add_score("years_loophole")
        return st


class Origin(Operator):
    """原初（第十三席）的真实动力学。

    这一席不是特殊 owner：它和别的席一样由 `OP_OCCUPY` 让因子对得上的个体来坐。
    本算子只做四件事：

      · **自我**：读在位者向量的原初分量占比（`selfhood = v[m] / sum(v)`），
        越过 `tau_origin` 即「成形」，能量按 `origin_gain × selfhood` 累积并逐帧衰减；
        连续 `origin_dissolve_dwell` 帧低于 `tau_origin_low` ⇒ 离位（自我消散）。
      · **创世**：能量 ≥ `origin_create_cost` 且某个非 meta 席空缺 ⇒ 补一个真实个体
        （确定性地取同因子、向量最接近席位均值者）。
      · **爱**：能量 ≥ `origin_love_cost` ⇒ 打开 `origin_love_duration` 帧的时间窗，
        `Drift` 真读它（耦合变紧 / 变异变小）。
      · **开拓**：结构连续 `origin_trailblaze_dwell` 帧不推进且能量足够 ⇒ 内生地
        拨动演算方向、并打开一道登记过的门（破停滞的尝试）。

    没有 meta 席的世界里它一帧都不做事（canonical 的 pipeline 也没有它）。
    """

    name = "OP_ORIGIN"

    def apply(self, st, ctx, rng, frame):
        meta = meta_indices(st)
        if not meta:
            return st
        p = ctx.params
        o = st.origin
        mi = int(meta[0])
        slot = st.register.slots[mi]
        tau = float(p.get("tau_origin", 0.12))
        tau_low = float(p.get("tau_origin_low", 0.05))
        gain = float(p.get("origin_gain", 0.2))
        decay = float(p.get("origin_decay", 0.002))
        cap = float(p.get("origin_energy_cap", 50.0))

        # ---- 外部变量共鸣 ---------------------------------------------------
        # 场外参与者（负编号）带着自己的属性向量进入演算；若它与原初/记忆共鸣，
        # 沉睡中的原初会被它唤醒 —— 「外部变量到来 → 原初苏醒」落在这里。
        thr = float(p.get("origin_resonance_threshold", 0.75))
        if slot.filled() and float(slot.vector.sum()) > 0.0:
            ref = np.asarray(slot.vector, dtype=np.float32)
        elif o.seed_vector is not None:
            ref = np.asarray(o.seed_vector, dtype=np.float32)
        elif st.memory_bank.shape[0]:
            ref = st.memory_bank.mean(axis=0).astype(np.float32)
        else:
            ref = None
        res, rh = 0.0, -1
        if ref is not None:
            na = float(np.linalg.norm(ref))
            if na > 0.0:
                for _i, _s in external_slots(st):
                    v = np.asarray(_s.vector, dtype=np.float32)
                    nb = float(np.linalg.norm(v))
                    if nb <= 0.0:
                        continue
                    c = float(np.dot(ref, v) / (na * nb))
                    if c > res:
                        res, rh = c, int(_s.owner)
        # 共鸣一旦建立就【保持】：属性向量会随演化漂移，但「外部变量与记忆的
        # 那条线」不该每帧断一次。只有外部变量真的离场时才解除。
        o.resonance = max(float(o.resonance), float(res))
        if res >= thr and rh != -1:
            o.resonance_host = int(rh)
            if not o.resonated:
                o.resonated = True
                st.add_score("origin_resonance")
            if not o.awake:
                o.awake = True
                o.form = max(int(o.form), 1)
                st.add_score("origin_resonance_wake")
        elif int(o.resonance_host) != -1 and not host_present(
                st, int(o.resonance_host)):
            o.resonance_host = -1

        # ---- 沉睡 / 苏醒 ---------------------------------------------------
        # 原初可以先占着席位却【不成形】：在 `origin_auto_wake_frame` 之前（或外部
        # `wake_origin` 锚点到达之前），自我度不累积、能量归零。这对应「原初
        # 遭受污染陷入长眠，直到外部变量干涉才苏醒」。
        if not o.awake:
            auto = int(p.get("origin_auto_wake_frame", -1))
            if auto >= 0 and int(frame) >= auto:
                o.awake = True
                o.form = max(int(o.form), 1)
                st.add_score("origin_awaken")
            else:
                o.form = 0
                o.filled = False
                o.selfhood = 0.0
                o.age = 0
                o.energy = max(0.0, o.energy * (1.0 - decay))
                o.dissolve_run = 0
                return st
        if int(o.form) < 1:
            o.form = 1
        # 记忆片段会过期；过期的片段不再被读取 / 转印。
        if o.memory_fragments:
            o.memory_fragments = [f for f in o.memory_fragments
                                  if f.active(int(frame))]

        # 十二因子数据的【覆盖率】：只有 factor_basis 写入过才算数。
        n_non_meta = sum(1 for l in st.loci if not getattr(l, "meta", False)) or 1
        o.coverage = min(1.0, float(o.factor_rows) / float(n_non_meta))
        mem_w = float(p.get("origin_memory_gain", 0.5))
        gain_eff = gain * ((1.0 - mem_w) + mem_w * float(o.coverage))

        # ---- 自我：成形 / 累积 / 消散 -------------------------------------
        if slot.filled() and float(slot.vector.sum()) > 0.0:
            v = np.asarray(slot.vector, dtype=np.float32)
            total = float(v.sum())
            sh = float(v[mi]) / total if total > 0.0 else 0.0
            # 「被瞥视」的时间窗内，外界目光把这一份自我读得更高（不是改向量）。
            if int(frame) < int(o.gaze_until):
                sh = min(1.0, sh * float(p.get("origin_gaze_boost", 1.5)))
            o.selfhood = sh
            if sh >= tau:
                o.ever = True
                o.filled = True
                o.age += 1
                o.dissolve_run = 0
                o.energy = min(cap, o.energy * (1.0 - decay) + gain_eff * sh)
                if o.seed_vector is None:
                    o.seed_vector = v.copy()
                # 读入十二因子数据之后，原初可以凝成「忆灵」形态。
                if (int(o.form) == 1
                        and float(o.coverage) >= float(p.get("origin_companion_coverage", 1.0))
                        and int(o.age) >= int(p.get("origin_companion_age", 600))
                        and sh >= tau):
                    o.form = 2
                    st.add_score("origin_companion")
                    st.score["emitted_origin_companion_formed"] = float(frame)
            else:
                o.filled = False
                o.age = 0
                o.energy = max(0.0, o.energy * (1.0 - decay))
                if sh < tau_low:
                    o.dissolve_run += 1
                    if o.dissolve_run >= int(p.get("origin_dissolve_dwell", 64)):
                        slot.owner, slot.value = None, 0.0
                        o.dissolve_run = 0
                        o.energy *= 0.5
                        st.add_score("origin_dissolved")
                else:
                    o.dissolve_run = 0
        else:
            o.filled = False
            o.selfhood = 0.0
            o.age = 0
            o.energy = max(0.0, o.energy * (1.0 - decay))
            o.dissolve_run = 0

        # ---- 三个 facet：只在已成形、能量足够时尝试 --------------------------
        if o.filled:
            # 创世：补一个真实个体进空着的非 meta 席。
            # `origin_create_min_form` 默认 1；origin 世界设为 2 —— 创世是忆灵形态
            # 之后才有的强作用，免得它在早期把本该由回望补上的空席直接填掉。
            cost = float(p.get("origin_create_cost", 2.0))
            if (o.energy >= cost
                    and int(o.form) >= int(p.get("origin_create_min_form", 1))):
                # 空席包括【被外部封印的席】：创世是比封印更强的一手 ——
                # 否则本世界里每一席都会被 Occupy 填满，创世永远没有空隙可补。
                # 记忆承载席归记忆自己补（下面的 rebind），创世不去抢。
                empties = [i for i, s in enumerate(st.register.slots)
                           if (not s.meta) and (not s.filled())
                           and i not in st.memory_seats]
                if empties:
                    seat = int(empties[0])
                    # 创世读的是【记忆里的十二因子数据】；没有记忆时才退回席位均值。
                    mean_vec = (st.memory_bank.mean(axis=0).astype(np.float32)
                                if st.memory_bank.shape[0]
                                else mean_seat_vector(st, exclude=(seat,)))
                    k = pick_candidate(st, seat, mean_vec)
                    if k >= 0:
                        serial = int(st.pool.serial[k])
                        st.register.slots[seat].owner = serial
                        st.register.slots[seat].value = float(
                            st.pool.vec[k, seat] * st.pool.fitness[k])
                        st.register.slots[seat].vector = st.pool.vec[k].copy()
                        st.pool.held[k] = True
                        st.pool.seated_clock[k] = st.world_clock
                        if seat in st.suppressed:
                            st.score["emitted_origin_create_break_seal"] = float(frame)
                        st.suppressed.discard(seat)   # 创世打破外部封印
                        o.energy -= cost
                        st.add_score("origin_create")

            # 爱：打开一个真实的时间窗（Drift 读 origin.love_until）。
            lc = float(p.get("origin_love_cost", 1.0))
            if o.energy >= lc and int(o.love_until) <= int(frame):
                dur = int(p.get("origin_love_duration", 64))
                if int(o.form) >= 2:          # 忆灵形态：爱的作用更持久
                    dur *= 2
                o.love_until = int(frame) + dur
                o.energy -= lc
                st.score["emitted_origin_love"] = float(frame)
                st.add_score("origin_love")

        # ---- 忆灵：form 2 时凝成一个【真实派生个体】 -------------------------
        # 它不是渲染标签：会进池、参与漂移/竞争、会死；死后原初可以再凝一个。
        if int(o.form) >= 2:
            alive = (int(o.companion_serial) >= 0
                     and st.pool.index_of_serial(int(o.companion_serial)) >= 0)
            if not alive:
                o.companion_serial = -1
                o.companion_stage = 0
                cc = float(p.get("origin_companion_cost", 3.0))
                if (o.energy >= cc
                        and int(frame) >= int(o.companion_until)):
                    k = st.pool.alloc()
                    if k >= 0:
                        if st.memory_bank.shape[0]:
                            v = st.memory_bank.mean(axis=0).astype(np.float32)
                        elif o.seed_vector is not None:
                            v = np.asarray(o.seed_vector, dtype=np.float32).copy()
                        else:
                            v = np.asarray(slot.vector, dtype=np.float32).copy()
                        total = float(v.sum())
                        if total <= 0.0:
                            v = np.full(int(st.dim), 1.0 / max(1, int(st.dim)),
                                        dtype=np.float32)
                        else:
                            v = (v / total).astype(np.float32)
                        st.pool.vec[k] = v
                        st.pool.factor[k] = int(mi)
                        st.pool.born[k] = int(frame)
                        st.born(int(frame), k)
                        st.pool.tags[k].add("origin_companion")
                        o.companion_serial = int(st.pool.serial[k])
                        o.energy -= cc
                        o.companion_until = int(frame) + int(
                            p.get("origin_companion_cooldown", 256))
                        # 新凝出的忆灵从「初凝」重新长起。
                        o.companion_stage = 1
                        o.companion_age = 0
                        o.companion_carry = 0
                        o.companion_bond = 0
                        o.companion_rebond_until = 0
                        st.add_score("origin_companion_spawn")

            # 依附：忆灵盯着一个真实的在位者（优先共鸣的外部变量），把记忆印回它。
            ck = (st.pool.index_of_serial(int(o.companion_serial))
                  if int(o.companion_serial) >= 0 else -1)
            if ck >= 0:
                o.companion_age += 1
                # 随身带着几段记忆：只看真正转印过的那些（新凝的忆灵继承已有的记忆）。
                o.companion_carry = sum(
                    1 for f in o.memory_fragments if f.transferred)
                hk = (st.pool.index_of_serial(int(o.companion_host))
                      if int(o.companion_host) >= 0 else -1)
                hi = host_slot(st, int(o.companion_host))
                newly_bonded = False
                if hk < 0 and hi < 0:
                    if (int(o.resonance_host) != -1
                            and host_present(st, int(o.resonance_host))):
                        o.companion_host = int(o.resonance_host)
                    else:
                        o.companion_host = pick_host(
                            st, exclude_serial=int(o.companion_serial))
                    if int(o.companion_host) != -1:
                        st.add_score("origin_attach")
                        o.companion_bond += 1
                        newly_bonded = True
                    hk = (st.pool.index_of_serial(int(o.companion_host))
                          if int(o.companion_host) >= 0 else -1)
                    hi = host_slot(st, int(o.companion_host))
                # 「承忆」阶段：换到新宿主时，把随身带着的那段记忆【完整】再印一次，
                # 而不只是每帧混一点向量 —— 记忆因此能越过一个宿主的死亡继续往前。
                if newly_bonded and int(o.companion_stage) >= 3:
                    for f in o.memory_fragments:
                        if not f.transferred:
                            continue
                        ph = f.phases[f.phase_index]
                        apply_memory_effect(
                            st, o, ph["effect"], ph["magnitude"],
                            hk, hi, mi, frame, p, cap)
                    st.score["emitted_origin_companion_rebond"] = float(frame)
                    st.add_score("origin_companion_rebond")
                if hk >= 0 or hi >= 0:
                    rate = float(p.get("origin_attachment_rate", 0.03))
                    mem = (st.memory_bank.mean(axis=0).astype(np.float32)
                           if st.memory_bank.shape[0]
                           else st.pool.vec[ck].copy())
                    # 「救世主记忆」被忆灵带在身上：印回宿主时，它占一半分量。
                    if o.savior_active and o.savior_vector is not None:
                        mem = (0.5 * mem + 0.5 * np.asarray(
                            o.savior_vector, dtype=np.float32)).astype(np.float32)
                    if hk >= 0:
                        v = (1.0 - rate) * st.pool.vec[hk] + rate * mem
                        total = float(v.sum())
                        if total > 0.0:
                            st.pool.vec[hk] = (v / total).astype(np.float32)
                    elif hi >= 0:
                        # 外部变量不是池中个体：把记忆印进它占着的那一席的属性向量。
                        slot_h = st.register.slots[hi]
                        v = (1.0 - rate) * np.asarray(slot_h.vector, dtype=np.float32) \
                            + rate * mem
                        total = float(v.sum())
                        if total > 0.0:
                            v = (v / total).astype(np.float32)
                            slot_h.vector = v
                            # 记忆场可能在累加承载量：不要把它每帧重置回向量的最大值。
                            slot_h.value = max(float(slot_h.value), float(v.max()))
                    # 记忆片段真正落到宿主身上：按【当前阶段】的 effect 改变世界。
                    for f in list(o.memory_fragments):
                        if not f.transferred:
                            f.start_frame = int(frame)
                            f.phase_index = 0
                            ph = f.phases[0]
                            apply_memory_effect(
                                st, o, ph["effect"], ph["magnitude"],
                                hk, hi, mi, frame, p, cap)
                            f.transferred = True
                            st.add_score("origin_memory_transfer")
                            st.score["emitted_origin_memory_transfer"] = float(frame)
                            if not o.savior_transferred:
                                o.savior_transferred = True
                                st.score["emitted_origin_savior_transfer"] = float(frame)
                                st.add_score("origin_savior_transfer")
                            continue
                        pi = f.phase_at(int(frame) - int(f.start_frame))
                        if pi != f.phase_index:
                            f.phase_index = int(pi)
                            ph = f.phases[f.phase_index]
                            apply_memory_effect(
                                st, o, ph["effect"], ph["magnitude"],
                                hk, hi, mi, frame, p, cap)
                            st.add_score("origin_memory_phase")
                        ph = f.phases[f.phase_index]
                        if ph["sustain"]:
                            apply_memory_effect(
                                st, o, ph["effect"], ph["rate"],
                                hk, hi, mi, frame, p, cap)
                            f.ticks += 1
                            st.add_score("origin_memory_tick")

                # 忆灵自己的成长阶段：只看真实读数 —— 活了多久、随身带过几段记忆。
                s2 = int(p.get("origin_companion_stage2_age", 600))
                s3 = int(p.get("origin_companion_stage3_age", 1500))
                if (int(o.companion_stage) < 2 and int(o.companion_age) >= s2
                        and int(o.companion_carry) >= 1):
                    o.companion_stage = 2
                    st.score["emitted_origin_companion_grow"] = float(frame)
                    st.add_score("origin_companion_grow")
                if (int(o.companion_stage) < 3 and int(o.companion_age) >= s3
                        and int(o.companion_carry) >= 2):
                    o.companion_stage = 3
                    st.score["emitted_origin_companion_grow"] = float(frame)
                    # 忆灵长到「承忆」＝ 记忆命途真的走通（不是渲染标签）。
                    st.score["emitted_origin_memory_path"] = float(frame)
                    st.add_score("origin_companion_grow")
                s4 = int(p.get("origin_companion_stage4_age", 2200))
                if (int(o.companion_stage) < 4 and int(o.companion_age) >= s4
                        and int(o.companion_carry) >= 2 and o.savior_transferred):
                    # 「忆者」：它不再只是替原初守席，而是自己成为记忆的执行者。
                    o.companion_stage = 4
                    st.score["emitted_origin_companion_grow"] = float(frame)
                    st.score["emitted_origin_companion_eminence"] = float(frame)
                    st.add_score("origin_companion_grow")

        # ---- 记忆承载的席位：空了就由【自己那一行】再补回来 ------------------
        # 原初有能量就自己补；能量不够时，长到「同行」的忆灵会替它守住这一席。
        if st.memory_seats and o.ever:
            rc = float(p.get("origin_rebind_cost", 0.5))
            ck2 = (st.pool.index_of_serial(int(o.companion_serial))
                   if int(o.companion_serial) >= 0 else -1)
            for i in sorted(int(x) for x in st.memory_seats):
                if i >= len(st.register.slots):
                    continue
                slot = st.register.slots[i]
                if getattr(slot, "meta", False) or slot.filled():
                    continue
                if ck2 >= 0 and int(o.companion_stage) >= 4:
                    # 「忆者」优先亲自守席 —— 它已经不只是替原初代管。
                    by_companion = True
                elif o.energy >= rc:
                    by_companion = False
                elif ck2 >= 0 and int(o.companion_stage) >= 2:
                    by_companion = True
                else:
                    continue
                row = memory_row_vec(st, i)
                slot.owner = MEMORY_OWNER
                slot.vector = row.copy()
                slot.value = float(row.max()) if row.size else 0.0
                st.suppressed.discard(i)
                st.score["emitted_origin_seat_reclaimed"] = float(frame)
                if by_companion:
                    st.score["emitted_origin_companion_rebind"] = float(frame)
                    st.add_score("origin_companion_rebind")
                    # 「忆者」：这一席由忆灵【自己】坐 —— 它成了记忆的执行者，
                    # 而不再只是隔着记忆去守。
                    if int(o.companion_stage) >= 4:
                        ck3 = st.pool.index_of_serial(int(o.companion_serial))
                        if ck3 >= 0:
                            slot.owner = int(o.companion_serial)
                            slot.vector = np.asarray(
                                st.pool.vec[ck3], dtype=np.float32).copy()
                            slot.value = float(slot.vector[i]
                                               * st.pool.fitness[ck3])
                            st.pool.held[ck3] = True
                            st.pool.seated_clock[ck3] = st.world_clock
                            st.score["emitted_origin_companion_seat"] = float(frame)
                            st.add_score("origin_companion_seat")
                else:
                    st.score["emitted_origin_memory_rebound"] = float(frame)
                    o.energy -= rc
                    st.add_score("origin_rebind")

        # ---- 开拓：结构停滞时的内生破局尝试 --------------------------------
        tc = float(p.get("origin_trailblaze_cost", 5.0))
        dwell = int(p.get("origin_trailblaze_dwell", 512))
        sig = st.world_signature()
        o.stagnant_run = 0 if (o.last_sig is None or sig != o.last_sig) \
            else o.stagnant_run + 1
        o.last_sig = sig
        if (o.stagnant_run >= dwell and o.energy >= tc
                and st.domains_exhausted and int(frame) >= int(o.trailblaze_until)):
            cur = SOLVER_NAMES.index(st.solver) if st.solver in SOLVER_NAMES else -1
            st.solver = SOLVER_NAMES[(cur + 1) % len(SOLVER_NAMES)]
            for g in (p.get("origin_trailblaze_gates") or []):
                if g in GATE_NAMES and g not in st.gates:
                    st.gates.add(str(g))
                    break
            o.energy -= tc
            o.stagnant_run = 0
            o.trailblaze_until = int(frame) + int(
                p.get("origin_trailblaze_cooldown", 512))
            o.last_sig = st.world_signature()
            st.add_score("origin_trailblaze")
        return st


OPERATORS = {
    "OP_DRIFT": Drift,
    "OP_INTERACT": Interact,
    "OP_OCCUPY": Occupy,
    "OP_COMPETE": Compete,
    "OP_ANNEX": Annex,
    "OP_REPOPULATE": Repopulate,
    "OP_BIFURCATE": Bifurcate,
    "OP_CAPABILITY": Capability,
    "OP_ENTROPY": Entropy,
    "OP_DOMAIN": Domain,
    "OP_ACTIVE_RENEWAL": ActiveRenewal,
    "OP_PROMOTION": Promotion,
    "OP_PATH": Paths,
    "OP_DECIDE": Decide,
    "OP_ORIGIN": Origin,
}

#: 登记过的机制门名（与上面两张表同源：门名必须真的是被读的那个）。
GATE_NAMES = (MEMORY_INHERIT_GATE, Bifurcate.name, Annex.name, ActiveRenewal.name)

#: 阶段装配【允许覆盖】的参数旋钮 —— 按「运行时真读它的地方」列举（白名单，不是黑名单）。
#: 写不在表里的键，在引擎里根本没人读 ⇒ 配置侧一律拒绝（不静默失效）。
#:
#:   Drift      → coupling_gain / mutation / noise_to_mutation / stability_eps
#:   Interact   → interact_gain / interact_repel
#:   Compete    → tau_support / tau_age / tau_noise_annihilation / tau_homogenized / life_span
#:   Repopulate → min_population / min_factor_cohort / inherit_mutation
#:   Capability → tau_capability
#:   Entropy    → entropy_mix / noise_decay
#:   Domain     → tau_falsify / domain_dwell（tau_falsify 检查器也读）
#:   Promotion  → promotion_gain / capacity_inherit / promotion_dwell / promotion_cooldown
#:                / renewal_consensus（主动更替的共识门槛）
#:   涌现登记器 → tau_stable / tau_influence
#:   消融（探针）→ ablation_frames / tau_ablation_entropy
#:   扰动·交涉  → tau_parley / tau_noise_parley（disturbance 的 parley 能力读 ——
#:                它是引擎里唯一「和平取得席位」的路，与 evict_holder 成对）
#:
#: 刻意【不在】表里的：
#:   · 结构参数 dim / observables / pool_capacity —— 状态在创建时按它们定死，中途改不了；
#:   · 引擎自身的循环控制旋钮 frames / attempt_* / trace_* / freeze_dwell / tick_marks /
#:     reuse_reference / ablation_period —— 它们在循环外就被读进局部量，改了对演算无效；
#:   · 非数值 verbosity / capability_names / verdict_rules，以及布尔开关 emergence；
#:   · 探针口径的来源 ablation_pool —— solve 据它写死 min_population，不许阶段改。
STAGE_TUNABLE = (
    "coupling_gain", "mutation", "noise_to_mutation", "stability_eps",
    "interact_gain", "interact_repel",
    "tau_support", "tau_age", "tau_noise_annihilation", "tau_homogenized",
    "life_span",
    "min_population", "min_factor_cohort", "inherit_mutation",
    "tau_capability",
    "entropy_mix", "noise_decay",
    "tau_falsify", "domain_dwell",
    "promotion_gain", "capacity_inherit", "promotion_dwell", "promotion_cooldown",
    "renewal_consensus",          # 主动更替：换代所需的决策共识门槛（Promotion 读）
    "tau_stable", "tau_influence",
    "ablation_frames", "tau_ablation_entropy",
    "tau_parley", "tau_noise_parley",   # 交涉取席位的成败判据（parley 读）
    "ember_delay",                      # 权柄账本：每被夺一次，再创世多等多少帧（Promotion 读）
    "annex_span_ratio",          # 嵌合协议：非嵌合因子的寿命倍率（Annex 读、Compete 用）
)