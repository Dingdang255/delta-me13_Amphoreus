#!/usr/bin/env python3
"""δ-me13「翁法罗斯」演算引擎 —— 入口。

    python3 run.py                      # 涌现版：名字全由演算生成
    python3 run.py --preset plot        # 剧情锚定版：名字按剧情绑定（不改轨迹）
    python3 run.py --frames 30000       # 只跑到第 30000 帧
    python3 run.py --seed 7             # 换一个世界种子（角色会完全不同）
    python3 run.py --dump-anchors       # 导出命名标定语料
    python3 run.py --preset plot --export   # 导出 dashboard → dashboard/翁法罗斯-可视化.html
    python3 run.py --preset plot --log      # 编年史落盘 → logs/翁法罗斯编年史_演算N.txt
    python3 run.py --preset plot --serve    # 起实时看板：边演算边在浏览器里看（演完可回放）
    python3 run.py --list-presets       # 列出可用预设

预设只提供【演算之外】的东西：固定种子、名字绑定、额外的外生事件、
以及一份期望时间线。其中时间线引擎从不读它 —— 报告里的【四】只是核对，
真正拿它去检索种子的是 tools/seed_probe.py --preset plot。

终止条件是【命题能否裁决】，不是"跑够多少帧"：
命题被判定（证真 / 证伪）即停；判不出来才走满预算。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine.assertions import AssertionRunner  # noqa: E402
from engine.core import run  # noqa: E402
from engine.conditions import evaluate as eval_condition  # noqa: E402
from engine.namer import Namer  # noqa: E402
from engine.features import extract  # noqa: E402
from engine.loader import Config, DataSet, ROOT, apply_fast  # noqa: E402
from engine.operators import MEMORY_OWNER, consensus  # noqa: E402
from engine.render import (Renderer, advance_label, cycle_frames,  # noqa: E402
                           myth_phase_frame, renewal_switch_frame, stage_starts,
                           stage_table)
from engine.timeline import check as check_timeline  # noqa: E402
from engine.viz import (Sampler, build_html, build_live_shell,  # noqa: E402
                        summary_cards, texture_of)

BAR = "─" * 72

# 裁决与停因的显示名一律来自配置（config/conclusions.json 的 label / stop_label、
# config/lexicon.json 的 stop_reasons），报告层不再维护任何写死的枚举表 ——
# 于是「新增一个结论维度」不必改这个文件。

# ---- 输出详细程度：按【类别】控制编年史的字数 ------------------------------
# 0 静默 / 1 摘要 / 2 常规 / 3 详细。默认写在 config/params.json 的 verbosity 里；
# 缺项按 3（最详细）。它只影响渲染 —— 删掉这一整块，演算结果逐帧不变。
_VERB_DEFAULT = {"promotion": 3, "emergence": 3, "deadlock": 3, "succession": 3,
                 "disturbance": 3, "verdict": 3, "domain": 3, "converged": 3,
                 "solver": 3, "violation": 3, "prune": 3}

_KIND_CAT = {
    "PROMOTION": "promotion", "EMERGENCE": "emergence",
    "DEADLOCK_LOOP": "deadlock", "DEADLOCK_TICK": "deadlock", "DEADLOCK_END": "deadlock",
    "ATTEMPT_VAIN": "deadlock", "ATTEMPT_TRACE": "deadlock",
    "SUCCESSION": "succession", "DISTURBANCE": "disturbance",
    "PROTOCOL_REWRITTEN": "disturbance",
    "CONCLUSION_REACHED": "verdict", "VERDICT": "verdict", "ASCENSION": "verdict",
    "DOMAIN_ADVANCE": "domain", "DOMAINS_EXHAUSTED": "domain",
    "SOLVER_CHANGED": "solver", "CONVERGED": "converged",
    "VIOLATION_STATE": "violation", "PRUNE": "prune",
}


class Verbosity:
    """按【输出类别】控制编年史详细程度。只读、只渲染。

    0 静默：该类不播报。
    1 摘要：再创世与轮回刻度照报，黄金裔每世只报首位，尝试类整段略去。
    2 常规：黄金裔逐位报，尝试按稀疏采样播报（现状）。
    3 详细：尝试逐次播报，承位易主连无名者也带上编号。
    """

    def __init__(self, levels=None):
        self.levels = dict(_VERB_DEFAULT)
        for k, v in (levels or {}).items():
            if k in self.levels:
                self.levels[k] = int(v)
        self._era_had_emergence = False

    def level(self, kind: str) -> int:
        return self.levels.get(_KIND_CAT.get(kind, ""), 3)

    def allow(self, kind: str, payload: dict) -> bool:
        lv = self.level(kind)
        if lv <= 0:
            return False
        if kind == "PROMOTION":                    # 世代刻度：任何档位都留
            self._era_had_emergence = False
            return True
        if kind == "EMERGENCE":
            if lv == 1:                            # 摘要：一世只报首位
                if self._era_had_emergence:
                    return False
                self._era_had_emergence = True
            return True
        if kind in ("ATTEMPT_VAIN", "ATTEMPT_TRACE"):
            if lv == 1:
                return False
            if lv == 2 and kind == "ATTEMPT_VAIN":
                return _notable_cycle(int(payload.get("cycle", 0)))
            return True
        return True


def parse_verbosity(spec):
    """把命令行的 `--verbosity` 写法学成 {类别: 档位}。

    `2`                 —— 所有类别都置 2
    `deadlock=1`        —— 只改死循环那一类
    `2,deadlock=3`      —— 先全置 2，再把死循环抬到 3（后者覆盖前者）
    """
    out = {}
    for part in str(spec).split(","):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            key, _, val = part.partition("=")
            key = key.strip()
            if key not in _VERB_DEFAULT:
                raise ValueError(f"未知的输出类别 {key!r}（可选：{'、'.join(sorted(_VERB_DEFAULT))}）")
            out[key] = int(val)
        else:
            out.update({k: int(part) for k in _VERB_DEFAULT})
    for k, v in out.items():
        if not 0 <= v <= 3:
            raise ValueError(f"类别 {k} 的档位 {v} 越界（只接受 0～3）")
    return out


def fmt(n):
    return f"{n:,}"


class Cast:
    """渲染层的角色名册：把引擎的编号翻成人名，并决定谁是「承载者」。

    它【只读】Telemetry。**名随人走** —— 一个编号对应一个名字，席位换手不换名；
    认不出来的编号绝不拿职位名顶替。名字有两个来源：涌现时引擎抛来的世界名
    （EMERGENCE），以及预设按【编号】钉在某个个体身上的名字（`serial:<n>`）。

    承载者的受难之名来自锚定层的 `stall_seat:` 键，引擎一概不知：预设把受难之名
    绑在哪一席，占着那一席的人就是承载者（默认退回「第一个涌现者」）。这也是
    渲染约定，不是引擎规则。
    """

    def __init__(self, R, namer):
        self.R = R
        self.namer = namer
        self.by_serial = {}
        self.by_rank = {}

    def see(self, payload):
        """从一条 EMERGENCE 记下一名角色：按 serial 查、按 rank 定位首位涌现者。"""
        name = payload.get("hanzi") or payload.get("latin") or "?"
        s = payload.get("serial")
        if s is not None:
            self.by_serial[int(s)] = name
        r = payload.get("rank")
        if r is not None:
            self.by_rank[int(r)] = name

    def resolve(self, serial):
        """编号 → 名字。认不出来返回 None。

        由【记忆】承载的位（编号 -1）是特例：预设可以用锚定把它点名给某个「记忆命途的
        衍生」（例如把长夜月钉在这一席上），没有点名时才退回「记忆」这个通名。
        """
        if serial is None:
            return None
        s = int(serial)
        hit = self.by_serial.get(s)
        if hit:
            return hit
        a = self.namer.name_by_serial(s)  # 预设按编号点名过这个体
        if a:
            return a[1]
        if s == MEMORY_OWNER:             # 由记忆本身承载的位
            return self.R.term("memory")
        return None

    def knows(self, serial):
        """这个编号是否认得出来（用于决定要不要点名）。"""
        return self.resolve(serial) is not None

    def carrier(self, payload=None):
        """承载者此刻的名字：占着预设指定的那一席的人，用其受难之名。"""
        alt = self.namer.stall_alt_name()
        if alt is None:
            return self.by_rank.get(0) or "承载者"
        owners = (payload or {}).get("owners")
        seat = self.namer.stall_seat_index()
        who = (self.resolve(owners[seat])
               if owners is not None and seat is not None and seat < len(owners)
               else None)
        # 受难之名与他自己的名字相同（本就是同一个人的两个称呼）时不必重复写两遍。
        return f"{alt[1]}（{who}）" if who and who != alt[1] else alt[1]


def _burden_text(R, b, advance=None, frame=None):
    """背负：累加的记账。`advance` 是这次世代更迭的名字（自动更替 / 再创世），
    与主句同名 —— 免得在「第 1 次自动更替」后面紧跟一句「再创世 1 次」。

    `frame` 决定用哪套【阶段语汇】：前三个阶段记的是「原动力 / 消亡」，第四阶段才是
    「火种 / 陨落」。模板来自 `lexicon.stall.burden`（带阶段覆盖）。
    """
    tpl = R.text("stall", "burden", frame)
    return tpl.format(
        seeds=fmt(int(b.get("seeds", 0))),
        advance=advance or R.term("promotion", frame),
        filled=b.get("filled", "?"), slots=b.get("slots", "?"),
        rounds=fmt(int(b.get("rounds", 0))), fell=fmt(int(b.get("fell", 0))),
        since_promotion=fmt(int(b.get("since_promotion", 0))))


def _notable_cycle(c: int) -> bool:
    """循环轮次的稀疏采样：少数几次足以讲清「一直在试、一直徒劳」。"""
    return c < 3 or c % 512 == 0


# ---- A5：连续同型事件折叠 ---------------------------------------------------
# 死循环末段会逐次刷出「已守到第 N 次轮回」，几千行几乎一模一样。把【连续同型】
# 的记录折成一条并附计数徽标，能读出结构变化而不是一堵墙。纯渲染 —— 删掉这段，
# 演算逐帧不变。折叠只作用于下面这几类【同质、会成串】的事件。
_COLLAPSE_KINDS = {"ATTEMPT_VAIN", "ATTEMPT_TRACE", "DEADLOCK_TICK"}


def _collapse_sig(kind, payload):
    """可折叠事件的同类判据：签名相同且相邻 ⇒ 折成一条。不可折叠 ⇒ None。"""
    if kind in ("ATTEMPT_VAIN", "ATTEMPT_TRACE"):
        return (kind, payload.get("stage"), payload.get("routine"),
                payload.get("approach"))
    if kind == "DEADLOCK_TICK":
        return (kind,)
    return None


class ChronicleFolder:
    """把【连续同型】事件折成一条的缓冲器。报告与实时输出共用同一份折叠口径。

    它只攒已经渲染好的文本，不碰任何状态。真正吐字由 emit_line(rid, frame, text, badge)
    负责 —— 于是同一折叠逻辑既能落进报告的字符串列表，也能落进实时输出流。
    `rid` 是这条事件在记录流里的【事件号】：折叠时取该组首条的那个（时间线打点与它同源，
    双击节点据此精确回跳；打点的类别都不可折叠，故永不撞号）。
    """

    def __init__(self, emit_line):
        self.emit_line = emit_line
        self.pending = None       # (rid, frame, sig, text, count, last_frame)

    def feed(self, rid, frame, kind, payload, text):
        sig = _collapse_sig(kind, payload)
        if self.pending is not None:
            prid, pf, psig, ptext, pcount, _plast = self.pending
            if sig is not None and sig == psig:
                self.pending = (prid, pf, psig, ptext, pcount + 1, frame)
                return
            self._flush()
        if sig is None:
            self.emit_line(rid, frame, text, None)
        else:
            self.pending = (rid, frame, sig, text, 1, frame)

    def _flush(self):
        if self.pending is None:
            return
        prid, pf, _sig, ptext, pcount, plast = self.pending
        badge = f"（同类 ×{fmt(pcount)} · 至帧 {fmt(plast)}）" if pcount > 1 else None
        self.emit_line(prid, pf, ptext, badge)
        self.pending = None

    def close(self):
        self._flush()


def chronicle_line(R, namer, kind, payload, cast=None, lv=3, advance_label=None,
                   frame=None):
    """把【一条】Telemetry 记录翻译成世界内的一句话。纯渲染，不参与演算。

    报告与实时输出共用这一份口径 —— 报告怎么讲，实时就怎么讲。
    lv 是该类别的详细程度（0 静默 / 1 摘要 / 2 常规 / 3 详细），只影响措辞。
    返回 None 表示这条记录不翻译（例如逐帧违例状态）。
    advance_label：这次世代更迭该叫哪一档（自动更替 / 主动更替 / 再创世，调用方按帧查档传入）。
    frame：这条记录发生在哪一帧 —— 它决定用【哪套阶段语汇】（前三个阶段 = 因子演算，
    第四阶段 = 人类古典文明/世界内）。句子模板与名词都走词表，`frame=None` 按第四阶段。
    """
    T = lambda k: R.tpl(k, frame)          # noqa: E731 —— 句模板
    W = lambda k: R.term(k, frame)         # noqa: E731 —— 名词
    if kind == "DISTURBANCE":
        if payload.get("label"):        # 预设自带的世界内措辞（预设层允许专有名词）
            return payload["label"]
        who = R.term("observer") if payload.get("channel") == "observer" else "环境"
        sel = f" [选择器:{payload['selector']}]" if payload.get("selector") else ""
        return f"{who}介入 · {R.capability(payload['capability'])}{sel}"
    if kind == "PROTOCOL_REWRITTEN":
        items = "、".join(f"{k} → {v}" for k, v in sorted(payload["changed"].items()))
        return f"◆ {R.term('protocol')}被改写：{items}"
    if kind == "DOMAIN_ADVANCE":
        line = f"初始变量推进 → {R.domain(payload['value'])}"
        got = payload.get("assembled") or ()
        if got:                         # 该阶段新装上的机制（阶段装配）
            line += "（装配：" + "、".join(R.event(g) for g in got) + "）"
        return line
    if kind == "DOMAINS_EXHAUSTED":
        # 前三 → 第四阶段的分界。这里不写「初始变量域已穷尽」了事，而是把「改叫法」
        # 讲成一个事件（wiki moegirl 第 47 行：第四阶段把背景设为人类古典文明，
        # 其中十二因子便成为十二泰坦 / 黄金裔）—— 免得读者觉得措辞是突然变的。
        return T("myth_onset").format(locus=W("locus"), persona=W("persona"))
    if kind == "SOLVER_CHANGED":
        return (f"演算方向被改写：{R.event(payload['from'])} → {R.event(payload['to'])}")
    if kind == "PROMOTION":
        return T("promotion").format(
            round=fmt(payload["round"]),
            advance=advance_label or W("promotion"),
            complete=T("complete"),
            burden=_burden_text(R, payload.get("burden") or {}, advance_label, frame),
            rise=T("rise").format(halfgod=W("halfgod"), locus=W("locus")))
    if kind == "CONVERGED":
        return T("converged").format(converged=W("converged"), memory=W("memory"),
                                     promotion=W("promotion"))
    if kind == "EMERGENCE":
        payload = namer.named_payload(payload)   # 内核只发编号，词汇在这一层补
        lid = payload.get("locus")
        seat = (T("seat_taken").format(seat=R.seat(namer, frame, lid))
                if lid else T("seat_none"))
        return T("emergence").format(persona=W("persona"), name=payload["hanzi"],
                                     latin=payload["latin"],
                                     machine=payload["machine"], seat=seat)
    if kind == "DEADLOCK_LOOP":
        who = cast.carrier(payload) if cast else "承载者"
        # 点名【哪一席】空着 —— 只说「那一席」不够，读者无从知道缺的是谁的位置。
        seats = "、".join(
            t for t in (R.seat(namer, frame, lid)
                        for lid in (payload.get("vacant_loci") or ())) if t
        ) or "那一席"
        why = R.text("deadlock", "why", frame).format(
            seeds=fmt(int(payload.get("seeds", 0))), vacant=seats,
            promotion=R.term("promotion", frame))
        return (f"⟳ {R.text('deadlock', 'loop', frame).format(why=why)}"
                f" · {R.text('stall', 'begin', frame).format(who=who)}")
    if kind == "DEADLOCK_TICK":
        who = cast.carrier(payload) if cast else "承载者"
        return "⟳ " + R.text("deadlock", "tick", frame).format(
            cycle=fmt(int(payload.get("cycle", 0))), who=who,
            elapsed=fmt(int(payload.get("elapsed", 0))))
    if kind == "ATTEMPT_VAIN":
        # 是否渲染、多久渲染一次，由【详细程度】在 allow() 里定；这里只管措辞。
        an = R.lex.get("deadlock", {})
        who = cast.carrier(payload) if cast else "承载者"
        if payload.get("routine"):
            # 末段：理智只剩一线，不再换法子，只是一遍遍走同一套动作。
            # 这里报【轮回序号】—— 一轮可能跨很多帧，故它与帧号不是一回事。
            return "⟳ " + R.text("deadlock", "routine", frame).format(
                who=who, cycle=fmt(int(payload.get("ordinal", 1))))
        # 段位（期望 / 幻灭 / 灼烧）由词表命名；缺该键则退回通用措辞。
        stage = payload.get("stage")
        if stage and ("stage_" + str(stage)) in an:
            return "⟳ " + R.text("deadlock", "stage_" + str(stage), frame).format(
                who=who, approach=R.capability(payload.get("approach")),
                cycle=fmt(int(payload.get("cycle", 0))))
        # 第一次轮回用「尝试」而非「换了一种法子」—— 他还没有「换」过。
        key = "vain_first" if int(payload.get("cycle", 0)) == 0 else "vain"
        return "⟳ " + R.text("deadlock", key, frame).format(
            who=who, approach=R.capability(payload.get("approach")))
    if kind == "ATTEMPT_TRACE":
        who = cast.carrier(payload) if cast else "承载者"
        return "⟳ " + R.text("deadlock", "trace", frame).format(
            who=who, approach=R.capability(payload.get("approach")))
    if kind == "DEADLOCK_END":
        return (f"⟳ {R.text('deadlock', 'end', frame).format(cycle=fmt(int(payload.get('cycle', 0))))}"
                f" · 走出时背负：{_burden_text(R, payload)}")
    if kind == "SUCCESSION":
        # 席位名与三句模板都按【这一帧所属阶段】取：前三阶段它还没有泰坦职位。
        locus = R.seat(namer, frame, payload["locus"])
        was, now = payload.get("from"), payload.get("to")

        def nm(serial):
            """只认【人】的名字。名随人走 —— 认不出来就无名，绝不拿职位名顶替。

            详细档（3）下，连无名者也带上编号，便于一路追这个人到底是谁。
            """
            hit = cast.resolve(serial) if cast else None
            if hit is None and lv >= 3 and serial is not None:
                return f"{R.term('agent_unsurfaced')}#{int(serial)}"
            return hit
        if now is None:                        # 失位
            who = nm(was)
            if not who:
                return None
            return R.text("stall", "succession_fall", frame).format(locus=locus, who=who)
        who = nm(now)
        if who is None:                        # 接掌者无名 —— 无名者之间的流转是噪声
            return None
        out = nm(was)                          # 退位者也可能无名：那就不提他
        note = (R.text("stall", "succession_displaced", frame).format(who=out)
                if out else "")
        return R.text("stall", "succession_rise", frame).format(
            locus=locus, who=who, note=note)
    if kind == "VERDICT":
        return f"★ 裁决：{R.verdict_label(payload['verdict'])} ⇒ 实验坍缩为「结束」"
    if kind == "CONCLUSION_REACHED":
        cn = R.verdict_label(payload["conclusion"])
        return f"◆ 结论达成：{cn}（{payload['id']}）"
    if kind == "ASCENSION":
        return (f"◆ 演算主体升格：未被改写的"
                f"「{R.verdict_label(payload['conclusion'])}」结论外溢而出")
    if kind == "PRUNE":
        return (f"⛔ 时间线剪枝：节点 {payload['node']} 未在 {fmt(payload['by'])} 帧前发生 "
                f"—— 提前停下（只用于检索）")
    return None


def violation_line(R, payload):
    """逐帧违例状态 → 世界内的一句话。实时输出只关心【出现了什么】。

    只报叙事上有意义的几类（神位空缺 / 黑潮），"尚未证伪"这类常态不报。
    """
    labels = {"VACANT": R.term("vacancy"), "OVERFLOW": R.term("overflow")}
    told = [labels[c] for c in (payload.get("codes") or ()) if c in labels]
    return "出现违例 → " + "、".join(told) if told else None


class LiveStream:
    """实时编年史：引擎每抛一条事件，立刻翻译并输出。

    它只读 —— 删掉它，演算结果逐帧不变。仅实时路径会额外翻译逐帧违例状态。

    sink / event_sink 是给【实时看板】（run.py --serve）用的两个只读旁路：
    编年史行与时间线打点各喂一份进去，页面便能一边演算一边长出来。
    """

    def __init__(self, ctx, data, seed, to_stdout=True, path=None,
                 sink=None, event_sink=None):
        self.ctx = ctx
        self.data = data
        self.seed = int(seed)
        self.R = Renderer(ctx)
        self._reuse_start = None              # 正在复用的那段区间（见 on_event）
        self._switch = None                   # 「自动更替 → 再创世」的切换帧（见 on_event）
        self._rid = 0                         # 事件号：与静态导出的 `traj.records` 下标同源
        self.cast = None                      # 首次事件时才拿得到 namer
        self.V = Verbosity(ctx.params.get("verbosity"))
        self.to_stdout = to_stdout
        self.fh = open(path, "w", encoding="utf-8") if path else None
        self.path = path
        self.folder = ChronicleFolder(self._emit_line)   # A5：连续同型事件折叠
        self.sink = sink                      # (frame, text, badge, rid) → 看板编年史
        self.event_sink = event_sink          # (frame, kind, payload, rid) → 看板时间线

    def _emit_line(self, rid, frame, text, badge):
        if self.sink is not None:
            self.sink(frame, text, badge, rid)
        line = f"  帧{fmt(frame):>9}  {self.R.locale(frame)}  {text}"
        if badge:
            line += "  " + badge
        self._write(line)

    def _write(self, text):
        if self.to_stdout:
            print(text, flush=True)
        if self.fh:
            self.fh.write(text + "\n")
            self.fh.flush()

    def header(self):
        gen = self.data.genesis
        self._write(BAR)
        self._write(f"  实时演算 · 命题「{gen['proposition']['note']}」"
                    f"  [{gen['proposition']['id']}]")
        self._write(f"  世界种子 {self.seed}    预设 {self.data.preset['name']}")
        self._write(BAR)

    def on_event(self, frame, kind, payload, clock, namer):
        rid = self._rid                        # 事件号：每条事件递增一次（与静态导出同序）
        self._rid += 1
        if self.cast is None:
            self.cast = Cast(self.R, namer)
        # 永劫回归期沿参考轨道复用：把那段时间从历法里扣掉（否则循环期的到访帧会被
        # 讲成"过了几万年"）。实时路径拿不到定型后的 `traj.spans`，只能边跑边登记：
        # 循环开启时先记 start，走出时补 end。
        if kind == "DEADLOCK_LOOP" and payload.get("start") is not None:
            self._reuse_start = int(payload["start"])
            self.R.add_reuse(self._reuse_start)
        elif kind == "DEADLOCK_END" and self._reuse_start is not None:
            self.R.add_reuse(self._reuse_start, frame)
            self._reuse_start = None
        # 世代更迭的三档名字：`renewal.mode` 落进覆盖表那一刻起叫「主动更替」（第三阶段），
        # 跨过 `DOMAINS_EXHAUSTED`（第四阶段）才叫「再创世」—— 两处界各有出处，见 advance_label。
        if kind == "PROTOCOL_REWRITTEN" and self._switch is None \
                and "renewal.mode" in (payload.get("changed") or {}):
            self._switch = int(frame)
        # 阶段语汇与「第 N 次循环」也要边跑边记：世界内起点、换代帧各记一份
        # （与 `myth_phase_frame` / `cycle_frames` 同源 —— 都读这两条事件）。
        if kind == "DOMAINS_EXHAUSTED":
            self.R.add_myth_from(frame)
        elif kind == "PROMOTION":
            self.R.add_cycle(frame)
        if kind == "EMERGENCE":
            self.cast.see(payload)            # 先记名，再翻译这条涌现
        if self.event_sink is not None:
            # 时间线打点照【全部事件】走，与静态导出同一口径 —— 不受详细程度影响。
            self.event_sink(frame, kind, payload, rid)
        if kind == "VIOLATION_STATE":
            if self.V.level(kind) < 2:        # 逐帧违例：常规档以上才实时刷
                return
            text = violation_line(self.R, payload)
            if text is None:
                return
            # 违例不参与折叠，但它可能夹在一条待折叠的串中间 —— 先把串吐出来保证顺序。
            self.folder.close()
            self._emit_line(rid, frame, text, None)
            return
        if not self.V.allow(kind, payload):
            return
        text = chronicle_line(self.R, namer, kind, payload, self.cast,
                              lv=self.V.level(kind), frame=frame,
                              advance_label=(advance_label(self.R, self._switch, frame)
                                             if kind == "PROMOTION" else None))
        if text is None:
            return
        # 光历是【帧】的刻度映射（见 calendar.json）；world_clock 只是轮回计数，
        # 拿它当时间轴会一直停在创世期，故一律用帧换算。
        self.folder.feed(rid, frame, kind, payload, text)

    def footer(self, traj):
        # 走到帧那一刻的历法/语汇：复用区间、换档帧、换代帧都换成定型后的那份
        # （实时登记的那份可能还差最后几段）。
        self.R = Renderer(self.ctx, traj.spans, cycle_frames(traj),
                          myth_phase_frame(traj))
        R = self.R
        self.folder.close()
        cn = R.verdict_label(traj.verdict)
        self._write(BAR)
        self._write(f"  演算结束：帧{fmt(traj.reached_frame)} → "
                    f"{R.locale(traj.reached_frame)} · 裁决 {cn} · "
                    f"实际迭代 {fmt(traj.iterations)}")
        if self.path:
            self._write(f"  编年史已写入 {self.path}")
            if not self.to_stdout:
                # 只落盘（未配 --live）时编年史一个字都不刷屏 —— 至少把去向报一句，
                # 否则自动编号的文件名用户无从得知。
                print(f"编年史已写入：{self.path}", flush=True)
        self._write(BAR)

    def close(self):
        if self.fh:
            self.fh.close()


def chronicle_rows(ctx, traj):
    """把 Telemetry 翻译成编年史【行】。纯渲染，不参与演算。

    返回 [(frame, text, badge|None, rid), ...]。badge 只在连续同型事件被折叠时出现；
    `rid` 是这条事件在记录流里的【事件号】（折叠取首条），与时间线打点同源 ——
    页面双击一个节点时据此精确命中它自己那条，而不是同一帧里排在最前的那条。
    报告（纯文本）与可视化（可检索列表）共用这一份口径 —— 报告怎么讲，页面就怎么讲。
    """
    R = Renderer(ctx, traj.spans, cycle_frames(traj), myth_phase_frame(traj))
    namer = traj.namer
    cast = Cast(R, namer)
    V = Verbosity(ctx.params.get("verbosity"))
    rows = []

    def emit_row(rid, frame, text, badge):
        rows.append((frame, text, badge, rid))

    # 世代更迭的名字分三档：更早【自动更替】、协议改写起【主动更替】、第四阶段起【再创世】。
    # 两处界：前者取 `renewal.mode` 进覆盖表那一帧，后者取 `DOMAINS_EXHAUSTED`（R.phase_of 判）。
    switch = renewal_switch_frame(traj)

    def advance_name(frame):
        return advance_label(R, switch, frame)

    folder = ChronicleFolder(emit_row)
    for rid, (frame, kind, payload) in enumerate(traj.records):
        if kind == "EMERGENCE":
            cast.see(payload)
        if not V.allow(kind, payload):
            continue
        text = chronicle_line(R, namer, kind, payload, cast, lv=V.level(kind),
                              advance_label=(advance_name(frame)
                                             if kind == "PROMOTION" else None),
                              frame=frame)
        if text is not None:
            folder.feed(rid, frame, kind, payload, text)
    folder.close()
    return rows


def chronicle(ctx, traj):
    """编年史全文（纯文本）。连续同型事件由 ChronicleFolder 折叠成一条 + 计数。"""
    out = []
    for frame, text, badge, _rid in chronicle_rows(ctx, traj):
        line = f"  帧{fmt(frame):>9}  {text}"
        if badge:
            line += "  " + badge
        out.append(line)
    return "\n".join(out)


def _progress_note(namer, ctx, traj):
    """裁决依据（只读）：把「证真 / 证伪」背后的连续量摊开，并点明它是【经验裁决】。

    纯只读：只读 traj.final.loci 的 progress 与位表 id，不碰任何状态、也不参与裁决。
    `progress` = 单独消融该席后迷你世界的熵 / 阈值 τ —— ≥τ 记为该席被证伪，越接近越勉强。
    这是**测量**而不是形式证明：故报告如实称它为「经验裁决」，别让「证真」二字
    看起来像逻辑证明。返回若干行文本；缺读数（例如没有末尾状态）时返回空列表。
    """
    loci = getattr(traj.final, "loci", None) if traj.final is not None else None
    if not loci:
        return []
    tau = float(ctx.params.get("tau_falsify", 0.0))
    pros = [float(l.progress) for l in loci]

    def name(i):
        hit = namer.title_by_id(loci[i].id)
        return hit[1] if hit and hit[1] else loci[i].id

    total = len(pros)
    done = [i for i, v in enumerate(pros) if v >= tau]
    lo = min(range(total), key=lambda k: pros[k])
    margin = (pros[lo] / tau) if tau else float("inf")
    lines = ["经验裁决：各席读数为「单独消融该席后迷你世界的熵 / 阈值 τ」，"
             "≥τ 即该席被证伪 —— 这是【测量】而非形式证明"]
    lines.append("　　" + " · ".join(f"{name(i)} {pros[i]:.2f}/{tau:g}"
                                     for i in range(total)))
    lines.append(f"　　达标 {len(done)}/{total}（{len(done) / total:.0%}）"
                 f" · 最勉强「{name(lo)}」{pros[lo]:.2f}（裕度 {margin:.2f}×τ）")
    gap = [i for i in range(total) if i not in done]
    if gap:
        lines.append("　　尚未证伪：" + "、".join(
            f"{name(i)}({pros[i]:.2f})" for i in gap[:6])
            + (" 等" if len(gap) > 6 else ""))
    return lines


def report(ctx, data, traj, results, explore=False):
    R = Renderer(ctx, traj.spans, cycle_frames(traj), myth_phase_frame(traj))
    p = ctx.params
    gen = data.genesis
    out = []
    out.append(BAR)
    out.append("  δ-me13「翁法罗斯」演算报告")
    out.append(BAR)
    out.append(f"  命题        {gen['proposition']['note']}   [{gen['proposition']['id']}]")
    out.append(f"  初始变量域  {' → '.join(R.domain(v) for v in gen['domain']['initial_variable'])}")
    out.append(f"  位表        {len(ctx.loci)} 位 × {p['dim']} 维")
    out.append(f"  世界种子    {ctx.seed}    预设 {data.preset['name']}")
    if getattr(ctx, "fast", 0) > 1:
        out.append(f"  ⚠ 测试提速模式（时间刻度 ×1/{ctx.fast}）—— 只验机制连通，"
                   f"帧号类断言与时间线不适用")
    st_style = traj.namer.style
    out.append(f"  音位风格    两音节为主，每 {st_style['long_period']} 个里出一个三音节 · "
               f"闭音节偏好 {st_style['coda_tilt']:+.2f} · "
               f"复辅音偏好 {st_style['onset_tilt']:+.2f}   （只影响命名，不改轨迹）")
    out.append(f"  帧预算      {fmt(traj.total_frames)}")
    out.append(f"  实际迭代    {fmt(traj.iterations)}   "
               f"（沿参考轨道复用 {fmt(traj.skipped_frames)} 帧 —— 结构未变，不算第二遍）")
    verb = {k: int(v) for k, v in (ctx.params.get("verbosity") or {}).items()}
    odd = {k: v for k, v in verb.items() if v != 3}
    if odd:
        out.append("  输出详细度  "
                   + " · ".join(f"{k}={v}" for k, v in sorted(odd.items()))
                   + "   （0 静默 / 1 摘要 / 2 常规 / 3 详细；未列出的类别为 3）")
    st = traj.final
    out.append(f"  走到帧      {fmt(traj.reached_frame)}  → {R.locale(traj.reached_frame)}")
    out.append(f"  最终状态    {R.term('round')} {st.round} · {R.term('promotion')} {st.promotions} 次 · "
               f"熵 {st.entropy:.4f} · 黑潮强度 {st.noise:.4f}")
    # 世界纹理（只读读数）：把末态压成三个低维统计，一眼看出世界「抱团 / 集中 / 分块」到
    # 什么程度。它不进摘要指纹、不参与演化 —— 纯观测。
    tex = texture_of(traj.reached_frame, st)
    out.append(f"  世界纹理    相似度中位 {tex[1]:.3f} · 能量集中度 {tex[2]:.3f} · "
               f"区域连通分量 {tex[3]}   （只读观测，不进指纹）")
    if traj.deadlock:
        out.append(f"  {R.term('deadlock')}    轮次 {fmt(st.cycles)} · "
                   f"尝试 {fmt(st.attempts)} 次 · 留痕 {fmt(st.traces)} 次"
                   f"（结构长期不推进 ⇒ 后续帧沿参考轨道复用，不再逐帧重算）")
    out.append("")

    out.append("  阶段目录    （每一档跑多少帧 · 新装了什么机制 · 期间发生了什么 · 该档的结论）")
    for row in stage_table(ctx, data, traj):
        mark = "①②③④⑤⑥⑦⑧⑨"[row["index"]] if row["index"] < 9 else f"({row['index'] + 1})"
        asm = "、".join(row["gates"]) or "—"
        extra = ("　覆盖 " + "、".join(f"{k}={v}" for k, v in sorted(row["params"].items()))
                 if row["params"] else "")
        note = f"　（{row['promotion_note']}）" if row["promotion_note"] else ""
        budget = "—" if row["budget"] is None else fmt(row["budget"])
        out.append(f"    {mark} {row['name']}  帧 {fmt(row['start'])}–{fmt(row['end'])}"
                   f"（预算 {budget}） 新装 {asm}{extra}{note}")
        if row["conclusion"]:
            out.append(f"       └ {row['conclusion']}")
        if row.get("myth_note"):
            # 这一档正是「世界内」起点 ⇒ 把「称谓为何而换」写在结论下面
            out.append(f"       ⇄ {row['myth_note']}")
        out.append(f"       读数：涌现 {fmt(row['born'])} {row['born_unit']} · "
                   f"{row['promotion_label']} {fmt(row['promotions'])} 次 · "
                   f"{row['fell_word']} {fmt(row['fell'])} {row['fell_unit']}")
    out.append("")

    # 世界规则 · 观测量：`rule_matrix` 在 6 个观测量上的投影（名字取自 config/mapping.json）。
    # 这两样都【不参与演化】、也不进 digest / world_signature —— 故「主动更替」改它们
    # 不动轨迹，效果只在这里看得到。
    obs = getattr(traj.final, "observables_vec", None)
    if obs is not None and len(obs):
        switch = renewal_switch_frame(traj)
        src = ("席位向量（自动更替循环）" if switch is None
               else f"决策账本（主动更替 @{fmt(switch)}）")
        ren = {k: v for k, v in (getattr(traj.final, "overrides", {}) or {}).items()
               if k.startswith("renewal.")}
        if "renewal.factor" in ren:
            gate = float(p.get("renewal_consensus", 0.0))
            now = consensus(traj.final)
            src += (f" · 主导支 {int(ren['renewal.factor'])}"
                    f" · 共识 {float(ren.get('renewal.share') or 0.0):.1%}"
                    f" · 共识门 ≥ {gate:.3f}（末态 {now:.3f}）")
        names = list(getattr(ctx, "obs_names", []) or [])
        cells = " · ".join(f"{names[i] if i < len(names) else i} {float(v):.4f}"
                           for i, v in enumerate(obs))
        out.append(f"  世界规则    （换代时把什么当成下一世的规则）{src}")
        out.append(f"    {cells}")
        out.append("")

    out.append("【一】演算历程")
    out.append(chronicle(ctx, traj) or "  （无）")
    out.append("")

    out.append("【二】涌现出来的角色（数据文件里没有任何一个）")
    src = ("名字来自预设锚定层（外部绑定，不改轨迹）" if data.preset.get("anchors")
           else "名字由音位层自行生成")
    out.append(f"  · {src} · 名随人走：一个名字钉在一个个体上，席位换手就换名")
    out.append("  · 「承位」列是【职位】（负世 / 岁月 / 门径…），不是人名")
    # 城邦只属于第四阶段 —— 世界还没走到那一档（如 emergent）就不摆这一列。
    show_city = myth_phase_frame(traj) is not None
    if show_city:
        out.append("  · 「城邦」列是可空缺的渲染层绑定（只填有考据的席位；无则显示 —）")
    if not traj.personas:
        out.append("  （无 —— 本次演算没有个体满足全部四条判据）")
    else:
        head = f"  {'承位':<10}"
        if show_city:
            head += f"{'城邦':<14}"
        out.append(head + f"{'世界名':<12}{'拉丁名':<14}{'机器编号':<14}{'涌现帧':>8}  能力")
        for per in traj.personas[:40]:
            latin, hanzi = traj.namer.persona_name(per)
            if per.locus_order is not None:
                lid = ctx.loci[per.locus_order].id
                loc = traj.namer.title_by_id(lid)[1]
                city = R.city(lid) or "—"
            else:
                loc, city = "—", "—"
            caps = ",".join(sorted(per.capabilities)) or "—"
            row = f"  {loc:<10}"
            if show_city:
                row += f"{city:<14}"
            out.append(row + f"{hanzi:<12}{latin:<14}"
                       f"{traj.namer.machine_name_of(per):<14}{fmt(per.surfaced_frame):>8}  {caps}")
        if len(traj.personas) > 40:
            out.append(f"  …… 共 {len(traj.personas)} 位")
    out.append("")

    out.append("【三】断言核对（剧情在这里，但它是断言）")
    if explore:
        out.append("  （探路档：跳过 —— 压缩了时间刻度，帧号类期望不再适用）")
    else:
        npass = sum(1 for r in results if r.ok)
        for r in results:
            mark = "PASS" if r.ok else "FAIL"
            extra = f"  {r.where}" if r.where else ""
            out.append(f"  [{mark}] {r.name:<32} expect={r.expect!r:<12} got={r.got!r}{extra}")
        out.append(f"  → {npass}/{len(results)} 通过")
    out.append("")

    out.append("【四】预设时间线核对（引擎从不读它，只用于核对 / 种子检索）")
    if explore:
        out.append("  （探路档：跳过 —— 同上）")
    elif not data.timeline_nodes:
        out.append("  （本预设没有 timeline.json）")
    else:
        feats = extract(traj, ctx)
        tl = check_timeline(data.timeline_nodes, feats)
        for r in tl:
            mark = "PASS" if r.ok else "FAIL"
            dl = f"  最晚帧 {fmt(r.deadline)}" if r.deadline is not None else ""
            out.append(f"  [{mark}] {r.id:<24} got={r.got!r:<22}{dl}  {r.label}")
        out.append(f"  → {sum(1 for r in tl if r.ok)}/{len(tl)} 命中")
    out.append("")

    out.append("【五】判定与结论")
    cn = R.verdict_label(traj.verdict)
    when = f"，判定于第 {fmt(traj.verdict_frame)} 帧" if traj.verdict_frame is not None else ""
    out.append(f"  裁决        {cn}（{traj.verdict}）  "
               f"{R.stop_label(traj.stop_reason)}{when}")
    out.append(f"  {traj.conclusion['template']}   [{traj.conclusion['id']}]")
    # 议题框架（conclusions.json 的 _framing）：正名 —— 这是经验裁决，不是形式证明。
    framing = (getattr(ctx, "conclusions", None) or {}).get("_framing")
    if framing:
        out.append(f"  · 议题框架  {framing}")
    lines = _progress_note(traj.namer, ctx, traj)
    if lines:
        out.append(f"  · 裁决依据  {lines[0]}")
        for line in lines[1:]:
            out.append(f"              {line}")
    if getattr(traj, "conclusion_trail", None):
        chain = " → ".join(f"{fmt(f)}:{R.verdict_label(c)}"
                           for f, c in traj.conclusion_trail)
        out.append(f"  结论链      {chain}")
    if getattr(traj, "ascended", False):
        out.append(f"  · 升格     未被改写的「{cn}」结论外溢（原著中的绝灭大君）")
    if getattr(traj.final, "overrides", None):
        out.append("  · 规则覆盖  " + "、".join(
            f"{k}={v}" for k, v in sorted(traj.final.overrides.items())))
    mr = int(traj.final.score.get("memory_repaired", 0.0))
    if mr:
        out.append(f"  · 记忆再造  {mr} 席由收拢来的记忆补上（本地永远补不上的那一席）")
    if traj.deadlock:
        span = sum(e - s for _, s, e in traj.spans)
        out.append(f"  · {R.term('deadlock')}：结构长期不推进，后续帧沿参考轨道复用，"
                   f"共 {fmt(span)} 帧（世界自己的走向，引擎未预设此情形）")
    if traj.converged:
        out.append(f"  · 轨道收敛：{R.term('converged')}（{R.term('memory')}路径）")
    out.append(BAR)
    return "\n".join(out)


def _next_free(directory, stem, ext=".txt"):
    """在 directory 里找一个还【不存在】的 `stemN.ext`（N 从 1 起）。

    这样反复跑也不会把上一份编年史覆盖掉 —— 每次留一份。
    """
    os.makedirs(directory, exist_ok=True)
    n = 1
    while True:
        path = os.path.join(directory, f"{stem}{n}{ext}")
        if not os.path.exists(path):
            return path
        n += 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=None)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--json", action="store_true", help="额外输出机器可读结果")
    ap.add_argument("--export", nargs="?", const="", default=None, metavar="PATH",
                    help="导出单文件 HTML 可视化 dashboard（十二席状态 / 指标曲线 / "
                         "事件时间线 + 折叠后的编年史）；只读渲染层，不改轨迹。"
                         "不给 PATH 时写到 ./dashboard/翁法罗斯-可视化.html")
    ap.add_argument("--serve", nargs="?", type=int, const=8765, default=None,
                    metavar="PORT",
                    help="演算时在本地起一台【只读】看板服务并自动打开浏览器："
                         "页面随演算实时生长（十二席 / 曲线 / 时间线 / 编年史），"
                         "演完即转为可暂停 / 播放 / 跳到任意时刻的回放台。"
                         "默认端口 8765；演完会一直挂着以便回看，Ctrl+C 结束。")
    ap.add_argument("--serve-reload", action=argparse.BooleanOptionalAction,
                    default=True,
                    help="配 --serve 用：演算跑完后自动把页面重载成【完整静态页】"
                         "（与 --export 内容一致），默认开。用 --no-serve-reload 关掉，"
                         "则改为在右下角弹一个「演算完成」提示，由你点「立即查看」再切过去。")
    ap.add_argument("--no-open", action="store_true",
                    help="配 --serve 用：不自动打开浏览器（自己访问打印出的地址）")
    ap.add_argument("--dump-anchors", action="store_true", help="导出命名标定语料")
    ap.add_argument("--preset", default="emergent",
                    help="presets/ 下的预设名；emergent = 涌现版（默认）")
    ap.add_argument("--live", action="store_true",
                    help="演算过程中实时输出编年史（谁诞生了 / 谁介入了 / 发生了什么）")
    ap.add_argument("--log", nargs="?", const="", default=None, metavar="PATH",
                    help="把实时编年史同时写入该文件（不配 --live 时只落盘、不刷屏）。"
                         "不给 PATH 时自动写到 ./logs/翁法罗斯编年史_演算N.txt"
                         "（N 依次递增，不覆盖已有文件）")
    ap.add_argument("--list-presets", action="store_true", help="列出可用预设")
    ap.add_argument("--verbosity", default=None, metavar="LVL 或 类别=LVL[,…]",
                    help="输出文本的详细程度：0 静默 / 1 摘要 / 2 常规 / 3 详细。"
                         "可给一个数字（全部类别都置它），也可按类别逐一覆盖："
                         "`--verbosity 2,deadlock=3,emergence=0`。"
                         "可选类别：" + "、".join(sorted(_VERB_DEFAULT)) +
                         "。缺省取 config/params.json 的 verbosity（全 3＝最详细）")
    ap.add_argument("--explore", nargs="?", type=int, const=100, default=None,
                    metavar="K",
                    help="探路档：把时间刻度与预设的事件帧按 K 压缩（默认 K=100），"
                         "并【跳过帧号类断言与时间线核对】—— 只验机制连通，"
                         "快但不可作为验收（帧号、锚定编号都会失效）")
    ap.add_argument("--fast", nargs="?", type=int, const=100, default=None,
                    metavar="K", help="--explore 的旧名，等价")
    args = ap.parse_args()

    if args.list_presets:
        d = os.path.join(ROOT, "presets")
        names = sorted(n for n in os.listdir(d)
                       if os.path.exists(os.path.join(d, n, "preset.json"))) if os.path.isdir(d) else []
        print("可用预设：emergent（涌现版）")
        for n in names:
            print("  " + n)
        return 0

    # --log 不给路径：自动落到 ./logs/翁法罗斯编年史_演算N.txt（N 递增，不覆盖旧的）。
    if args.log == "":
        args.log = _next_free(os.path.join(ROOT, "logs"), "翁法罗斯编年史_演算")

    data = DataSet(ROOT, preset=args.preset)
    # 词表可由预设覆盖：同一段演算，预设可以把它讲成另一个世界的神话。
    ctx = Config(ROOT, lex_overlay=data.preset.get("lexicon"))
    # 输出详细程度：命令行优先于 config/params.json（它只影响渲染，不影响演算）。
    if args.verbosity:
        merged = dict(ctx.params.get("verbosity") or {})
        try:
            merged.update(parse_verbosity(args.verbosity))
        except ValueError as err:
            ap.error(str(err))
        ctx.params["verbosity"] = merged
    explore = args.explore if args.explore is not None else args.fast
    if explore and int(explore) > 1:
        apply_fast(ctx, data, int(explore))

    # 解析种子（与 run() 同一口径），好在实时头部就把世界号打出来。
    seed = args.seed
    if seed is None:
        seed = data.preset.get("seed")
        if seed is None:
            seed = data.genesis.get("seed", 0)

    # 实时看板（--serve）：先起服务、把空看板交给浏览器，再开始演算 ——
    # 于是打开就看到世界在长。它只读：删掉这一整块，演算逐帧不变。
    board = None
    board_url = None
    if args.serve is not None:
        from engine.live import LiveState, make_watch, serve as serve_board
        total = int(args.frames if args.frames is not None
                    else ctx.params.get("frames", 20000))
        board = LiveState(ctx, data)
        page = build_live_shell(
            ctx, total,
            title=f"δ-me13「翁法罗斯」演算 · {data.preset['name']} · 实时",
            autoreload=args.serve_reload)
        _srv, board_url = serve_board(board, page, port=args.serve,
                                      open_browser=not args.no_open)
        print(f"实时看板已启动：{board_url}"
              f"（演算每前进一步，页面自动更新；"
              f"{'演完自动切到与导出一致的完整页' if args.serve_reload else '演完右下角会弹「立即查看」提示'}"
              f"）", flush=True)

    # 指标采样器（A3）：导出可视化与实时看板都需要逐帧读数。
    # 它只读、从不剪枝（与 watch 同接口）—— 挂上与否，演算逐帧一致。
    sampler = None
    if args.export is not None or board is not None:
        total = int(args.frames if args.frames is not None
                    else ctx.params.get("frames", 20000))
        sampler = Sampler(total)

    # 实时编年史：--live / --log 负责刷屏与落盘；--serve 则把同一份行与事件喂给看板。
    row_sink = event_sink = None
    if board is not None:
        R0 = Renderer(ctx)
        row_sink = lambda frame, text, badge, rid: board.add_row(frame, text, badge, rid)
        event_sink = lambda frame, kind, payload, rid: board.add_event(
            R0, frame, kind, payload, rid)
    stream = None
    if args.live or args.log or board is not None:
        stream = LiveStream(ctx, data, seed, to_stdout=args.live, path=args.log,
                            sink=row_sink, event_sink=event_sink)
        if args.live or args.log:
            stream.header()

    watch = sampler
    if board is not None:
        watch = make_watch(board, sampler)

    # 命名器由【应用层】自己造 —— 内核只把它当不透明句柄携带（见 engine/core.py::run）。
    # 条件谓词同理：内核只负责"每帧问一次"，条件的写法与求值都在服务层（engine/conditions.py）。
    # 预设里没写 when 时，内核那边一个条件都不会挂 ⇒ 与不传它逐位相同。
    namer = Namer(ctx, data.anchors)
    traj = run(ctx, data, seed=seed, max_frames=args.frames, namer=namer,
               rules=eval_condition,
               on_event=(stream.on_event if stream else None),
               watch=watch)
    # 机器编号按【登记次序】一次发齐 —— 发号会推进计数器，晚发 / 漏发都会串号。
    namer.bind_machines(traj.personas)

    if board is not None:
        board.finish(traj, summary_cards(ctx, traj, data.genesis),
                     verdict_label=Renderer(ctx).verdict_label(traj.verdict))

    if stream:
        stream.footer(traj)
        stream.close()

    results = [] if explore else AssertionRunner(ctx, data).run(traj)

    print(report(ctx, data, traj, results, explore=bool(explore)))

    # 可视化页面：导出（落盘）与实时看板的【收官页】用的是**同一次** build_html ——
    # 于是 --serve 的世界跑完后，页面重载出来就是与 --export 逐字一致的那张
    # （不依赖导出文件是否落盘）。
    if args.export is not None or board is not None:
        html_text = build_html(ctx, traj, sampler.points if sampler else None,
                               lines=chronicle_rows(ctx, traj),
                               title=f"δ-me13「翁法罗斯」演算 · {data.preset['name']}",
                               data=data,
                               texture=sampler.texture if sampler else None)
        if board is not None:
            board.set_final_page(html_text)     # 实时页据此自动重载成完整静态页
        if args.export is not None:
            path = args.export or os.path.join(ROOT, "dashboard", "翁法罗斯-可视化.html")
            if not os.path.splitext(path)[1]:
                path += ".html"
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(html_text)
            nbytes = len(html_text.encode("utf-8"))
            print(f"已导出可视化 dashboard：{path}"
                  f"（{nbytes:,} 字节 · 单文件、零外部依赖）")

    if args.dump_anchors:
        path = os.path.join(ROOT, "data", "anchors.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            for a in traj.namer.export_anchors(traj.personas):
                f.write(json.dumps({"fingerprint": a["fingerprint"],
                                    "latin": a["latin"], "hanzi": a["hanzi"],
                                    "name": [a["latin"], a["hanzi"]]},
                                   ensure_ascii=False) + "\n")
        print(f"已导出 {len(traj.personas)} 条标定语料到 {path}")

    if args.json:
        print(json.dumps({
            "seed": ctx.seed,
            "iterations": traj.iterations,
            "skipped": traj.skipped_frames,
            "promotions": traj.final.promotions,
            "deadlock": traj.deadlock,
            "converged": traj.converged,
            "conclusion": traj.conclusion["id"],
            "progress": {l.id: round(float(f.progress), 4)
                         for l, f in zip(ctx.loci, traj.final.loci)},
            "personas": [{"machine": traj.namer.machine_name_of(p),
                          "name": list(traj.namer.persona_name(p)),
                          "locus_order": p.locus_order,
                          "surfaced": p.surfaced_frame} for p in traj.personas],
            "assertions": {r.name: r.ok for r in results},
        }, ensure_ascii=False, indent=2))

    if board is not None:
        # 演算已完，但看板还挂着 —— 好让人在页面上回放 / 跳到任意时刻细看。
        print(f"\n实时看板仍在 {board_url} 提供服务（看板已转为回放台，Ctrl+C 结束）。",
              flush=True)
        try:
            while True:
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("\n已关闭实时看板。")

    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())