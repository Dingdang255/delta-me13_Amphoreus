"""内核的系统调用 —— 冻结为 8 个，带版本号 `v1`。

    load(machine_spec) -> Session       用【机器规格】建一个世界
    session.step(n) -> FrameReport      推进 n 帧（含死循环分支、参考轨道复用）
    session.snapshot() / restore(h)     存档 / 读档
    session.inject(disturbance)         投递【外生】扰动 —— 唯一能打破闭环的入口
    session.observe() -> Metrics        【只读】指标快照
    session.events() -> EventStream     事件流（`emit()` 的消费侧）
    session.capabilities() -> dict      声明可用算子 / 权限
    version() -> str                    内核接口版本，供应用做兼容判断

**为什么是这 8 个、且不许再长**：见 `docs/adr/0001-内核接口冻结与版本纪律.md`。
想加第 9 个之前，先回答"为什么现有 8 个组合不出来"，并把答案写成一页 ADR。

本模块是**薄**的一层：主循环仍然是 `core._advance`，这里只做「把一次运行拆成
可寻址的会话」，演化语义一个比特都不加。于是 `core.run()` 退化成
`load(...).step(...)` 的组合，而不是第二套实现。

它不 import 服务层（裁决 / 消融 / 断言 / 命名 / 渲染），一行都不 —— 那些东西由
应用层通过 `runtime` / `namer` / `rules` 这几个**不透明句柄**交进来。
"""
from __future__ import annotations

from .core import StageCtx, _advance, _stage_index, initial_state
from .disturbance import CAPABILITIES
from .loader import Config, DataSet, ROOT
from .state import DEATH_CAUSES

#: 内核接口版本。破坏性变更必须升 major，并写进 `CHANGELOG.md`（见 ADR-0001）。
API_VERSION = "1"


def version() -> str:
    """内核接口版本。应用据此判断自己能跑在哪个内核上。"""
    return API_VERSION


class EventStream:
    """事件流：`emit()` 的只读消费侧。

    每条记录是 `(frame, kind, payload)` —— 引擎的**唯一**输出出口（见 core.emit）。
    它只读：改它不改世界，删它也删不掉已经发生的事。
    """

    __slots__ = ("records",)

    def __init__(self, records=()):
        self.records = records

    def __iter__(self):
        return iter(self.records)

    def __len__(self):
        return len(self.records)

    def __getitem__(self, i):
        return self.records[i]

    def kinds(self) -> list:
        """出现过的事件类型（按首次出现次序）。"""
        out = []
        for _frame, kind, _payload in self.records:
            if kind not in out:
                out.append(kind)
        return out


class Snapshot:
    """一份存档：世界 + 账本 + 事件流长度 + 待触发的条件投递。

    「**世界可回滚，账本不回滚**」这条分界写在 `State.copy_world_from` 上；
    存档只是把当前这一刻原样封起来（见 `State.snapshot`）。

    `armed` 是「带 `when` 的投递里还没触发的那几条」—— 读档要把它一并带回来，
    否则读档会把已经触发过的条目重新武装，同一条投递在一次运行里触发两次。
    """

    __slots__ = ("state", "frame", "events", "armed")

    def __init__(self, state, frame, events, armed=None):
        self.state = state
        self.frame = int(frame)
        self.events = int(events)
        self.armed = None if armed is None else list(armed)

    def __repr__(self):
        return f"<Snapshot 帧 {self.frame:,} · 世界 {self.state.digest()[:12]}>"


class Session:
    """一个活着的世界。8 个系统调用里除 `version()` 外的 7 个都挂在它身上。

    **它是薄的**：不缓存演化中间量、不重写主循环，只持有"世界现在在哪一帧"
    与"应用交来的那几个不透明句柄"。

    `step()` 可以被调用多次（分几段推进）。**世界状态是逐帧精确的** —— 续跑走的
    正是判据 4（帧截断复现）那条被证明过的路径：`start_state` + `start_frame`。
    但**事件流是按段拼接的**：接缝那一帧，少数【状态派生】的复述
    （`VIOLATION_STATE` / `CONCLUSION_REACHED` / 重新扫出来的 `EMERGENCE`）可能
    再报一次 —— 它们是「此刻是什么样」的复述，不是「又发生了一次」。
    要一段严丝合缝的事件流，就一次跑完（`step(None)`）。
    """

    __slots__ = ("_cfg", "_data", "_seed", "_runtime", "_namer", "_rules",
                 "_trace", "_capture", "_iter_cap", "_watch", "_on_event",
                 "_inbox", "_state", "_frame", "_traj", "_armed", "_live")

    def __init__(self, cfg, data, *, seed=None, runtime=None, namer=None, rules=None,
                 trace=True, capture=None, iter_cap=None, watch=None, on_event=None,
                 start_state=None, start_frame=0, inbox=None):
        self._cfg = cfg
        self._data = data
        self._runtime = runtime
        self._namer = namer
        self._rules = rules
        self._trace = bool(trace)
        self._capture = capture
        self._iter_cap = iter_cap
        self._watch = watch
        self._on_event = on_event
        # 外部中断收件箱：`inject()` 往这里投，主循环在到期帧取走。
        # **空箱时主循环一个分支都不多走** ⇒ 与没有它逐位相同。
        self._inbox = list(inbox) if inbox else []
        # 种子口径与主循环逐字相同（预设种子 > 机器规格种子 > 0）。
        if seed is None:
            seed = data.preset.get("seed")
            if seed is None:
                seed = data.genesis.get("seed", 0)
        self._seed = int(seed)
        self._state = start_state
        self._frame = int(start_frame)
        self._traj = None
        # 带 `when` 的投递的【待触发清单】：**懒取**一份 `data.conditioned` 的副本。
        # 交给主循环的是【这个列表本身】——它每触发一条就从中删掉一条，于是分几段
        # `step()` 时已触发的条目不会被重新武装（一次运行里每条只触发一次）。
        self._armed = None
        # 本帧的【活状态镜像】`(世界, 轨迹)`，仅在 `step()` 执行期间非 None。
        # 见 `_watch_frame` / `observe()`。
        self._live = None

    # ---- 状态 -----------------------------------------------------------------
    @property
    def frame(self) -> int:
        """下一帧要走的帧号（= 已经走过的最后一帧 + 1）。"""
        return self._frame

    @property
    def state(self):
        """当前世界。**只读**：要改它，请走 `inject()`（外生扰动是唯一入口）。"""
        return self._ensure_state()

    @property
    def report(self):
        """最近一次 `step()` 的 FrameReport（一次都没跑过时为 None）。"""
        return self._traj

    def _ensure_state(self):
        """还没跑过就先摆好第 0 帧的世界（与主循环的建世界逐字同一段逻辑）。"""
        if self._state is None:
            ctx = StageCtx(self._cfg)
            st = initial_state(ctx, self._data, self._seed)
            ctx.rebind(self._data.stage_params(_stage_index(st, self._data)))
            self._state = st
        return self._state

    def _armed_list(self):
        """待触发的条件投递（懒取一份副本；之后用的都是**这同一个列表**）。"""
        if self._armed is None:
            self._armed = list(getattr(self._data, "conditioned", ()) or ())
        return self._armed

    def _watch_frame(self, frame, st, traj):
        """内核每帧回调的**只读镜像**：记下这一帧的 `(世界, 轨迹)`，再转交用户 `watch`。

        为什么要镜像：反应式订阅（`apps/script.py`）的条件是在**事件回调里**求值的，
        而事件发生在帧中途 —— 那时 `self._state` 还停在本次 `step()` 的起点。
        内核的 `watch(n, st, traj)` 拿到的 `st` / `traj`，正是它自己算 `obs_now(n)`
        和 `registrar.personas` 时看的**同一份对象** ⇒ 镜像它们，"应用的条件"读到的
        观测量与"预设的 `when`"读到的就是同一帧的同一口径。

        它只读：不碰世界、不推进任何东西；用户没给 `watch` 时恒返回 True（不停下）。
        """
        self._live = (st, traj)
        if self._watch is None:
            return True
        return self._watch(frame, st, traj)

    # ---- ② step ---------------------------------------------------------------
    def step(self, n=None):
        """推进 **最多** n 帧（`n=None` ⇒ 走满配置预算）。返回 FrameReport。

        终止条件不是"跑够 n 帧"，而是【命题能否裁决】：中途可判定就按裁决停下。
        `n` 是**本次要推进的帧数**（相对量），不是绝对帧号 —— 于是
        `step(1000); step(1000)` 与 `step(2000)` 走到同一个世界状态。
        """
        if n is not None and int(n) < 0:
            raise ValueError("step(n) 的 n 不能为负（n=None 表示走满配置预算）")
        total = None if n is None else self._frame + int(n)
        report = _advance(
            self._cfg, self._data, seed=self._seed, max_frames=total,
            trace=self._trace, start_state=self._state, start_frame=self._frame,
            namer=self._namer, capture=self._capture, iter_cap=self._iter_cap,
            watch=self._watch_frame, on_event=self._on_event, rules=self._rules,
            runtime=self._runtime, inbox=self._inbox,
            conditioned=self._armed_list())
        self._absorb(report)
        return self._traj

    def _absorb(self, report):
        """把这一段的报告并进会话：世界/帧号取最新，事件流与计数按段累加。"""
        self._state = report.final
        self._live = None            # 活状态镜像只在 step() 执行期间有效
        self._frame = int(report.reached_frame) + 1
        if self._traj is None or self._traj is report:
            self._traj = report
            return
        t = self._traj
        t.records.extend(report.records)
        t.spans.extend(report.spans)
        t.iterations += report.iterations
        t.skipped_frames += report.skipped_frames
        t.violation_counts.update(report.violation_counts)
        t.deadlock = bool(t.deadlock or report.deadlock)
        # 标量读数一律取最新那一段的（它们描述的是"此刻"，不是"累计"）。
        for name in ("total_frames", "reached_frame", "final", "personas", "converged",
                     "verdict", "verdict_frame", "stop_reason", "conclusion",
                     "conclusion_seen", "conclusion_trail", "ascended", "truncated"):
            setattr(t, name, getattr(report, name))

    # ---- ③ snapshot / restore -------------------------------------------------
    def snapshot(self):
        """存档：封住此刻的世界（世界可回滚；账本按 `State.clone` 原样带走）。

        连「还没触发的条件投递」一并封存 —— 读档才能把世界与待触发清单一起倒回去。
        """
        return Snapshot(self._ensure_state().snapshot(), self._frame,
                        len(self._traj.records) if self._traj is not None else 0,
                        self._armed)

    def restore(self, h):
        """读档：回到存档那一刻。事件流一并截回存档时的长度（不重放已读过的段）。"""
        self._state = h.state.snapshot()      # 再克隆一份：读档不与存档共享可变状态
        self._frame = int(h.frame)
        self._armed = None if h.armed is None else list(h.armed)
        self._live = None
        if self._traj is not None and h.events < len(self._traj.records):
            del self._traj.records[h.events:]
        return self

    # ---- ④ inject -------------------------------------------------------------
    def inject(self, disturbance):
        """投递一条【外生】扰动 —— 对应"中断"。**这是唯一能打破闭环的入口**。

        世界自己永远走不出死循环（内部无法自证）；只有外部能撬动结构。
        不写 `frame` 时默认落在**下一帧**（`self._frame`），即"立刻"。
        返回归一后的那条记录（原样入箱，供调用方核对）。
        """
        rec = dict(disturbance or {})
        cap = rec.get("capability")
        if not cap:
            raise ValueError(
                "inject() 收到一条没有 capability 的扰动："
                "内核按能力分发，认不出能力就无处可投。")
        rec.setdefault("frame", self._frame)
        if not isinstance(rec["frame"], int) or isinstance(rec["frame"], bool) \
                or rec["frame"] < 0:
            raise ValueError(
                f"扰动帧应为非负整数，实为 {rec['frame']!r}"
                "（不给则默认落在下一帧）")
        rec.setdefault("channel", "world")
        rec.setdefault("payload", {})
        self._inbox.append(rec)
        return rec

    @property
    def inbox(self):
        """还没投递出去的外生扰动（只读副本）。"""
        return [dict(r) for r in self._inbox]

    # ---- ⑤ observe ------------------------------------------------------------
    def observe(self):
        """【只读】观测快照 —— **条件能读到的全部就是这些**（读不到的名字一律报错）。

        键名与内核主循环里那份**逐字相同**（见 `core._advance` 的 `obs_now`）：
        帧号 + 账本计数 + 席位占用 / 承载 / 寄存器 + 能力现身 + 已发生事件表。
        故"应用的条件"与"预设的 when"读的是同一门语言。

        它不碰世界一个比特，也不推进任何东西 —— 把接口调一万次，轨迹不动。

        两处口径说明：`frame` 取的是【会话当前帧】，在事件回调里求值时应用自己把它
        改成本次事件的帧（内核主循环也是这么构造的）；`personas` 取的是最近一次
        `step()` 记下的登记数，跑之前为 0。

        **在 `step()` 执行期间**（即事件回调里），这里读的是内核刚递来的那一帧的
        【活状态镜像】（见 `_watch_frame`）—— 与预设的 `when` 读到的是同一帧的同一份
        数，而不是"上一次 `step()` 结束时的世界"。`step()` 返回后镜像即失效。
        """
        live = self._live
        if live is not None:
            st, live_traj = live
            personas = len(live_traj.personas)
        else:
            st = self._ensure_state()
            personas = len(self._traj.personas) if self._traj is not None else 0
        obs = {"frame": int(self._frame), "promotions": int(st.promotions),
               "round": int(st.round), "domain_index": int(st.domain_index),
               "entropy": float(st.entropy), "noise": float(st.noise),
               "personas": personas,
               "deadlocked": 1 if st.deadlock_anchor else 0,
               # 已发生的事件名：`_emit` 与 dispatch 都会往 score 里落一个
               # `emitted_<事件名>` ⇒ 账本自己记得"哪些桥段真的执行过"。
               "events": {str(k)[len("emitted_"):] for k in st.score
                          if str(k).startswith("emitted_")}}

        filled, loads = 0, []
        for i, slot in enumerate(st.register.slots):
            lid = str(slot.locus_id).lower()
            has = 1 if slot.filled() else 0
            filled += has
            load = float(st.loci[i].load)
            loads.append(load)
            obs["seat_" + lid] = has
            obs["load_" + lid] = load
            obs["value_" + lid] = float(slot.value)
        obs["seats_filled"] = filled
        obs["seats_vacant"] = len(st.register.slots) - filled
        obs["load_max"] = max(loads) if loads else 0.0
        obs["load_min"] = min(loads) if loads else 0.0
        obs["load_span"] = (max(loads) - min(loads)) if loads else 0.0

        present = set()
        for k in st.pool.index():
            for t in st.pool.tags[int(k)]:
                if t.startswith("capability:"):
                    present.add(t.split(":", 1)[1])
        for cap in CAPABILITIES:
            obs["cap_" + str(cap)] = 1 if cap in present else 0

        # 账本：按死因分档的累计陨落数（墓碑只增，故直接数一遍即可，无需增量表）。
        tally = {}
        for t in st.tombstones:
            cause = str(t[3])
            tally[cause] = tally.get(cause, 0) + 1
        for cause in DEATH_CAUSES:
            obs["deaths_" + str(cause)] = int(tally.get(cause, 0))
        obs["deaths"] = int(sum(tally.values()))
        # 只读旁注（条件读不到它们 —— 不在 known_names 里）：世界摘要与账本。
        obs["digest"] = st.digest()
        obs["ledger"] = {"cycles": int(st.cycles), "attempts": int(st.attempts),
                         "traces": int(st.traces), "seeds": int(st.seeds),
                         "world_clock": int(st.world_clock)}
        return obs

    # ---- ⑥ events -------------------------------------------------------------
    def events(self):
        """事件流（`emit()` 的消费侧）。**一切对外可见之物都只能走这里。**

        一次都没跑过时是空流；`trace=False` 起跑的会话也是空流 —— 那表示
        "这一趟不留记录"，不是"什么都没发生"。
        """
        return EventStream(() if self._traj is None else tuple(self._traj.records))

    # ---- ⑦ capabilities -------------------------------------------------------
    def capabilities(self):
        """声明这台机器能做什么：可用算子 / 可投递能力 / 谁握有哪些权限。

        对应 OS 的 capability 模型：`presets/<n>/actors.json` 里的
        「谁是外生实体 + 它握有哪些修改权限」就是权限表，内核只认
        「已登记的实体」这个事实，不认任何一个名字。
        """
        from .operators import OPERATORS
        grants = {}
        for a in (getattr(self._data, "actors", None) or []):
            grants[str(a["id"])] = [str(g) for g in (a.get("grants") or ())]
        return {
            "api_version": API_VERSION,
            "pipeline": list(self._cfg.pipeline),
            "operators": sorted(OPERATORS),
            "capabilities": sorted(str(c) for c in CAPABILITIES),
            "actors": grants,
        }


#: 机器规格里可以写哪些键。写别的当场报错 —— 静默忽略一个拼错的键，
#: 只会变成"我明明配了它却没生效"这类最难查的事故。
_SPEC_KEYS = ("root", "preset", "lexicon", "config", "data", "seed", "runtime",
              "namer", "rules", "trace", "capture", "iter_cap", "watch",
              "on_event", "start_state", "start_frame", "inbox")


def load(machine_spec=None):
    """用【机器规格】建一个世界，返回 `Session`。

    `machine_spec` 可以是一句话（预设名），也可以是一张表：

        load()                      # 涌现版（默认预设 _default）
        load("plot")                # presets/plot
        load({"preset": "plot", "seed": 7, "runtime": apps.services.default()})

    表里认得的键见 `_SPEC_KEYS`：世界那半边（`preset` / `root` / `config` /
    `data` / `lexicon`）+ 运行选项（`seed` / `runtime` / `namer` / `rules` /
    `trace` / `capture` / `iter_cap` / `watch` / `on_event` / `start_state` /
    `start_frame` / `inbox`）。

    `config` / `data` 可以直接把**已经装配好的**对象交进来（`run()` 就是这么
    退化成本组合的）；不给才现装。
    """
    if machine_spec is None:
        spec = {}
    elif isinstance(machine_spec, str):
        spec = {"preset": machine_spec}
    elif isinstance(machine_spec, dict):
        spec = dict(machine_spec)
    else:
        raise TypeError(
            f"机器规格应是预设名（字符串）或一张表（dict），实为 "
            f"{type(machine_spec).__name__}")

    unknown = sorted(k for k in spec if k not in _SPEC_KEYS)
    if unknown:
        raise ValueError(
            f"机器规格里有内核不认得的键：{'、'.join(unknown)}"
            f"（可选：{'、'.join(_SPEC_KEYS)}）"
            "—— 静默忽略一个拼错的键，只会变成「配了却没生效」。")

    root = spec.get("root") or ROOT
    data = spec.get("data")
    if data is None:
        data = DataSet(root, preset=spec.get("preset"))
    cfg = spec.get("config")
    if cfg is None:
        overlay = spec.get("lexicon")
        if overlay is None:
            overlay = data.preset.get("lexicon")
        cfg = Config(root, lex_overlay=overlay)

    opts = {k: v for k, v in spec.items() if k not in ("root", "preset", "lexicon",
                                                       "config", "data")}
    return Session(cfg, data, **opts)