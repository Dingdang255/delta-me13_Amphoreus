"""L0：主循环。

本文件不应出现任何专有名词。若出现，构建失败（tools/grep_forbidden.py）。
整段代码里没有一个专有名词，也没有一个个体是先于演算存在的。
"""
from __future__ import annotations

from collections import Counter

import numpy as np

from .disturbance import CAPABILITIES, dispatch
from .emergence import EmergenceRegistrar
from .operators import OPERATORS
from .scheduler import Scheduler
from .state import DEATH_CAUSES, DEFAULT_SOLVER, State, mix, world_distance
from .verdicts import ascends_of, evaluate, inner_conclusion

# 等待的刻度：死循环里的时长按几何级数展开成几个读数（纯渲染，不推进任何状态）。
# 生产值即此处的默认；可被 params.tick_marks 覆盖（--fast 提速时按比例缩短）。
_TICKS = (10 ** 3, 10 ** 4, 10 ** 5, 10 ** 6, 10 ** 7, 10 ** 8, 10 ** 9)


class Trajectory:
    def __init__(self):
        self.records = []          # (frame, kind, payload)
        self.spans = []            # (kind, start, end)
        self.personas = []
        self.namer = None
        self.final = None
        self.total_frames = 0
        self.iterations = 0
        self.skipped_frames = 0
        self.violation_counts = Counter()
        self.conclusion = None
        self.converged = False
        self.deadlock = False
        self.truncated = False      # 是否为迭代上限所截断（安全阀，不改变任何语义）
        self.verdict = None         # "proved" | "refuted" | "undecided"：命题裁决结果
        self.verdict_frame = None   # 命题被裁决的那一帧
        self.stop_reason = None     # PROVED | REFUTED | ITER_CAP | BUDGET
        self.reached_frame = 0      # 实际走到的最后一帧
        self.conclusion_seen = None      # 里程碑：当前已播报过的内层结论
        self.conclusion_trail = []       # [(frame, conclusion)]：结论链
        self.ascended = False            # 是否升格外溢（结论被"改写"那一改的外生产物）


# 判据表（C4）的求值在 engine/verdicts.py：情形与附加条件都是注册表，
# 一条规则 = when + 可选的 require 列表。这里只在每帧求值一次，供「结论里程碑」
# 与「裁决」共用 —— 过去两处各扫一遍判据表（每帧两次），现在一次。


def _stage_index(st, data) -> int:
    """当前处在第几阶段。

    变量域穷尽之后算「阶段四」（下标 = 域长），否则就是域下标本身。
    没配 `stages` 时返回 0（调用方拿到的装配恒为空）。
    """
    n = len(st.domain)
    return n if st.domains_exhausted else int(st.domain_index)


def _assemble(st, data) -> list:
    """把当前阶段的机制装进世界。幂等：门只增不减，且装配是【累积】的。

    返回【本次新装上的门】（供编年史播报）。没配 `stages` 时恒为空 —— 与历史逐位一致。
    只写 `st.gates`：它在 `world_signature()` 里，于是冻结检测与复用等价都看得见这次变化。
    """
    want = set(data.stage_gates(_stage_index(st, data)))
    new = want - st.gates
    if new:
        st.gates |= new
    return sorted(new)


class StageCtx:
    """「基础配置 + 当前阶段的参数覆盖」合成的 ctx —— 交给算子 / 检查器 / 调度器 / 登记器。

    它只把 `.params` 换成【合并后的字典】（随阶段推进原地更新），其余属性一律转发给真实
    的 Config。于是阶段参数真的能改变【世界】的演化，而不只是探针条件 —— 这是把"阶段"
    从「实验条件」升级为「世界规则」的那一步。

    没配 `stages`（或各项都空）时，合并结果与基础参数逐项相同 ⇒ 行为与历史逐位一致。
    """

    def __init__(self, cfg):
        self._cfg = cfg
        self.params = dict(cfg.params)

    def rebind(self, overrides):
        """按当前阶段重算合并参数。**原地更新** —— 持有本对象的读者立刻看得见。"""
        merged = dict(self._cfg.params)
        merged.update(overrides or {})
        self.params.clear()
        self.params.update(merged)

    def __getattr__(self, name):
        return getattr(self._cfg, name)


def initial_state(cfg, data, seed: int) -> State:
    """统计播种：第一帧的个体从【位的基】里采样出来，没有任何一个是被指定的。"""
    p = cfg.params
    sd = cfg.seeding
    gen = data.genesis
    st = State(cfg.loci, int(p["dim"]), int(p["observables"]),
               int(p["pool_capacity"]), list(gen["domain"]["initial_variable"]))
    st.solver = str(gen.get("runtime", {}).get("solver", DEFAULT_SOLVER))
    st.domain_disorder = [float(x) for x in gen["domain"].get("disorder", [])]

    rng = np.random.default_rng(mix(seed, 0x5EED))
    alpha0 = float(sd["alpha"])
    lo, hi = int(sd["per_locus"]["min"]), int(sd["per_locus"]["max"])
    for locus in cfg.loci:
        count = int(rng.integers(lo, hi + 1))
        for _ in range(count):
            i = st.pool.alloc()
            if i < 0:
                break
            alpha = np.full(int(p["dim"]), alpha0, dtype=np.float64)
            alpha[locus.order] = 6.0
            v = rng.dirichlet(alpha).astype(np.float32)
            st.pool.vec[i] = v / float(v.sum())
            st.pool.factor[i] = int(locus.order)     # 出生即定的原生因子
            st.pool.born[i] = 0
            st.born(0, i)

    # 外部实体表：把预设登记过的实体装进状态。引擎只认「已登记」这个事实，
    # 不认任何一个名字 —— 谁在操作这个世界，由预设说了算。
    for a in (getattr(data, "actors", None) or []):
        st.actors[str(a["id"])] = {"label": a.get("label", ""),
                                   "grants": tuple(a.get("grants") or ()),
                                   "state": {}}
    # 阶段装配：第 0 阶段的机制从一开始就装上（没配 stages ⇒ 这里什么都不会发生）。
    _assemble(st, data)
    return st


def _vacant(st):
    """当前空缺的位（按位次）。只报位次，不报是谁 —— 引擎不认识任何专有名词。"""
    return [i for i, s in enumerate(st.register.slots) if s.owner is None]


def run(cfg, data, seed: int | None = None, max_frames: int | None = None,
        trace: bool = True, start_state=None, start_frame: int = 0,
        namer=None, capture=None, iter_cap: int | None = None,
        watch=None, on_event=None, rules=None, runtime=None) -> Trajectory:
    """逐帧推进。

    start_state/start_frame：从第 k 帧的存档续跑（判据 4 帧截断复现）。
    namer：命名器的【不透明句柄】—— 内核从不使用它，只是原样挂到 traj 上，
           供表现层（报告 / 看板 / 断言）取用。故“换命名器不改轨迹”不再是需要
           证明的性质，而是构造成立的事实：内核既不 import 命名，也不调用它。
    capture：可选的逐迭代摘要收集器，用于跨运行 diff。
    iter_cap：迭代次数上限（安全阀）。仅用于检索大量种子时封顶开销；
              未到上限时它对演算结果没有任何影响。触顶则 traj.truncated=True。
    watch：可选的逐帧观察钩子 watch(frame, st, traj) -> bool。返回 False 只做一件事：
           让本次运行【提前停下】（traj.stop_reason="PRUNED"）。
           它只读、不写状态，因此停下之前走过的每一帧与全程运行逐帧一致 ——
           它只是一个安全阀，用来在检索大量种子时提前毙掉明显不合的轨道。
    on_event：可选的实时回调 on_event(frame, kind, payload, clock, namer)。
           每当引擎记下一条事件（与 traj.records 同源）就立即回调，用于实时监听。
           它只读、不写状态 —— 删掉它，Trajectory 逐帧不变。
    rules：可选的【不透明谓词】rules(expr, obs) -> bool，用来求值投递条目上的 `when`。
           与 namer / watch / on_event 同一手法：内核只负责"每帧问它一次"，
           **不认识条件的写法、也不 import 任何条件语言**（那种语言住在服务层，
           见 engine/conditions.py 与 tools/layer_lint.py 的层次表）。
           obs 由内核自己构造（帧号 / 账本计数 / 已发生的事件表 …）—— 那本就是
           observe() 这个系统调用该干的事。
           不传 ⇒ 内核完全忽略 `when`；此时若真有条目带 when，会在启动时【报错】
           而不是静默忽略（静默会把"条件写错了"变成"这条永远不触发"，最难查）。
    runtime：应用层交来的【服务实现束】（见 engine/services.py）—— 内核只按名调用，
           **不 import 服务层**。其中的 `checks` 每帧收违例（调度器的控制输入）、
           `probe` 跑消融探针、`judge` 决定停不停。与 namer / rules 同一手法。
           **必须给**：缺了不是"行为略不同"，而是跑不了 —— 故不给就当场报错。

    终止条件：不是"跑够多少帧"，而是【命题能否裁决】（见 _decide）。
              被裁决则 traj.stop_reason ∈ {PROVED, REFUTED} 并停下；
              否则才会走满预算（BUDGET）或撞上安全阀（ITER_CAP）。
    """
    p = cfg.params
    # 带 `when` 的投递要等条件成立才触发 —— 内核不认识条件，得由应用层把谓词递进来。
    # 没递又真有条目带 when：**当场报错**，绝不静默忽略（见 run 的 docstring）。
    pending = list(getattr(data, "conditioned", ()) or ())
    if pending and rules is None:
        raise ValueError(
            f"世界里有 {len(pending)} 条带 when 的投递，但 run() 没收到 rules=。"
            "要么传 rules=engine.conditions.evaluate，要么把那些 when 去掉 ——"
            "内核不猜条件；静默忽略会把「条件写错」变成「这条永远不触发」。")
    # 服务实现束：内核不 import 服务层，改由应用层交来（见 engine/services.py）。
    # 它没有"合理默认" —— 少了违例读数，调度器的行为就变了，故必须显式给。
    if runtime is None:
        raise ValueError(
            "run() 需要 runtime=（应用层交来的服务实现束）。"
            "缺了它不是「行为略不同」而是跑不了 —— 违例是内核调度的控制输入。"
            "用 engine.services.default() 即可。")
    if seed is None:
        seed = data.preset.get("seed")
        if seed is None:
            seed = data.genesis.get("seed", 0)
    seed = int(seed)
    cfg.seed = seed
    total = int(max_frames if max_frames is not None else p.get("frames", 20000))

    # 死循环期的参数：尝试落点间隔 / 单次演算帧数 / 留痕阈值 δ / 可用方向。
    attempt_period = max(1, int(p.get("attempt_period", 4096)))
    attempt_span = max(0, int(p.get("attempt_span", 4)))
    trace_delta = float(p.get("trace_threshold", 1.0))
    # 一次尝试真的在世界里留下结构差异的概率。刻得极低是有意的：几万次尝试里
    # 只有寥寥数次能挪动世界一线，其余连试算都不必做 —— 「试过很多法子，几乎
    # 什么都没改变」。它是独立子流上的一个读数，不影响逐帧可复现性。
    trace_chance = float(p.get("trace_chance", 1.0))
    # 尝试策略 = 一条【阶段阶梯】（决策树）：段位由尝试次数（失败次数）推进，
    # 段内【按次序】取能力 —— 不再掷骰子。段的语义（期望 / 幻灭 / 灼烧 / 执念）
    # 由预设的词表命名，引擎只认 {id, until, caps, routine} 四个字段。
    attempt_stages = [s for s in (p.get("attempt_stages") or []) if s.get("caps")]

    def _stage_for(cycle):
        """按尝试次数定位所处阶段，并给出该段的起始编号（段内据此顺序取能力）。"""
        start = 0
        for stg in attempt_stages:
            until = stg.get("until")
            if until is None or cycle < int(until):
                return stg, start
            start = int(until)
        return (attempt_stages[-1], start) if attempt_stages else (None, 0)

    # 结构须【连续冻结】这么多帧才判定为死循环：瞬时的一两次重复是常态，不足为凭。
    freeze_dwell = max(1, int(p.get("freeze_dwell", 256)))
    # 等待的几何刻度（纯渲染）。可被 params.tick_marks 覆盖。
    ticks = tuple(int(t) for t in (p.get("tick_marks") or _TICKS))
    # 是否沿参考轨道复用（生产为 True）。关掉只是把循环期改回逐帧真算，
    # 专供「等价性检查」核对复用没有伪造世界状态。
    reuse_reference = bool(p.get("reuse_reference", True))

    # 阶段参数从这里进世界：ctx_run 把「基础 params + 当前阶段覆盖」合成后交给
    # 算子 / 检查器 / 调度器 / 登记器（缺省 ⇒ 与基础参数逐项相同，行为不变）。
    ctx_run = StageCtx(cfg)
    ops = [OPERATORS[n]() for n in cfg.pipeline]
    scheduler = Scheduler()
    registrar = EmergenceRegistrar(ctx_run)
    traj = Trajectory()
    # namer 只是【不透明句柄】：内核原样挂在 traj 上，既不构造它、也不调用它的
    # 任何方法、更不知道它是什么类型。命名归表现层（engine/namer.py）负责。
    traj.namer = namer

    st = initial_state(ctx_run, data, seed) if start_state is None else start_state
    ctx_run.rebind(data.stage_params(_stage_index(st, data)))
    n = int(start_frame)

    seen_events = set()          # 已经发生过的事件名 —— 供 event("X") 这类条件读

    def emit(frame, kind, payload):
        """记下一条事件：写进 Telemetry（trace 时），并立即转给实时回调。

        这是引擎【唯一】的事件出口 —— 报告、特征提取、实时输出看到的是同一串记录。
        注意：`event("X")` 读的事件名**不从这里收** —— 播报用的载荷里没有 `event`
        字段（只有频道 / 能力 / 标签），事件名在【投递记录】上，见下面的分发处。
        """
        if trace:
            traj.records.append((frame, kind, payload))
        if on_event is not None:
            on_event(frame, kind, payload, st.world_clock, traj.namer)

    # 死因计数：墓碑是**只增**的，故按增量并进计数器；只在真要建快照时才走这一步。
    _death_tally = {}
    _death_seen = [0]

    def _refresh_deaths():
        """把新增的墓碑并进死因计数。存档回滚过（墓碑变少）就重数一遍。"""
        tombs = st.tombstones
        if len(tombs) < _death_seen[0]:
            _death_tally.clear()
            _death_seen[0] = 0
        while _death_seen[0] < len(tombs):
            cause = str(tombs[_death_seen[0]][3])
            _death_tally[cause] = _death_tally.get(cause, 0) + 1
            _death_seen[0] += 1

    def obs_now(frame):
        """内核视角的观测快照 —— 条件能读到的全部就是这些（读不到的名字一律报错）。

        它就是 `observe()` 这个系统调用：帧号 + 账本计数 + 席位占用 + 能力现身 +
        已发生事件表。**只读**，不碰世界一个比特；没有条件挂起时根本不构造（零开销）。
        """
        _refresh_deaths()
        obs = {"frame": int(frame), "promotions": int(st.promotions),
               "round": int(st.round), "domain_index": int(st.domain_index),
               "entropy": float(st.entropy), "personas": len(registrar.personas),
               "deadlocked": 1 if deadlock is not None else 0,
               "events": seen_events}

        # 席位：每席是否有人（`seat_l00` 这类，取值 0/1）+ 满 / 空的总数；
        # 以及每席的【承载】与寄存器值 —— 实测这两样才是真正会重排的量
        # （三个簇轮流挑头），条件挂在它们上面才有区分度。
        filled = 0
        loads = []
        for i, slot in enumerate(st.register.slots):
            lid = str(slot.locus_id).lower()
            has = 1 if slot.filled() else 0
            filled += has
            obs["seat_" + lid] = has
            load = float(st.loci[i].load)
            loads.append(load)
            obs["load_" + lid] = load
            obs["value_" + lid] = float(slot.value)
        obs["seats_filled"] = filled
        obs["seats_vacant"] = len(st.register.slots) - filled
        obs["load_max"] = max(loads) if loads else 0.0
        obs["load_min"] = min(loads) if loads else 0.0
        obs["load_span"] = (max(loads) - min(loads)) if loads else 0.0

        # 能力：按配置的能力表**给全量布尔** —— 于是条件里引用一个"还没现身"的能力
        # 也读得到（值为 0），不会因为名字不存在而报错。
        present = set()
        for k in st.pool.index():
            for t in st.pool.tags[int(k)]:
                if t.startswith("capability:"):
                    present.add(t.split(":", 1)[1])
        for cap in CAPABILITIES:
            obs["cap_" + str(cap)] = 1 if cap in present else 0

        # 账本：按死因分档的累计陨落数（`deaths_aged` / `deaths_dethroned` …）
        for cause in DEATH_CAUSES:
            obs["deaths_" + str(cause)] = int(_death_tally.get(cause, 0))
        obs["deaths"] = int(sum(_death_tally.values()))
        return obs

    last_prom_frame = [0]

    def burden(frame):
        """承载者此刻【背负】的量。全是通用计数，不含任何专有名词。

        每一项都取自累加型计数器，而不是会被周期性复位的瞬时字段
        （death_events 会被熵算子清零，memory_bank 终局为空，都不能用）。
        """
        filled = sum(1 for s in st.register.slots if s.owner is not None)
        return {
            "filled": int(filled),
            "slots": len(st.register.slots),
            # 谁坐哪一席（只给编号）。渲染层据此把「承载者」认到具体的人身上 ——
            # 引擎不认识人，也不该认识：它只报编号，谁是谁由 L5 命名器说了算。
            "owners": tuple(s.owner for s in st.register.slots),
            "seeds": int(st.seeds),
            "rounds": int(st.promotions),
            "clock": int(st.world_clock),
            "fell": int(st.score.get("deaths_natural", 0.0)),
            "skipped": int(traj.skipped_frames),
            "since_promotion": int(frame - last_prom_frame[0]),
        }

    def _attempt(frame):
        """承载者的一次尝试：换一种法子，与冻结的参考结构比对。

        绝大多数尝试连一丝结构差异都留不下 —— 先用【独立随机子流】过一道很窄的
        概率窄门，门没过就连试算都省了，直接判「徒劳」。过了门才在克隆上行使能力、
        真演算若干帧：徒劳则丢弃克隆，留痕则提交进主轨道。

        用哪种能力由【阶段阶梯】决定（段位随失败次数推进、段内按次序取），
        作用于哪个位则由独立子流决定。它绝不消耗主 rng，所以种子确定性与逐帧
        复现（checkpoint_replay）不受影响。这里不出现任何专有名词 —— 能力名与
        阶段名都是通用的，"是谁在试""这是他第几段心境"由渲染层事后赋予。

        返回 True 表示这次尝试【留痕】（世界被挪动了一线）。
        """
        if not attempt_stages:
            return False
        cycle = deadlock["cycle"]
        stg, stg_start = _stage_for(cycle)
        caps = [c for c in (stg.get("caps") or []) if c]
        if not caps:
            return False
        routine = bool(stg.get("routine"))
        stage_id = str(stg.get("id") or "?")
        h = mix(seed, 0xA771, cycle)
        # 段内【按次序】取能力：第一次轮回自然落在「期望」段的首项（游说）——
        # 他还想着仅凭陈说利害就能让人交出手里那一份。
        cap = caps[(cycle - stg_start) % len(caps)]
        fn = CAPABILITIES.get(cap)
        if fn is None:
            return False
        # 账本先落：每轮回一次，本世的量就归入账本（账本只增不减，世界会回退）。
        st.attempts += 1
        deadlock["cycle"] = cycle + 1

        if routine:
            # 末段：只剩「阻止再创世」那一丝理智，不再换法子，动作固定成同一套 ——
            # 收拢、守缺，等当世那一位来杀他、接下负担再开一轮。于是必然徒劳。
            emit(frame, "ATTEMPT_VAIN", dict(burden(frame), cycle=cycle, stage=stage_id,
                                             approach=cap, routine=True,
                                             ordinal=frame - deadlock["epoch"] + 1))
            return False

        # 窄门：另起一条独立子流，抽一个真正摊开的读数。
        # （不能直接切 h 的高位：mix 是 FNV 式的乘法混淆，相邻 cycle 的高位几乎不变，
        #   拿它当骰子等于掷不动的骰子。交给 numpy 的生成器把种子摊匀。）
        roll = float(np.random.default_rng(mix(seed, 0x60D3, cycle)).random())
        if roll >= trace_chance:
            emit(frame, "ATTEMPT_VAIN", dict(burden(frame), cycle=cycle, stage=stage_id,
                                             approach=cap, ordinal=frame - deadlock["epoch"] + 1))
            return False

        target = [(h >> 17) % len(st.register.slots)]
        payload = {}
        if cap == "modify_operator":
            # 「去动那根权杖本身」：给世界拨一个谁也不读的开关 —— 结构上留痕，
            # 演算上毫无差别。他改得了规则的名字，改不了规则做的事。
            payload = {"enable": "OP_SEAL_%d" % (h % 8)}
        trial = st.clone()
        fn(trial, ctx_run, payload, target, frame)     # 行使能力（方向 + 方法）
        # 循环里世界是【原地重演】，并没有真的过掉这几千万帧。试算也必须按循环
        # 起点的时计走：否则算子会拿当前的真实帧号去算年龄，全体在一瞬间集体
        # 寿终，席位随之为本因子后生者腾位 —— 那十二位便「死」了一回。
        t0 = int(deadlock["start"])
        for k in range(attempt_span):              # 真演算：在克隆上走若干帧
            rng = np.random.default_rng(mix(seed, 0xA771, cycle, 0xA5, k))
            for idx, op in enumerate(ops):
                op.apply(trial, ctx_run, rng, t0 + 1 + k)
        dist = world_distance(trial.world_signature(), deadlock["ref"])
        if dist < trace_delta:                     # 徒劳：世界纹丝不动
            emit(frame, "ATTEMPT_VAIN", dict(burden(frame), cycle=cycle, stage=stage_id,
                                             approach=cap, ordinal=frame - deadlock["epoch"] + 1))
            return False
        keep_seats = st.register                    # 这一轮的血案会被回退
        st.copy_world_from(trial)                   # 留痕：世界被挪动了一线
        st.register = keep_seats                    # 只是「谁坐哪一席」不跟着留痕走
        st.traces += 1
        emit(frame, "ATTEMPT_TRACE", dict(burden(frame), cycle=cycle, stage=stage_id,
                                          approach=cap, ordinal=frame - deadlock["epoch"] + 1))
        return True

    def _open_deadlock(frame, start, ref):
        """按【绝对帧锚】建立一次循环的运行期状态。

        落点（抑制 / 刻度）一律锚定在 start 上，而不是「检测到循环的那一帧」——
        于是无论从哪一帧续跑，重建出的调度都与全程完全一致（帧可复现）。
        """
        span = frame - start
        tick_i = 0
        while tick_i < len(ticks) and ticks[tick_i] <= span:
            tick_i += 1
        # epoch = 【进入循环那一帧】= 结构冻结起点 + freeze_dwell：判定恰在 freeze_run
        # 首次达到 freeze_dwell 那一帧发生，故它**能从 start 推出来**。
        #   —— 这里必须【推】而不是取调用时的 frame：续跑时 `_open_deadlock(n, anchor, …)`
        #   的 n 是"续跑的那一帧"，取 frame 会让 epoch 偏大、轮回序号与账本读数（seeds）
        #   整段偏小，与从头跑不一致。而 digest / world_signature 都不含这些读数，单测与
        #   指纹都照不出来 —— 只能靠推导保证（判据 4 的帧截断复现已覆盖此路径）。
        return {"start": start, "ref": ref, "epoch": start + freeze_dwell,
                "last_attempt": start + (span // attempt_period) * attempt_period,
                "cycle": int(st.attempts), "tick_i": tick_i}

    def _apply_seeds(frame):
        """循环期的账本读数：取得量（seeds）随轮回累积。

        自进入循环那一帧（epoch）起，世界每过一帧即过一轮，每轮再收满一次——
        故累积量 = 位数 × 已过轮数。

        数值【锚定在 epoch 上】（而不是逐次 += 累加），于是续跑与从头跑逐帧一致；
        也不进任何摘要 / 签名，只是账本读数。
        """
        if deadlock is None:
            return
        st.seeds = len(st.register.slots) * max(1, int(frame) - int(deadlock["epoch"]))

    # 续跑时用存档自身的结构签名作为「上一帧」，保证首个续跑帧的周期检测与全程一致
    prev_sig = st.world_signature() if start_frame > 0 else None
    # 异常死循环的运行期状态：None = 常规演化；非 None = 世界结构已冻结。
    deadlock = None
    freeze_run = 0        # 结构已【连续】与上一帧相同的帧数
    last_stalled = False
    last = {"codes": (), "prom": 0, "dom": 0, "conv": False, "solver": st.solver,
            "exhausted": False,
            "owners": tuple(s.owner for s in st.register.slots)}
    announced = set()     # 已播报过的 persist 扰动（按记录身份去重）
    before_overrides = dict(st.overrides)   # 覆盖表快照：变更即播报（只读，不改状态）
    vacant_run = [0] * len(st.register.slots)   # 每一席已连续空置的帧数（判「真空缺」）

    def _rebase_ages(frame, start):
        """循环期间世界只是【原地重演】，并没有真正变老 —— 走出时把这段帧数从年龄里扣掉。

        不这么做，跳过的三千多万帧会在走出那一瞬把所有个体一次性「变老」，
        引发大灭绝：席位集体换人，最后一次再创世也就不是原来那十二位了。
        """
        span = int(frame) - int(start)
        if span > 0:
            # 只改【确实出生过】的位置：born 兼作「是否有过」的标记，别把空位也算进去。
            used = st.pool.alive | (st.pool.born > 0)
            st.pool.born[used] += span

    def _deadlock_step(frame):
        """循环的一帧：先判退出（世界被外生扰动撬动），再发尝试与刻度。

        返回 True 表示这一帧【走出了循环】。它不改世界一个比特 —— 尝试只在克隆上
        真演算，没能留下结构差异就丢弃；留下了才提交。观测者不是参与者。
        """
        nonlocal deadlock, prev_sig, freeze_run, last_stalled
        _apply_seeds(frame)                 # 账本读数：取得量随轮回累积（锚定 epoch）
        sig_now = st.world_signature()
        if sig_now != deadlock["ref"]:
            # 外生扰动撬动了结构 —— 内部永远做不到，只有外部可以。
            _rebase_ages(frame, deadlock["start"])
            emit(frame, "DEADLOCK_END", dict(burden(frame),
                                             length=frame - deadlock["start"],
                                             cycle=frame - deadlock["epoch"] + 1))
            traj.spans.append(("deadlock", deadlock["start"], frame))
            deadlock = None
            st.deadlock_anchor = 0
            prev_sig = sig_now
            freeze_run = 0
            last_stalled = False
            return True

        # 尝试落点：承载者的一次真实出手（落点锚定在 start 上，续跑后逐帧一致）。
        if frame - deadlock["last_attempt"] >= attempt_period:
            deadlock["last_attempt"] = frame
            if _attempt(frame):
                deadlock["ref"] = st.world_signature()

        # 等待的刻度：几何级数展开，纯渲染（删掉这段，演算结果逐帧不变）。
        # cycle 报【轮回序号】：自进入循环那一帧（epoch）起算第 1 轮，世界每过一帧即一轮。
        # 它与「尝试」不是一回事 —— 尝试另有节拍（attempt_period）。
        if (deadlock["tick_i"] < len(ticks)
                and frame >= deadlock["start"] + ticks[deadlock["tick_i"]]):
            tv = ticks[deadlock["tick_i"]]
            deadlock["tick_i"] += 1
            emit(frame, "DEADLOCK_TICK", dict(burden(frame),
                                              cycle=frame - deadlock["epoch"] + 1,
                                              elapsed=tv))
        return False

    while n < total:
        if iter_cap is not None and traj.iterations >= int(iter_cap):
            traj.truncated = True
            break

        # ㊀ 续跑重建：存档若带着循环锚（≠0），立刻恢复循环（不改世界一个比特）。
        #     放在最前，确保续跑的首帧也直接走循环分支、不被当成常规帧记进捕获 ——
        #     这正是帧截断复现能跨异常区成立的原因。
        if deadlock is None and st.deadlock_anchor:
            deadlock = _open_deadlock(n, int(st.deadlock_anchor), st.world_signature())
            traj.deadlock = True
            last_stalled = True

        # ⓪ 裁决即终止：命题已可判定 ⇒ 实验坍缩为「结束」。
        #    终止条件不是"跑够多少次"，而是"能不能下结论"。
        if n > int(start_frame):
            # 判据表每帧只求值一次，里程碑与裁决共用（外生改写已并入 —— 否则
            # 结论链只停在"结论二"，看不到最后那一改）。
            inner, ascends = evaluate(st, ctx_run, last_stalled)
            # 结论里程碑：只记录、只播报，不改状态、不终止（与 DEADLOCK_TICK 同性质）。
            if inner is not None and inner != traj.conclusion_seen:
                traj.conclusion_seen = inner
                traj.conclusion_trail.append((n - 1, inner))
                emit(n - 1, "CONCLUSION_REACHED", {
                    "conclusion": inner,
                    "id": cfg.conclusions[inner]["id"]})

            # 外生干预未穷尽之前一律不下结论 —— 下一次干预可能重新打开刚被证伪的位。
            # （实测：同一个世界里「全部位已证伪」会先出现两次，都被后续干预重新打开；
            #   只有最后一次是终局。）
            if inner is not None and data.next_onset(n - 1) is None and not pending:
                traj.verdict = inner
                traj.verdict_frame = n - 1
                # 停因就是裁决枚举的大写形式 —— 它只是「为什么停下」的短码，
                # 长句由配置（conclusions.json 的 stop_label）给出，报告层不写死。
                traj.stop_reason = str(inner).upper()
                if deadlock is not None:
                    _rebase_ages(n - 1, deadlock["start"])
                    _apply_seeds(n - 1)     # 走出循环那一帧的账本读数（锚定 epoch）
                    emit(n - 1, "DEADLOCK_END", dict(burden(n - 1),
                                                     length=(n - 1) - deadlock["start"],
                                                     cycle=(n - 1) - deadlock["epoch"] + 1))
                    traj.spans.append(("deadlock", deadlock["start"], n - 1))
                    deadlock = None
                    st.deadlock_anchor = 0
                emit(n - 1, "VERDICT", {"verdict": inner})
                if ascends:
                    # 未被改写的终局结论（判据表里标了 ascends）⇒ 演算主体升格，产物外溢。
                    traj.ascended = True
                    emit(n - 1, "ASCENSION", {"conclusion": inner})
                break

        # ⓪' 外部观察钩子：只读判定，用来提前毙掉明显不合的轨道（安全阀，不改语义）。
        if watch is not None and not watch(n, st, traj):
            traj.truncated = True
            traj.stop_reason = "PRUNED"
            break

        traj.iterations += 1

        # ① 外部扰动：程序不区分是谁，只按能力分发。
        #    persist 的记录每帧都会被重新投递（效果照旧），但只在【首次】播报 ——
        #    否则一条长驻扰动会把编年史刷成一堵墙（它已经在施加效果，不必重复宣告）。
        # ①' 带条件的投递：声明帧已过、且条件此刻成立，才触发。没有 when 时 `pending`
        #     为空 ⇒ 这段一步都不走，逐帧开销为零，与加入之前逐位相同。
        due = []
        if pending:
            obs = obs_now(n)
            for rec in list(pending):
                if int(rec["frame"]) <= n and rules(rec["when"], obs):
                    pending.remove(rec)
                    due.append(rec)
        for rec in data.at(n) + due:
            _, fired = dispatch(rec, st, ctx_run, n)
            if not fired:
                continue
            # 事件名在这里收：它在【投递记录】上（`payload.event`），不在播报载荷里。
            # `event("X")` 这类条件读的就是"这个事件发生过没有"。
            ev = (rec.get("payload") or {}).get("event")
            if ev is not None:
                seen_events.add(str(ev))
            if rec.get("payload", {}).get("persist"):
                key = id(rec)
                if key in announced:
                    continue
                announced.add(key)
            emit(n, "DISTURBANCE", {
                "channel": rec.get("channel"),
                "capability": rec["capability"],
                "selector": (rec.get("selector") or {}).get("expr"),
                "label": rec.get("label"),
            })
        # 覆盖表若被外生实体改写，逐条播报 —— 观测者只读，不改状态一个比特。
        if st.overrides != before_overrides:
            emit(n, "PROTOCOL_REWRITTEN", {
                "changed": {k: st.overrides[k] for k in st.overrides
                            if before_overrides.get(k) != st.overrides[k]},
                "rules": sorted(st.overrides)})
        before_overrides = dict(st.overrides)
        # 规则覆盖表的【生效点】：「演算方向」这条规则被读到即生效 —— 覆写逻辑的落点。
        # （另一条规则 promotion.mode 由 Promotion 算子自行读取。）
        if "solver.direction" in st.overrides:
            st.solver = str(st.overrides["solver.direction"])

        # ⑤' 异常死循环：世界结构已冻结 ⇒ 沿参考轨道复用（不再逐帧重算算子）。
        #     观测者【不改状态一个比特】：它只在几何刻度上留下"等待"的读数，
        #     并按周期发起一次【真实】尝试。内部永远走不出去，只有外生扰动可以。
        #     reuse_reference=False 时不做跳跃、世界逐帧真算 —— 仅供等价性检查。
        if deadlock is not None:
            ended = _deadlock_step(n)
            if reuse_reference:
                if ended:
                    n += 1
                    continue
                # 沿参考轨道复用：直接跳到下一个事件帧（复用帧数记入 skipped_frames）
                cand = total
                nxt = data.next_onset(n)
                if nxt is not None:
                    cand = min(cand, int(nxt))
                cand = min(cand, deadlock["last_attempt"] + attempt_period)
                if deadlock["tick_i"] < len(ticks):
                    cand = min(cand, deadlock["start"] + ticks[deadlock["tick_i"]])
                if pending:
                    # 还有挂起的条件投递 ⇒ 下一帧就可能成立，不能跳过去
                    cand = min(cand, n + 1)
                if cand <= n:
                    cand = n + 1
                traj.skipped_frames += cand - n
                # 循环期的到访帧也要进捕获：否则「帧截断复现」在复用区无从比对。
                if capture is not None:
                    capture.append((n, st.digest()))
                n = cand
                continue
            # reuse 关闭：本帧照常真算，落到下面的通用演化里。

        # 帧重放的复位点：取在扰动【之后】——外生干预不可被帧重放覆写（公理三）。
        # 只有配置里存在 REPLAY_SAME_FRAME 策略时才需要这份快照（它唯一的用途就是
        # 「原地重放」把世界退回帧首）。没有该策略时跳过深拷贝 —— 逐帧结果不变。
        snapshot = st.snapshot() if getattr(cfg, "needs_snapshot", True) else None

        # ② 通用演化：算子列表来自配置
        rng = np.random.default_rng(mix(seed, n))
        assembled = ()
        for idx, op in enumerate(ops):
            op.apply(st, ctx_run, rng, n)
            if cfg.pipeline[idx] == "OP_DOMAIN":
                # 阶段推进后【立刻装配】该阶段的机制（幂等；没配 stages ⇒ 无事发生），
                # 并把该阶段的参数覆盖绑进 ctx_run（其后本帧的算子看到的就是新参数）。
                assembled = _assemble(st, data)
                ctx_run.rebind(data.stage_params(_stage_index(st, data)))
            if cfg.pipeline[idx] == "OP_ENTROPY" and n % int(p["ablation_period"]) == 0:
                # 当前阶段的装配（门 + 参数覆盖）要进消融 —— 否则阶段机制对 progress 没有因果。
                # 探针实现由应用层交来（内核不认识"消融"）；它只写 locus.progress / progress2。
                si = _stage_index(st, data)
                runtime.probe(st, ctx_run, seed,
                              data.stage_gates(si), data.stage_params(si))

        # ③ 通用检查：遍历全称域，收集全部违例（检查器由应用层交来，内核不认识它们）
        violations = runtime.checks(st, ctx_run, n)
        for v in violations:
            traj.violation_counts[v.code] += 1

        # ④ 涌现登记：遍历全体个体（只写 Telemetry）
        for per in registrar.scan(st, n):
            emit(n, "EMERGENCE", registrar.describe(per))

        # ⑤ 调度：推进 / 终止 / 恢复，策略位置无关
        action = scheduler.decide(st, violations, ctx_run, n, snapshot)

        if trace or on_event is not None:
            codes = tuple(sorted({v.code for v in violations}))
            if codes != last["codes"]:
                emit(n, "VIOLATION_STATE", {"codes": codes})
                last["codes"] = codes
            if st.promotions != last["prom"]:
                emit(n, "PROMOTION", {"round": st.round, "clock": st.world_clock,
                                      "burden": burden(n)})
                last["prom"] = st.promotions
                last_prom_frame[0] = n
            if st.domain_index != last["dom"]:
                payload = {"index": st.domain_index,
                           "value": st.domain[min(st.domain_index, len(st.domain) - 1)]}
                if assembled:
                    payload["assembled"] = list(assembled)
                emit(n, "DOMAIN_ADVANCE", payload)
                last["dom"] = st.domain_index
            if st.domains_exhausted and not last["exhausted"]:
                emit(n, "DOMAINS_EXHAUSTED", {})
                last["exhausted"] = True
            if st.solver != last["solver"]:
                emit(n, "SOLVER_CHANGED", {"from": last["solver"], "to": st.solver})
                last["solver"] = st.solver
            if st.converged and not last["conv"]:
                emit(n, "CONVERGED", {"round": st.round})
                last["conv"] = True
            # 承位易主 / 失位 / 补位：换手双方【至少一方已经是登记过的角色】才入编年史。
            # 无名个体之间的流转是常态竞争，报出来只是噪声。判据只看 owner。
            # 补位另有门槛：空置【连续两帧以上】才算真空缺 —— 再创世那一瞬的清空—重占
            # 不算「有人接替」。
            owners = tuple(s.owner for s in st.register.slots)
            if owners != last["owners"]:
                known = registrar.registered
                for i, (was, now) in enumerate(zip(last["owners"], owners)):
                    if was == now:
                        continue
                    # 无名者之间的流转是常态竞争，不入编年史。但「失位 / 补位」两端里
                    # 只要有一端有名就照报 —— 点名与否由 L5 命名器说了算，引擎不替它判断
                    # （它只看得见「登记过没有」，看不见锚定层给谁点了名）。
                    if was is not None and now is not None and not (was in known or now in known):
                        continue
                    if was is None and vacant_run[i] < 2:
                        continue
                    emit(n, "SUCCESSION", {
                        "locus": cfg.loci[i].id, "from": was, "to": now,
                        "burden": burden(n)})
                last["owners"] = owners
            for i, o in enumerate(owners):
                vacant_run[i] = vacant_run[i] + 1 if o is None else 0

        st_next = action.next_state(st, snapshot)
        # 逐迭代摘要只在 capture 被提供时（帧截断复现等工具）才需要 —— 正常跑不必
        # 每帧把整个池哈希一遍，故只在真正要它的时候算。
        if capture is not None:
            capture.append((n, st_next.digest()))

        # ⑥ 周期检测 → 【异常观测器】
        #    世界结构与上一帧完全一致 ⇒ 结构此刻没有推进。但一两帧的重复是常态
        #    （竞争中的瞬时平衡），不足为凭：须【连续冻结 freeze_dwell 帧】才判定
        #    演算落入了设计之外的死循环。观测者不改变世界一个比特：它只记录这条
        #    异常，后续帧交给「沿参考轨道复用」处理。
        sig = st_next.world_signature()
        if prev_sig is not None and sig == prev_sig:
            freeze_run += 1
        else:
            freeze_run = 0
        # 额外前置：**变量域未穷尽不开循环**。
        #   永劫回归是【阶段四】的现象（wiki：第四阶段理论上的最后一次再创世被强行回退，
        #   才陷入死循环）。而"结构暂时不推进"在前几档是常态 —— 尤其某档的机制还没装配
        #   到能改变结构的东西时（例：再创世是阶段三才装的），世界会**早早冻结**；
        #   若就此判成死循环，帧被跳过、帧基阶段时钟随之饿死，
        #   那一档的门便永远开不了 —— 循环把自己锁死在自己的入口之前。
        if deadlock is None and freeze_run >= freeze_dwell and st_next.domains_exhausted:
            traj.deadlock = True
            st.cycles += 1
            start = n - freeze_run
            st_next.deadlock_anchor = start    # 进存档：续跑据此重建循环
            deadlock = _open_deadlock(n, start, sig)
            last_stalled = True
            # vacant = 空着的位次；vacant_loci = 它们的位置编号（渲染层据此点名「哪一席」）；
            # cycle = 轮回序号（进入循环那一帧即第 1 轮）；start = 结构冻结的那一帧
            # （= 复用区间的起点，渲染层据此把"重放的时间"从历法里扣掉）。
            emit(n, "DEADLOCK_LOOP", dict(burden(n), cycle=1,
                                          start=start,
                                          vacant=_vacant(st_next),
                                          vacant_loci=[cfg.loci[i].id
                                                       for i in _vacant(st_next)]))

        prev_sig, st = sig, st_next
        n += 1

    if deadlock is not None:
        traj.spans.append(("deadlock", deadlock["start"], total))
        _apply_seeds(n - 1)   # 兜底路径也把账本读数对齐

    traj.reached_frame = n - 1
    traj.final = st
    traj.personas = registrar.personas
    traj.total_frames = total
    traj.converged = bool(st.converged)

    # 若没在演算中被裁决，就按走到最后的那个状态给一个结论 —— 并标明这只是"走完了预算"。
    # 这里的 stalled 取【真实的冻结点】（last_stalled），不是无条件置真：`stalled_and_exhausted`
    # 那条判据要的正是"结构真的冻结了"，而预算耗尽 ≠ 结构冻结 —— 一个跑满预算、变量域
    # 已穷尽、却仍在演化的世界，应落「未决」而非「证伪」。
    if traj.verdict is None:
        traj.verdict = (inner_conclusion(st, ctx_run, last_stalled) or "undecided")
    if ascends_of(ctx_run, traj.verdict) and not traj.ascended:
        # 兜底路径也要记升格：未被改写的世界困在循环里、预算耗尽才收场，
        # 走不到 ⓪ 的判决分支，所以补一次 ASCENSION。
        traj.ascended = True
        emit(traj.reached_frame, "ASCENSION", {"conclusion": traj.verdict})
    if traj.stop_reason is None:
        traj.stop_reason = "ITER_CAP" if traj.truncated else "BUDGET"
    traj.conclusion = cfg.conclusions[traj.verdict]
    return traj