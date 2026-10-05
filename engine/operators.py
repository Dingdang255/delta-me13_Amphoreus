"""L2：通用算子。

每个算子只做【一帧】的转移；没有任何 per-locus 分支，没有任何专有名词。
位的语义完全由【数值】决定，不由代码决定。
"""
from __future__ import annotations

import numpy as np

MEMORY_OWNER = -1   # 由记忆承载的位：不会被活体重新争夺


def is_external_owner(owner) -> bool:
    """这一席的承载者是不是【外生】的（编号 < 0）—— 不从池子里长出来的场外参与者。

    带外编号构成一族：`MEMORY_OWNER`（由记忆承载）只是其中一员；预设登记的场外参与者
    （`bind_participant` 投进来的那些）用别的负号。判据只看【编号的符号】这个状态标志，
    不看名字 —— 于是换词表 / 换命名器都不改轨迹（命名正交）。外生占位一律：
    不被活体抢占 / 不被逐火驱逐 / 不被竞争淘汰 / 不计入涌现。
    """
    return owner is not None and int(owner) < 0


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
        push = (v @ ctx.coupling) * p["coupling_gain"]
        sigma = p["mutation"] * (1.0 + p["noise_to_mutation"] * st.noise)
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
                slot.owner, slot.value = None, 0.0
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
    （见 engine/verdicts.py 的 `all_falsified`）。
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