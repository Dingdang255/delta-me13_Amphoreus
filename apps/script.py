"""§D2 事件驱动应用模型：**订阅 + 响应**（声明式，路线 A）。

预设的 `script.jsonl` 每行一条规则：

    {"on": "promotion", "if": "promotions >= 8", "permit": "preset",
     "channel": "world", "label": "……",
     "do": [{"emit": "mydei_ascends"}, {"inject": "suppress_slot:order:1"}]}

两种投递时机 —— 同一条规则按 `on` 落在其中**一种**：

  · `on: "FRAME"` —— **定时投递**。用 `at` 指定帧（`if` 可选）。它编译成与
    `presets/<n>/events.jsonl` **形状完全一致**的投递记录，由 `install(data)` 并进
    世界，此后走内核原本那条路（同一个求值点、同一套跳帧锚）。于是
    「脚本的退化形式 ≡ 旧日程表」不是跑一遍碰运气，而是**同一条数据**
    （见 `from_events`、`tests/test_script.py`）。
  · 其余 `on`（内核的事件类别，见 `kernel.vocabulary.EVENT_KINDS`）—— **反应**。
    挂在内核的事件回调上；条件成立就把动作 `session.inject(...)` 出去，**下一帧生效**
    （事件发生在第 n 帧 ⇒ 扰动落在 n+1）。每条反应只触发一次；条件当时不成立就继续
    等下一次同类事件。

三条纪律（与设计稿 §8.5 一致）：

  1. **不许看未来**：`if` 用 `apps/conditions.py` 那门语言（三类词、禁 `eval`）。
     它的词法里根本没有"按下标取未来帧"这类形状，故预读未来在构造上不成立。
  2. **写回必须申报权限**：凡动作里有 `capability != "emit"` 的，规则必须写 `permit`，
     取值要么是预设 `actors.json` 里已登记的实体 id，要么是保留值 `"preset"`
     （＝预设作者以自己名义写回 —— 今天 `events.jsonl` 里那些不带 actor 的机制投递
     就是这一类）。未申报一律编译不过。
  3. **拼错的订阅名当场报错**：静默会把"写错了"变成"这条永远不触发"。

反应条件读到的量 = **内核 `when` 条件在同一帧读到的量**（见 `kernel.api.Session.observe`
的口径说明）—— 条件这一门语言只有一份，预设与应用说的是同一句话。

本模块是**应用**：它 import 内核的常量（能力表 / 事件类别 / 选择器注册表），内核则
一行都不 import 它（依赖方向 apps → kernel，见 `tools/layer_lint.py`）。
"""
from __future__ import annotations

from kernel.disturbance import CAPABILITIES
from kernel.selector import known as selector_known
from kernel.vocabulary import EVENT_KINDS

from .conditions import check as check_condition
from .conditions import evaluate as eval_condition
from .conditions import known_names as condition_names

__all__ = ["ScriptError", "FRAME", "RESERVED_PERMIT", "Compiled",
           "compile_rules", "from_events", "Script"]


#: 定时订阅的关键字（`on` 写它 = "不看事件，按帧投递"）。
FRAME = "FRAME"

#: `permit` 的保留值：预设作者以自己名义写回。它对应今天 `events.jsonl` /
#: `disturbances.jsonl` 里那些**没有** actor 字段的机制投递 —— 那些写回是预设作者
#: 做的，不是某个具名实体做的。具名实体则必须写它在 `actors.json` 里登记的 id。
RESERVED_PERMIT = "preset"


class ScriptError(ValueError):
    """脚本写错了：形状不对、订阅名不认得、条件不合法、权限没申报。"""


class Compiled:
    """一份编译结果：定时投递（进世界）+ 反应（挂事件回调）。"""

    __slots__ = ("scheduled", "reactions", "rules")

    def __init__(self, scheduled, reactions, rules):
        #: 与 `events.jsonl` 同形的投递记录 —— 交给 `DataSet.add()`。
        self.scheduled = scheduled
        #: 反应表（每条是一个 dict，见 `_compile_reaction`）。
        self.reactions = reactions
        #: 原始规则（保留，供核对与报错定位）。
        self.rules = rules

    @property
    def reactive(self) -> bool:
        return bool(self.reactions)

    def __repr__(self):
        return (f"<Compiled 定时 {len(self.scheduled)} 条 · "
                f"反应 {len(self.reactions)} 条>")


# ---- 动作归一：都变成【投递形状】的 {capability, payload, selector} -------------
def _action(action, where):
    """把一条动作归一成投递形状。

    认三种写法：

      {"emit": "事件名"} / {"emit": {"event": …, …}}   ⇒ 能力 `emit`（只播报，不改世界）
      {"inject": "能力"} / {"inject": "能力:选择器表达式"} / {"inject": {…}}  ⇒ 真写回
      {"capability": …, "payload": …, "selector": …}       ⇒ 全形（`from_events` 用它）
    """
    if not isinstance(action, dict):
        raise ScriptError(f"{where} 的动作应为对象，实为 {type(action).__name__}")

    if "emit" in action:
        v = action["emit"]
        if isinstance(v, str):
            payload = {"event": v}
        elif isinstance(v, dict):
            payload = dict(v)
        else:
            raise ScriptError(
                f"{where} 的 emit 应为事件名（字符串）或载荷（对象），"
                f"实为 {type(v).__name__}")
        return {"capability": "emit", "payload": payload, "selector": None}

    if "inject" in action:
        v = action["inject"]
        if isinstance(v, str):
            cap, _, expr = v.partition(":")
            cap, expr = cap.strip(), expr.strip()
            return {"capability": cap, "payload": {},
                    "selector": {"expr": expr} if expr else None}
        if isinstance(v, dict):
            return {"capability": str(v.get("capability") or ""),
                    "payload": dict(v.get("payload") or {}),
                    "selector": v.get("selector")}
        raise ScriptError(
            f"{where} 的 inject 应为「能力」/「能力:选择器」字符串或对象，"
            f"实为 {type(v).__name__}")

    if "capability" in action:
        return {"capability": str(action.get("capability") or ""),
                "payload": dict(action.get("payload") or {}),
                "selector": action.get("selector")}

    raise ScriptError(
        f"{where} 的动作既没有 emit 也没有 inject / capability：{sorted(action)}"
        f"（可选：emit / inject / capability）")


def _check_action(act, where, problems):
    """能力 / 选择器 / 载荷的静态校验。就地往 problems 追加，不抛异常。"""
    cap = act["capability"]
    if cap not in CAPABILITIES:
        problems.append(
            f"{where} 的 capability = {cap!r} 不是已注册的能力"
            f"（可选：{'、'.join(sorted(CAPABILITIES))}）")
    sel = act["selector"]
    if sel is not None:
        expr = sel.get("expr") if isinstance(sel, dict) else None
        if not selector_known(expr):
            problems.append(
                f"{where} 的 selector.expr = {expr!r} 不是引擎认识的选择器")
    if not isinstance(act["payload"], dict):
        problems.append(f"{where} 的 payload 应为对象")


def _emitted(payload):
    """这份载荷会登记的事件名（`emitted_<名>`）—— 供 `event("X")` 的静态闸门核。"""
    ev = (payload or {}).get("event")
    return {str(ev)} if ev is not None else set()


# ---- 编译 -------------------------------------------------------------------
def _norm_rule(rule, i, actors, where, problems):
    """校验一条规则的【形状】，返回归一结果或 None（有问题时）。"""
    at = f"{where}[{i}]"
    if not isinstance(rule, dict):
        problems.append(f"{at} 应为对象，实为 {type(rule).__name__}")
        return None

    on = rule.get("on")
    if not isinstance(on, str) or not on.strip():
        problems.append(f"{at} 缺 on（订阅谁：\"FRAME\" 或某个事件类别）")
        return None
    kind = on.strip().upper()
    timer = kind == FRAME
    if not timer and kind not in EVENT_KINDS:
        problems.append(
            f"{at} 的 on = {on!r} 既不是 {FRAME}，也不是内核会发的事件类别"
            f"（可选：{FRAME}、{'、'.join(sorted(EVENT_KINDS))}）")
        return None

    frame_v = rule.get("at")
    if timer:
        if not isinstance(frame_v, int) or isinstance(frame_v, bool) or frame_v < 0:
            problems.append(
                f"{at} 是 {FRAME} 订阅，须给 at = 帧号（非负整数），实为 {frame_v!r}")
            return None
    elif frame_v is not None:
        problems.append(
            f"{at} 是反应式订阅（on={on!r}），不该写 at —— 它由事件触发，"
            f"不由帧触发（要按帧投递请写 on: \"{FRAME}\" + at）")
        return None

    cond = rule.get("if")
    if cond is not None and (not isinstance(cond, str) or not cond.strip()):
        problems.append(f"{at} 的 if 应为条件表达式（字符串）")
        return None

    do = rule.get("do")
    if not isinstance(do, list) or not do:
        problems.append(f"{at} 的 do 应为【非空】动作数组")
        return None

    acts = []
    for j, raw in enumerate(do):
        try:
            act = _action(raw, f"{at}.do[{j}]")
        except ScriptError as exc:
            problems.append(str(exc))
            return None
        _check_action(act, f"{at}.do[{j}]", problems)
        acts.append(act)

    needs_permit = any(a["capability"] != "emit" for a in acts)
    permit = rule.get("permit")
    if needs_permit:
        ids = {str(a.get("id")) for a in actors}
        if permit is None:
            problems.append(
                f"{at} 的动作要写回世界（{_caps(acts)}），却没有申报 permit。"
                f"写回必须申报权限：填预设 actors.json 里登记的实体 id，"
                f"或以 {RESERVED_PERMIT!r} 表示「预设作者自己」")
        elif str(permit) != RESERVED_PERMIT and str(permit) not in ids:
            problems.append(
                f"{at} 的 permit = {permit!r} 不是本预设 actors.json 里登记的实体"
                f"（可选：{RESERVED_PERMIT}、{'、'.join(sorted(ids)) or '（本预设没有 actors.json）'}）")
    elif permit is not None and str(permit) not in {
            str(a.get("id")) for a in actors} | {RESERVED_PERMIT}:
        problems.append(
            f"{at} 的 permit = {permit!r} 不是本预设 actors.json 里登记的实体")

    channel = rule.get("channel", "world")
    if not isinstance(channel, str) or not channel:
        problems.append(f"{at} 的 channel 应为非空字符串")
        return None
    label = rule.get("label")
    if label is not None and not isinstance(label, str):
        problems.append(f"{at} 的 label 应为字符串")
        return None
    lore_ref = rule.get("lore_ref")
    if lore_ref is not None and (
            not isinstance(lore_ref, list)
            or not all(isinstance(x, str) and x for x in lore_ref)):
        problems.append(f"{at} 的 lore_ref 应为非空字符串数组")
        return None

    return {"kind": kind, "timer": timer, "at": frame_v, "if": cond, "acts": acts,
            "channel": channel, "label": label, "lore_ref": lore_ref, "where": at}


def _caps(acts):
    return "、".join(sorted({a["capability"] for a in acts
                             if a["capability"] != "emit"})) or "—"


def _record(norm, act):
    """归一规则 + 一条动作 → 与 `events.jsonl` **同形**的投递记录。

    形状是刻意的：从 `events.jsonl` 翻过来的脚本，编译出来必须与原文**逐字相同**
    —— 否则"双轨等价"就只是"看起来差不多"。故这里按键序固定、且只在真有值时
    才落 `when` / `label`（与旧行的写法一致）。
    """
    rec = {"frame": int(norm["at"]), "channel": norm["channel"],
           "capability": act["capability"], "selector": act["selector"],
           "payload": dict(act["payload"])}
    if norm["if"]:
        rec["when"] = norm["if"]
    if norm["label"] is not None:
        rec["label"] = norm["label"]
    if norm.get("lore_ref"):
        rec["lore_ref"] = list(norm["lore_ref"])
    return rec


def compile_rules(rules, *, cfg=None, actors=(), events=(), where="script.jsonl"):
    """把声明式规则编译成（定时投递 + 反应）。不合规一律报错，绝不静默降级。

    cfg      —— 可选 `Config`：条件里的席位名（`seat_l01` …）按它的位表 id 校验。
    actors   —— 预设 `actors.json` 的实体表（`permit` 据此校验）。
    events   —— 额外允许的事件名（预设别的文件里声明过的桥段名）。
    """
    rules = list(rules or [])
    problems, norms = [], []
    for i, rule in enumerate(rules):
        norm = _norm_rule(rule, i, actors, where, problems)
        if norm is not None:
            norms.append(norm)

    # 事件名的静态闸门：允许「本脚本自己会发的」+「预设别处声明过的」。
    allowed_events = {str(e) for e in (events or ()) if e}
    for norm in norms:
        for act in norm["acts"]:
            allowed_events |= _emitted(act["payload"])
    names = condition_names(cfg)
    for norm in norms:
        if not norm["if"]:
            continue
        try:
            check_condition(norm["if"], allowed_names=names,
                            allowed_events=allowed_events)
        except Exception as exc:                              # noqa: BLE001
            problems.append(f"{norm['where']} 的 if 不合法：{exc}")

    if problems:
        raise ScriptError(
            f"{where} 编译未通过（{len(problems)} 处）：\n  - "
            + "\n  - ".join(problems))

    scheduled, reactions = [], []
    for norm in norms:
        if norm["timer"]:
            for act in norm["acts"]:
                scheduled.append(_record(norm, act))
        else:
            reactions.append({"kind": norm["kind"], "if": norm["if"],
                              "acts": norm["acts"], "channel": norm["channel"],
                              "label": norm["label"], "where": norm["where"]})
    return Compiled(scheduled, reactions, rules)


def from_events(records):
    """把 `events.jsonl` / `disturbances.jsonl` 的旧行翻成脚本规则（**无损**）。

    翻法是逐字段搬运：`frame` → `at`、`when` → `if`、其余原样。于是
    `compile_rules(from_events(rows)).scheduled == rows` 是**可断言的等式**，
    而不是"跑一遍看着像" —— 这就是 §8.2 说的"退化等价可证"。

    非 `emit` 的动作补 `permit: "preset"`（旧行没有 actor 字段，那些写回本就是
    预设作者做的）。
    """
    out = []
    for r in records:
        act = {"capability": r["capability"], "payload": dict(r.get("payload") or {}),
               "selector": r.get("selector")}
        rule = {"on": FRAME, "at": int(r["frame"]), "do": [act]}
        if r.get("channel"):
            rule["channel"] = r["channel"]
        if r.get("when"):
            rule["if"] = r["when"]
        if r.get("label") is not None:
            rule["label"] = r["label"]
        if r.get("lore_ref"):
            rule["lore_ref"] = list(r["lore_ref"])
        if r["capability"] != "emit":
            rule["permit"] = RESERVED_PERMIT
        out.append(rule)
    return out


def declared_events(preset):
    """预设里声明过的【事件名】（`events` / `disturbances` 的 `payload.event`）。

    条件是数据，不是代码 —— 拼错的事件名由静态闸门拦。这个函数就是那份闸门的
    "已知名单"来源。
    """
    out = set()
    for key in ("events", "disturbances"):
        for rec in (preset.get(key) or ()):
            ev = (rec.get("payload") or {}).get("event")
            if ev:
                out.add(str(ev))
    return out


class Script:
    """一份已编译的脚本 + 它绑定的会话。**它是应用**：只读事件、按声明写回。

    用法（run.py 就是这么用的）：

        script = Script.from_preset(data, cfg=ctx)
        script.install(data)          # 定时投递并进世界（空脚本时无事发生）
        sess = load({... "watch": script.watch(...) ...})
        script.bind(sess)             # 反应要写回，得有地方投
        traj = sess.step(...)

    `on_event` / `watch` 的签名与内核回调一致，故可以直接组成 or 链交给 `load()`。
    """

    def __init__(self, compiled, session=None):
        self._c = compiled
        self._session = session
        self._fired = set()

    @classmethod
    def from_preset(cls, data, cfg=None, session=None):
        """从预设的 `script.jsonl` 造一份脚本（预设没写 → 空脚本，一切照旧）。"""
        preset = getattr(data, "preset", {}) or {}
        compiled = compile_rules(
            getattr(data, "script", ()) or [], cfg=cfg,
            actors=getattr(data, "actors", ()) or (),
            events=declared_events(preset))
        return cls(compiled, session)

    # ---- 定时投递 ------------------------------------------------------------
    @property
    def scheduled(self):
        return self._c.scheduled

    def install(self, data):
        """把定时投递并进世界（`DataSet.add`）。返回并进了几条。"""
        if not self._c.scheduled:
            return 0
        return data.add(list(self._c.scheduled))

    # ---- 反应 ---------------------------------------------------------------
    @property
    def reactive(self) -> bool:
        return self._c.reactive

    @property
    def fired(self) -> list:
        """已经触发过的反应（序号，按触发次序）。"""
        return sorted(self._fired)

    def bind(self, session):
        """绑定会话 —— 反应要**写回**（`inject`）得有地方投。返回自己。"""
        self._session = session
        return self

    def on_event(self, frame, kind, payload=None, clock=None, namer=None):
        """内核事件回调（签名与 `LiveStream.on_event` 一致，多出的参数是内核的旁注）。"""
        if not self._c.reactions:
            return
        f = int(frame)
        k = str(kind).upper()
        for i, rea in enumerate(self._c.reactions):
            if i in self._fired or rea["kind"] != k:
                continue
            if rea["if"] is not None and not self._holds(rea, f):
                continue
            self._fired.add(i)
            for act in rea["acts"]:
                self._deliver(rea, act, f)

    def _holds(self, rea, frame) -> bool:
        """反应的条件求值。读的就是 `observe()` —— 与预设的 `when` 同一门语言。

        `frame` 改成【这条事件发生在哪一帧】：条件里的 `frame` 指的是"现在"，
        不是"本次 step 从哪开始"。
        """
        obs = self._need_session(rea).observe()
        obs["frame"] = int(frame)
        return bool(eval_condition(rea["if"], obs))

    def _deliver(self, rea, act, frame):
        """把一条动作作为【外生扰动】投出去 —— **下一帧生效**（帧号写成 frame+1）。"""
        rec = {"frame": int(frame) + 1, "channel": rea["channel"],
               "capability": act["capability"], "selector": act["selector"],
               "payload": dict(act["payload"])}
        if rea["label"] is not None:
            rec["label"] = rea["label"]
        self._need_session(rea).inject(rec)

    def _need_session(self, rea):
        if self._session is None:
            raise ScriptError(
                f"{rea['where']} 要写回世界（或要读世界状态），但脚本还没绑定会话："
                f"先 Script.bind(session) 再跑。")
        return self._session

    def __repr__(self):
        return (f"<Script 定时 {len(self._c.scheduled)} 条 · "
                f"反应 {len(self._c.reactions)} 条 · 已触发 {len(self._fired)}>")