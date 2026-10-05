"""反证法的消融求解器。

它不是公式——它在内部【再跑一轮逐步模拟】。嵌套 ≠ 解析。
对每个位做单因子消融：只保留该因子，看系统是否仍然走向失序。
"""
from __future__ import annotations

import numpy as np

from .operators import Compete, Drift, Entropy, Interact, Repopulate
from .state import State, mix

ABLATION_PIPELINE = (Drift(), Interact(), Compete(), Repopulate(), Entropy())

#: 三路探针各自的 rng 流标签 —— 让「独留 / 剔除 / 基准」互不共用抽样。
#: **不含 frame**：探针不读世界状态，每帧重抽只会给 progress 叠一层与动力学无关的
#: 抖动（同一席读数每 500 帧来回跳）—— 那是噪声，不是动力学。
_SOLO, _OFF, _EVEN = 1, 2, 3

#: 内容缓存：同一「口径 + 输入内容 + 抽样号」只算一次。命中即返回同一个浮点
#: （纯函数 ⇒ 逐位可复现）；换阶段 / 换变量域 / 换参数即自动失效。
_CACHE = {}
_CACHE_MAX = 65536


class _Params(dict):
    def __init__(self, base, over):
        super().__init__(base)
        self.update(over)


class _Ctx:
    """只替换参数，其余全部沿用同一套配置——保证消融与本体同源。"""

    def __init__(self, ctx, over):
        self.params = _Params(ctx.params, over)
        self.coupling = ctx.coupling
        self.seeding = ctx.seeding
        self.mapping = ctx.mapping


def _sig_params(params) -> tuple:
    """参数的完整内容签名（可哈希）—— 探针读到的每一个旋钮都在里面。"""
    return tuple(sorted((str(k), repr(v)) for k, v in params.items()))


def _sig_seeding(seeding) -> tuple:
    """播种配置的内容签名。消融管线里 `Repopulate` 会读 `seeding["alpha"]`
    （见 `engine/operators.py`），故它必须进缓存键 —— 否则同一进程内换了播种配置
    会命中陈旧浮点。`_sig_params` 的约定是「探针读到的每一个旋钮都在签名里」，
    这一项补上那个缺口。
    """
    return tuple(sorted((str(k), repr(v)) for k, v in seeding.items()))


def _sig_loci(loci) -> tuple:
    """位表的内容签名：**只取耦合行**。

    消融管线（漂移 / 相互作用 / 淘汰 / 补种 / 熵）只经 `ctx.coupling` 读耦合，**不读**
    `locus.capacity` / `decay` —— 那两个只被承位 / 再创世用，都不在管线里。故把它们
    排除：否则每次换代 `capacity *= capacity_inherit` 都会打散缓存键（实测：改
    capacity/decay 对 progress / progress2 **逐位无影响**）。
    """
    return tuple((str(l.id), int(l.order),
                  tuple(repr(float(c)) for c in l.couplings)) for l in loci)


def solve(st, ctx, seed, stage_gates=(), stage_overrides=None):
    """遍历全部位，逐一做消融实验，结果写回 locus.progress / progress2（连续读数）。

    `stage_gates` 是【当前阶段的机制装配】。它必须进得来 —— 阶段机制若不进消融，
    它对 progress（进而对裁决）就没有因果，那就只是渲染上的说法了。

    `stage_overrides` 是【当前阶段的参数覆盖】。它同样只进消融 —— 这与既有的
    `domain_disorder` 走的是同一条通路：本引擎里「初始变量 / 阶段」一向只定义
    **探针条件**，不改造主世界（`disorder` 从第一天起就只喂给这里）。

    **探针是「内容」的纯函数，不是「时机」的函数**：迷你世界读到的只有
    `(seed, 位次, 口径, 阶段门, 参数, dim/obs/domain, 位表, 播种)` —— 世界演化到哪一帧
    对它没有影响。于是同一「阶段 × 变量域」内 progress 是定值，`solve` 虽仍每
    `ablation_period` 帧被调用，重算会被内容缓存短路。

    **基准与路 B 各取 `ablation_draws` 组独立样本再取均值；路 A 仍是单次抽样**：
    迷你世界只有 `ablation_pool` 个个体，单次熵很吵；而路 B 是 12 席**共用一个分母**
    （十二席全在的基准世界），单次抽样会让 12 个比值同时涨落 —— 实测「12 席同时
    达标」原本只靠 6% 的抽样运气（见遗留议题 §1.4）。取均值把抖动压到 1/√K。
    路 A（`progress`）目前**仍传 `draws=1`**：它的读数与达标线 `tau_falsify` 都是既有
    世界的基线，改成均值会改变 `proved` / `destruction` 的可达性 —— 属「会动轨迹」的
    改动，须单独评估、全量重测后再动。
    """
    p = ctx.params
    disorder = 0.0
    if st.domain_disorder:
        di = min(int(st.domain_index), len(st.domain_disorder) - 1)
        disorder = float(st.domain_disorder[di])
    over = dict(stage_overrides or {})
    over.update({                   # 探针自己的四个口径【最后写】—— 任何阶段参数都盖不掉它
        "min_population": int(p["ablation_pool"]),
        "life_span": 10 ** 9,
        "min_factor_cohort": 0,     # 消融只保留单一因子，不做因子均衡
        "disorder": disorder,       # 当前初始变量取值对应的世界失序度
    })
    sub = _Ctx(ctx, over)
    gates = tuple(stage_gates)
    sig = (int(seed), gates, _sig_params(sub.params), int(st.dim), int(st.obs_dim),
           tuple(st.domain), _sig_loci(st.loci), _sig_seeding(sub.seeding))
    draws = max(1, int(p.get("ablation_draws", 1)))
    tau = float(p["tau_ablation_entropy"])
    # 基准（十二席全在）：路 B 的公共分母，必须估稳，故取 K 次均值
    base_e = _mean_entropy(st, sub, 0, sig, gates, _EVEN, _PEAK_EVEN, "argmax", draws)
    # 【第二路探针 · 剔除口径】保留其余 11 个因子，只把这一位拿掉 —— 问的是
    # 「少了它，世界还照样失序吗」。与路 A【独留】构成对偶，而两路的席间差异来自
    # **不同的东西**：路 A 只看该位的耦合行，路 B 看的是「其余因子在没有它时能否失序」。
    #
    # `progress2` 的达标线是参数里的 `tau_falsify_band`，**不是** τ ——
    # 这个比值（剔除后熵 / 全在时熵）的期望本就在 1 以下（实测 0.96–0.99），
    # 用 τ=1 等于要求「删掉任意一席都不损失失序度」，在期望上就是假的。
    # 现在的语义是「删掉任一席，失序度损失不超过 (1 − band)」= 没有哪一席是瓶颈。
    for i, locus in enumerate(st.loci):
        solo_e = _mean_entropy(st, sub, i, sig, gates, _SOLO, None, None, 1)
        leave_e = _mean_entropy(st, sub, i, sig, gates, _OFF, _PEAK_OFF, "argmax", draws)
        locus.progress = solo_e / tau if tau > 0 else 0.0
        locus.progress2 = leave_e / base_e if base_e > 0 else 0.0
    return st


#: 独留口径的采样峰值（该因子在 dirichlet 里的权重）——**不可改**，改了就动轨迹。
_PEAK_SOLO = 8.0
#: 剔除口径的采样峰值：该维度几乎抽不到 —— 样本落到其余因子上。
_PEAK_OFF = 0.02
#: 基准口径的采样峰值：与基线权重相同 ⇒ 十二个因子**均匀全在**，不偏向任何一个。
_PEAK_EVEN = 0.10


def _mini_world(st, sub, index, rng, stage_gates=(), peak=None, home=None):
    """造消融用的迷你世界：容量取样本数的三倍。

    `peak` 是该因子在采样里的权重峰值：默认 `_PEAK_SOLO` = **独留**（样本偏向该因子）；
    传一个很小的值（如 0.02）即**剔除**（该维度几乎抽不到，样本落到其余因子上）。

    `home` 是原生因子怎么记：默认记 `index`（独留口径 —— **必须保持不变**，否则会改既有
    世界的 `progress`）；剔除口径传 `"argmax"`（各自记最强的那个维度）。

    这里把 `stage_gates` 装上 —— 于是「该阶段开了哪些机制」会真的参与这轮迷你演算。
    （只装阶段装配的门，**不**照搬主世界的 `st.gates`：外生扰动开的门属另一码事，
    照搬会改变既有世界的既有结果。）
    """
    dim = st.dim
    size = int(sub.params["ablation_pool"])
    mini = State(st.loci, dim, st.obs_dim, size * 3, st.domain)
    mini.gates = set(stage_gates)

    alpha = np.full(dim, 0.10, dtype=np.float32)
    alpha[index] = _PEAK_SOLO if peak is None else float(peak)
    vecs = rng.dirichlet(alpha, size=size).astype(np.float32)
    vecs /= vecs.sum(axis=1, keepdims=True)
    for k in range(size):
        j = mini.pool.alloc()
        if j < 0:
            break
        mini.pool.vec[j] = vecs[k]
        mini.pool.factor[j] = (int(index) if home is None
                               else int(np.argmax(vecs[k])))
        mini.pool.born[j] = 0
    return mini


def _entropy(st, sub, index, sig, gates, tag, draw, peak=None, home=None):
    """单个位、单路、第 `draw` 组抽样跑完迷你世界后的末熵（带内容缓存）。

    rng 由 `(seed, 位次, 口径标签, 抽样号)` 派生 —— 见 `solve`：**不含 frame**。
    """
    key = (sig, int(index), int(tag), int(draw))
    hit = _CACHE.get(key)
    if hit is not None:
        return hit
    rng = np.random.default_rng(mix(int(sig[0]), int(index), int(tag), int(draw)))
    mini = _mini_world(st, sub, index, rng, gates, peak=peak, home=home)

    for t in range(int(sub.params["ablation_frames"])):     # ← 逐帧，不是解析解
        for op in ABLATION_PIPELINE:
            op.apply(mini, sub, rng, t)

    val = float(mini.entropy)
    if len(_CACHE) >= _CACHE_MAX:      # 上限：纯函数，清空无副作用，防长进程无界增长
        _CACHE.clear()
    _CACHE[key] = val
    return val


def _mean_entropy(st, sub, index, sig, gates, tag, peak, home, draws) -> float:
    """同一探针取 `draws` 组独立样本的末熵均值（压掉单次抽样的抖动）。"""
    n = max(1, int(draws))
    total = 0.0
    for d in range(n):
        total += _entropy(st, sub, index, sig, gates, tag, d, peak, home)
    return total / n