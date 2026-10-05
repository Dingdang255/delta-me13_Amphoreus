"""L0/L1：状态容器。

零领域知识——不知道位叫什么，也不知道谁是谁。
"""
from __future__ import annotations

import hashlib
import numpy as np


def mix(*parts) -> int:
    """FNV 式混合：把几个整数（seed / 序号 / 因子标签…）压成一个 64 位整数。

    纯函数、无状态 —— 「同一组输入派生同一个 rng」这条可复现性就建立在它上面。
    原先 `core.py` 与 `ablation.py` 各抄了一份**逐字相同**的实现，统一到这里，
    免得两边哪天各改一半。
    """
    h = 0x9E3779B97F4A7C15
    for p in parts:
        h = (h ^ (int(p) & 0xFFFFFFFFFFFFFFFF)) * 0x100000001B3 & 0xFFFFFFFFFFFFFFFF
    return h


#: 初始演算方向。
DEFAULT_SOLVER = "OP_SOLVE_ENTROPY"

#: 墓碑的【死因】封闭集合 —— 由调用点给出（见 `State.bury`）。都是通用词，不含专名。
DEATH_CAUSES = ("aged", "isolated", "homogenized", "dethroned",
                "evicted", "displaced")
#: 「外生干预」类死因 —— 逐火之旅的伤亡就是它们。
EXTERNAL_CAUSES = ("evicted", "displaced")

#: 合法的「演算方向」名 —— 判据表（`verdict_rules[].require` 的 `solver`）与
#: genesis 的 `runtime.solver` 都引它。加一个方向 = 在这里补一项；名字写错过去会
#: 静默失效（判据恒不成立、方向比对恒为假），故 loader 据此在启动时校验。
#: 引擎里不出现「谁在用这些方向」的专有名词，只认这些通用名。
SOLVER_NAMES = (
    DEFAULT_SOLVER,
    "OP_SOLVE_DESTRUCTION",
    "OP_MEMORY_CONVERGE",
)


class Locus:
    """一个「位」。没有 name 字段；名字由 L5 命名器在渲染时事后赋予。"""

    __slots__ = ("id", "order", "capacity", "decay", "couplings", "progress",
                 "progress2", "load")

    def __init__(self, id: str, order: int, capacity: float, decay: float, couplings):
        self.id = id
        self.order = int(order)
        self.capacity = float(capacity)
        self.decay = float(decay)
        self.couplings = np.asarray(couplings, dtype=np.float32)
        # 反证法得出的【连续】进度：消融熵 / 消融阈值（≥ tau_falsify 即被证伪）。
        # 它是连续量，不是布尔量 —— 于是阈值 tau_falsify 是真的可调旋钮，
        # 渲染层也能读出「还差多少」而不只是「是 / 否」。
        self.progress = 0.0
        # 第二路探针（去耦口径）：同样的迷你世界与样本，只把位间耦合切断。
        # 「这一席能否独立驱动失序」因此有两个口径 —— 路 A 含耦合、路 B 无耦合。
        # 两路都不进 digest / world_signature，故不改轨迹（R3 只加读数）。
        self.progress2 = 0.0
        self.load = 0.0          # 当前承载量


class Slot:
    """一位当前的状态。"""

    __slots__ = ("locus_id", "value", "owner", "vector")

    def __init__(self, locus_id: str, dim: int):
        self.locus_id = locus_id
        self.value = 0.0
        self.owner = None                       # 承载者的 serial（不代表"角色名"）
        self.vector = np.zeros(dim, dtype=np.float32)

    def filled(self) -> bool:
        return self.owner is not None


class Register:
    __slots__ = ("slots",)

    def __init__(self, loci, dim: int):
        self.slots = [Slot(l.id, dim) for l in loci]

    def vacant(self):
        return [i for i, s in enumerate(self.slots) if not s.filled()]

    def complete(self) -> bool:
        return not self.vacant()


class AgentPool:
    """个体的存储。个体没有名字，只有编号、向量与标记。

    两张查找表（`index()` / `index_of_serial()`）带缓存：它们每帧被调用二十余次，
    而底层是容量级的线性扫描 —— 缓存后每帧只重建一两次，属于主要热点之一。
    缓存只在 alloc / kill 时作废，故是**纯查表**：取到的仍是同一批号、且 `index()`
    依旧按升序返回（涌现登记按此顺序定 rank，顺序一变，锚定编号就会变）。
    """

    def __init__(self, capacity: int, dim: int):
        self.dim = dim
        self.capacity = capacity
        self.alive = np.zeros(capacity, dtype=bool)
        self.vec = np.zeros((capacity, dim), dtype=np.float32)
        self.mem = np.zeros((capacity, dim), dtype=np.float32)
        self.has_mem = np.zeros(capacity, dtype=bool)
        self.born = np.zeros(capacity, dtype=np.int64)
        self.serial = np.zeros(capacity, dtype=np.int64)
        self.fitness = np.ones(capacity, dtype=np.float32)
        self.stable = np.zeros(capacity, dtype=np.int32)
        self.support = np.zeros(capacity, dtype=np.float32)
        self.held = np.zeros(capacity, dtype=bool)
        # 承位那一刻的 world_clock（-1 = 从未承位）。用于区分「本世的承位者」与
        # 「上一世留下的在位者」——逐火只夺后者的席。它只是账目，不进任何摘要/签名。
        self.seated_clock = np.full(capacity, -1, dtype=np.int64)
        self.factor = np.full(capacity, -1, dtype=np.int32)   # 原生因子（出生即定）
        self.tags = [set() for _ in range(capacity)]
        self._free = list(range(capacity - 1, -1, -1))
        self._next_serial = 0
        self._live = None          # 缓存：在生者的下标（升序）
        self._by_serial = None     # 缓存：编号 → 下标（只收在生者）

    # ---- 生命周期 ----------------------------------------------------
    def alloc(self) -> int:
        if not self._free:
            return -1
        i = self._free.pop()
        self.alive[i] = True
        self.serial[i] = self._next_serial
        self._next_serial += 1
        self.fitness[i] = 1.0
        self.stable[i] = 0
        self.support[i] = 0.0
        self.held[i] = False
        self.seated_clock[i] = -1
        self.has_mem[i] = False
        self.factor[i] = -1
        self.tags[i] = set()
        self._live = None
        self._by_serial = None
        return i

    def kill(self, i: int) -> None:
        if not self.alive[i]:
            return
        self.alive[i] = False
        self.held[i] = False
        self._free.append(i)
        self._live = None
        self._by_serial = None

    def index(self) -> np.ndarray:
        if self._live is None:
            self._live = np.flatnonzero(self.alive)
        return self._live

    def index_of_serial(self, serial: int) -> int:
        """编号 → 下标；查不到（或那一位已死）返回 -1。

        编号在 alloc 时由 `_next_serial` 单调发放，故在生者之间不会重复；
        死掉的位置可能还留着旧编号，但按「只收在生者」建表即可与线性扫描等价。
        """
        if self._by_serial is None:
            self._by_serial = {int(self.serial[i]): int(i) for i in self.index()}
        return self._by_serial.get(int(serial), -1)

    def __len__(self):
        return int(self.alive.sum())

    def clone(self):
        """只复制【会被算子改动】的部分；比 copy.deepcopy 快一个数量级。"""
        n = AgentPool.__new__(AgentPool)
        n.dim = self.dim
        n.capacity = self.capacity
        n.alive = self.alive.copy()
        n.vec = self.vec.copy()
        n.mem = self.mem.copy()
        n.has_mem = self.has_mem.copy()
        n.born = self.born.copy()
        n.serial = self.serial.copy()
        n.fitness = self.fitness.copy()
        n.stable = self.stable.copy()
        n.support = self.support.copy()
        n.held = self.held.copy()
        n.seated_clock = self.seated_clock.copy()
        n.factor = self.factor.copy()
        n.tags = [set(s) for s in self.tags]
        n._free = list(self._free)
        n._next_serial = self._next_serial
        # 查找表缓存【不随克隆带走】：克隆体自己按需重建（结果与源一致，且不会
        # 让两个体共享同一张会失效的表）。
        n._live = None
        n._by_serial = None
        return n


class State:
    """一帧的完整状态。"""

    # 判据表（params.verdict_rules）里 counter 允许引用的【账本计数】字段。
    # 它们都是可比的整数读数（单调累积或按帧记账）。loader 据此在启动时校验配置：
    # 名字写错的话，运行时 getattr(st, counter, 0) 会静默取 0 —— 那条判据恒不成立，
    # 却查不出原因。声明在此，是为了让「加计数字段」与「校验它」是同一处事实。
    COUNTER_FIELDS = ("destruction_events", "death_events", "promotions", "round",
                      "cycles", "attempts", "traces", "seeds")

    def __init__(self, loci, dim: int, observables: int, capacity: int, domain: list):
        self.dim = dim
        self.obs_dim = observables
        # 【深拷贝】位表，不持有调用方的对象 —— 演算会在 `locus` 上改结构位
        # （承载量等），若与 `cfg.loci` 共享引用，同一个 Config 上的第二次 run
        # 就会带着被上一次改烂的位表开始（**跨 run 污染**）。数值逐项相同，故轨迹不变。
        self.loci = [Locus(l.id, l.order, l.capacity, l.decay, l.couplings) for l in loci]
        self.pool = AgentPool(capacity, dim)
        self.register = Register(self.loci, dim)

        self.world_clock = 0            # 世界自己的钟（死循环时停驻）
        self.round = 0
        self.domain = list(domain)
        self.domain_index = 0
        self.domain_dwell = 0
        self.domains_exhausted = False
        # 初始变量取值对应的「世界失序度」——由 genesis 传入，参演反证法。
        # 数值索引与值名无关：换一份 domain 就换一套演化史。
        self.domain_disorder = []

        self.entropy = 0.0
        self.noise = 0.0
        self.observables_vec = np.zeros(observables, dtype=np.float32)
        self.rule_matrix = np.zeros((len(loci), dim), dtype=np.float32)

        self.gates = set()              # 被外部打开的机制
        self.solver = DEFAULT_SOLVER
        self.suppressed = set()         # 被压制的位
        self.memory_bank = np.zeros((0, dim), dtype=np.float32)

        self.promotions = 0
        self.promotion_dwell = 0
        self.promotion_cooldown = 0
        self.converged = False
        self.destruction_events = 0
        self.death_events = 0
        self.score = {}                 # 累加型通用指标，供断言核对

        # ---- 个体史（账本语义：只增不减、不随世界回滚、不进指纹）----------------
        # 引擎此前只把个体当【统计样本】：`kill()` 之后槽位立刻可被 `alloc()` 复用并覆盖
        # （serial / born / factor / stable / tags 全被重写），于是「谁死了、因何、被谁」
        # 在下一个补种之后就查不到了；而「谁从谁手里接的位」更是从未记录。
        # 这两样把它补上 —— 它们是**主轨道**的记录，`clone()` 一律不给：`snapshot()` 每帧
        # 都要克隆，拷几万条会拖垮演算；于是试算世界的历史也不会漏进主账本。
        self.tombstones = []            # [(帧, 编号, 因子, 死因, by), …]
        self.chronicle = {}             # 编号 -> {born, factor, from_serial, died, cause, by}

        # 外生变量对【结论】的改写（账本语义：永不随世界回滚，故不进 copy_world_from）。
        # 非空即表示：结论已被改写，不再取决于反证法的演算结果。
        self.conclusion_override = None

        # 外生实体对【规则】的改写（账本语义：永不随世界回滚，故不进 copy_world_from）。
        # 非空即表示：某些演算规则已被覆写，算子须据此换一条算法分支。
        self.overrides = {}
        # 外部实体表：{id: {"label", "grants", "state"}}（账本语义）。
        # 「谁在操作这个世界、各自握有哪些修改权限」由此成为登记过的真东西。
        self.actors = {}

        # ---- 账本 L：单调累积，是「记得」。世界 W 可回滚，账本永不回滚。
        self.attempts = 0               # 承载者发起的尝试次数（换法子算新的一次）
        self.cycles = 0                 # 进入异常死循环的轮次
        self.traces = 0                 # 真正挪动了世界的尝试次数（留痕）
        self.seeds = 0                  # 累计取得量：常规轮恒为满值，死循环期只增不减

        # 死循环的【锚】（0 = 未进入）。它进存档：续跑时据此重建循环，
        # 使尝试/刻度的落点成为「帧 + 状态」的纯函数 —— 帧截断复现因此成立。
        self.deadlock_anchor = 0

    # ---- 工具 --------------------------------------------------------
    def gate(self, name: str) -> bool:
        return name in self.gates

    def add_score(self, key: str, delta=1.0):
        self.score[key] = self.score.get(key, 0.0) + delta

    # ---- 个体史：出生 / 承位 / 死亡 ------------------------------------------
    def born(self, frame: int, k: int):
        """登记一个新生个体。**必须存进账本** —— pool 的槽位随后会被复用覆盖。"""
        self.chronicle[int(self.pool.serial[k])] = {
            "born": int(frame), "factor": int(self.pool.factor[k]),
            "from_serial": None, "died": None, "cause": None, "by": None,
        }

    def inherit(self, new_serial: int, old_serial: int):
        """承位：记下【新主人是从谁手里接的这一席】—— 引擎里真实存在的传承关系。

        （`_pilgrimage` 的「弑：退位者陨落」是它唯一的来源：本世的承位者顶掉上一世
        留下的在位者。出生谱系则**不记** —— 新生是凭空取样，没有父代可言。）
        """
        rec = self.chronicle.get(int(new_serial))
        if rec is not None:
            rec["from_serial"] = int(old_serial)

    def bury(self, frame: int, k: int, cause: str, by=None):
        """记一块墓碑，并给那个体的生平封笔。

        死因由【调用点】给出 —— 引擎里"怎么死的"只有那里知道。取值都是通用词：
        `aged` 寿终 / `isolated` 被孤立 / `homogenized` 被同化 / `dethroned` 被夺席 /
        `evicted` 被逐出 / `displaced` 为接掌者让位。`by` 记施术者（池中编号，
        或外生实体的 id），环境性的死记 None。
        """
        serial = int(self.pool.serial[k])
        self.tombstones.append((int(frame), serial, int(self.pool.factor[k]),
                                str(cause), by))
        rec = self.chronicle.get(serial)
        if rec is not None:
            rec["died"] = int(frame)
            rec["cause"] = str(cause)
            rec["by"] = by

    def digest(self) -> str:
        h = hashlib.blake2b(digest_size=16)
        idx = self.pool.index()
        if idx.size:
            q = np.rint(self.pool.vec[idx] * 4096).astype(np.int32)
            h.update(q.tobytes())
            h.update(np.sort(self.pool.serial[idx]).astype(np.int64).tobytes())
        h.update(bytes(int(s.owner is not None) for s in self.register.slots))
        h.update(bytes(sorted(self.suppressed)))
        h.update(bytes(str(sorted(self.gates)), "utf-8"))
        h.update(bytes(str((self.round, self.domain_index, self.solver)), "utf-8"))
        h.update(bytes(str(round(self.entropy, 6)), "utf-8"))
        # 会门控【真实跃迁】的累加计数器也必须进摘要：若把它们漏掉，
        # 「再创世」的驻留帧会被误判成不动点而被周期跳跃跳过，跃迁永不发生。
        h.update(bytes(str((self.promotions, self.promotion_dwell,
                            self.promotion_cooldown, self.converged)), "utf-8"))
        return h.hexdigest()

    def world_signature(self):
        """结构级【可比较】签名：以元组而非哈希给出，因而可以逐位求差
        （用于判定一次尝试「留痕」的幅度是否 ≥ δ）。

        账本类【单调累加】量刻意不进这里：一旦纳入，签名永不重复，死循环无从
        检测。个体向量也不进 —— 它们在死循环里仍在逐帧漂移，那是「世界在变」，
        不是「结构在变」。

        位占用与压制集合按位展开成 0/1，其余是标量；world_distance() 逐位比对。

        被压制的位一律记作【空】：压制是「这一席此刻无人在位」。名册里可能还留着
        原主（死循环期的留痕只挪世界、不带走谁坐哪一席），那是账面，不是当下的结构 ——
        若把留着的原主算成「在位」，同一刻逐帧真跑（算子会当场清空受压的席）就会与
        复用期算出两个不同的签名，复用等价性便无从谈起。
        """
        occ = tuple(1 if (s.owner is not None and i not in self.suppressed) else 0
                    for i, s in enumerate(self.register.slots))
        sup = tuple(1 if i in self.suppressed else 0
                    for i in range(len(self.register.slots)))
        return occ + sup + (
            tuple(sorted(self.gates)), self.solver,
            int(self.domains_exhausted), int(self.converged),
            int(self.promotions), int(self.promotion_dwell),
            int(self.promotion_cooldown), int(self.round),
            int(self.world_clock), int(self.domain_index))

    def copy_world_from(self, other):
        """只把【世界 W】搬过来；账本（轮次 / 尝试 / 得分 / 取得量 / 轮回计数）留在原地。

        用于把一次「留痕」的试验世界提交进主轨道。**这是刻意的世界 / 账本分界**：
        世界可回滚，账本永不回滚（见 `core.run` 的状态拆分约定）。故这里搬
        `pool / register / entropy / noise / observables_vec / rule_matrix / gates /
        solver / suppressed / memory_bank / domain* / converged / promotion_*`，
        而 `round / promotions / attempts / traces / seeds / score / world_clock` 不动。
        于是「留痕」只挪世界、不动已记账的轮次与尝试 —— 两者此后可以不一致，那是
        账本语义，不是错位。
        """
        self.pool = other.pool.clone()
        reg = Register(self.loci, self.dim)
        for i, s in enumerate(other.register.slots):
            t = reg.slots[i]
            t.value = s.value
            t.owner = s.owner
            t.vector = s.vector.copy()
        self.register = reg
        self.entropy = other.entropy
        self.noise = other.noise
        self.observables_vec = other.observables_vec.copy()
        self.rule_matrix = other.rule_matrix.copy()
        self.gates = set(other.gates)
        self.solver = other.solver
        self.suppressed = set(other.suppressed)
        self.memory_bank = other.memory_bank.copy()
        self.domain = list(other.domain)
        self.domain_index = other.domain_index
        self.domain_dwell = other.domain_dwell
        self.domains_exhausted = other.domains_exhausted
        self.converged = other.converged
        self.promotion_dwell = other.promotion_dwell
        self.promotion_cooldown = other.promotion_cooldown

    def snapshot(self):
        return self.clone()

    def clone(self):
        n = State.__new__(State)
        n.dim = self.dim
        n.obs_dim = self.obs_dim
        n.loci = [Locus(l.id, l.order, l.capacity, l.decay, l.couplings) for l in self.loci]
        n.pool = self.pool.clone()
        n.register = Register(n.loci, self.dim)
        for i, s in enumerate(self.register.slots):
            t = n.register.slots[i]
            t.value = s.value
            t.owner = s.owner
            t.vector = s.vector.copy()
        n.world_clock = self.world_clock
        n.round = self.round
        n.domain = list(self.domain)
        n.domain_index = self.domain_index
        n.domain_dwell = self.domain_dwell
        n.domains_exhausted = self.domains_exhausted
        n.domain_disorder = list(self.domain_disorder)
        n.entropy = self.entropy
        n.noise = self.noise
        n.observables_vec = self.observables_vec.copy()
        n.rule_matrix = self.rule_matrix.copy()
        n.gates = set(self.gates)
        n.solver = self.solver
        n.suppressed = set(self.suppressed)
        n.memory_bank = self.memory_bank.copy()
        n.promotions = self.promotions
        n.promotion_dwell = self.promotion_dwell
        n.promotion_cooldown = self.promotion_cooldown
        n.converged = self.converged
        n.destruction_events = self.destruction_events
        n.death_events = self.death_events
        n.score = dict(self.score)
        n.attempts = self.attempts
        n.cycles = self.cycles
        n.traces = self.traces
        n.seeds = self.seeds
        n.deadlock_anchor = self.deadlock_anchor
        n.conclusion_override = self.conclusion_override
        n.overrides = dict(self.overrides)
        n.actors = {k: {"label": v.get("label", ""),
                        "grants": tuple(v.get("grants") or ()),
                        "state": dict(v.get("state") or {})}
                    for k, v in self.actors.items()}
        # 个体史是【主轨道】的记录：克隆体从零开始（见 __init__ 的说明）。
        # 必须显式给 —— `clone` 走的是 `__new__`，绕过 `__init__`。
        n.tombstones = []
        n.chronicle = {}
        return n


def world_distance(a, b) -> int:
    """两个结构签名之间【不同位的个数】—— δ 判据就是拿它和 trace_threshold 比。"""
    return sum(1 for x, y in zip(a, b) if x != y)