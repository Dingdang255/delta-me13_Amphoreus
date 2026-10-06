"""tools 公共脚手架（不参与演算，只用于验证判据）。

提供：加载、摘要统计、逐迭代捕获、以及把 Config 复制后做等距改写的工具。
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from engine.core import run                      # noqa: E402
from engine.loader import Config, DataSet, apply_fast   # noqa: E402

#: 各只读工具报告里那条分隔线 —— 原先 7 个工具各写一遍，统一到这里。
BAR = "─" * 72


def load(root=ROOT, preset="plot", fast=0):
    """装载一次演算。

    默认走 plot 预设 —— 剧本（扰动流 / 断言 / 词表）现在都挂在预设上，
    涌现版（preset=None）没有剧本，世界会很快自行抵达结论、验不到死循环。
    """
    data = DataSet(root, preset=preset)
    ctx = Config(root, lex_overlay=data.preset.get("lexicon"))
    if fast and int(fast) > 1:
        apply_fast(ctx, data, int(fast))
    return ctx, data, root


def jsonl(path):
    """读「一行一条 JSON」的文件（空行略过；文件不存在返回空表）。

    `presets/*.jsonl` 与 `data/*.jsonl` 都是这个形状，几个只读工具各自抄了一份 ——
    统一到这里，免得行/空行的口径再漂移。
    """
    import json

    out = []
    if not os.path.exists(path):
        return out
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def num(txt):
    """把 `"3"` / `"3.0"` / `"0.5"` 解析成 int 或 float（整数值给 int）。"""
    f = float(txt)
    return int(f) if f.is_integer() else f


def esc(txt):
    """HTML 最小转义（`& < >`）—— `parallels` / `sensitivity` 的 SVG/HTML 共用这一份。"""
    return str(txt).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def fmt(n) -> str:
    """千分位整数（`12345` → `"12,345"`）—— 各只读工具的报告共用。"""
    return f"{int(n):,}"


def serial_of(key):
    """`"serial:<n>"` → n；形状不符（或 n 非整数）则 None。锚定层的键都过它。"""
    k = str(key or "")
    if not k.startswith("serial:"):
        return None
    try:
        return int(k.split(":", 1)[1])
    except ValueError:
        return None


#: 低饱和配色（与 `engine/viz.py` 的时间线打点同一路数）—— 各只读扫描器共用。
PALETTE = ("#7fd0ff", "#7fe0a0", "#ffd27f", "#ff8a8a", "#b28dff",
           "#ff9ed6", "#8ab4ff", "#e8c06a")


def resolve_seeds(txt, default="0:8"):
    """种子序列：`A:B`（起:个数）或 `a,b,c`；也接受已是列表的取值。

    `txt` 为空（None / 空串）时用 `default` —— 各工具的默认不同，故由调用方传。
    """
    if isinstance(txt, list):
        return [int(x) for x in txt]
    txt = str(txt or default)
    if ":" in txt:
        start, count = txt.split(":", 1)
        return list(range(int(start), int(start) + int(count)))
    return [int(x) for x in txt.split(",")]


def seat_spans(ctx, data, seed=None, frames=None):
    """逐帧观测十二席的「有人坐」段表：`spans[i] = [{"start","end","serial"}, …]`。

    只记【有人坐】的段（空档不进表 ⇒ 「上一任」就是上一段有人坐的段）；口径按
    `register.slots[i].owner` 算 —— 逐出 / 接掌这类机制看的正是这个字段。
    返回 `(spans, 末次再创世帧 | None, traj)`。
    """
    seats = len(ctx.loci)
    spans = [[] for _ in range(seats)]
    cur = [None] * seats
    prom = [None]

    def watch(n, st, traj):
        for i, slot in enumerate(st.register.slots):
            if slot.owner == cur[i]:
                continue
            if cur[i] is not None:                   # 旧的一段落幕
                spans[i][-1]["end"] = n
            cur[i] = slot.owner
            if slot.owner is not None:               # 新的一段开场
                spans[i].append({"start": n, "end": None,
                                 "serial": int(slot.owner)})
        return True

    def on_event(frame, kind, payload, clock, namer):
        if kind == "PROMOTION":
            prom[0] = frame

    namer = _default_namer(ctx, data)
    traj = run(ctx, data, seed=seed, max_frames=frames, namer=namer,
               on_event=on_event, watch=watch)
    namer.bind_machines(traj.personas)      # 机器编号按登记次序一次发齐
    return spans, prom[0], traj


def summary(traj, ctx) -> dict:
    """一次运行的【可观测量】。判据 1/3/5 比对的就是它。"""
    st = traj.final
    return {
        "iterations": traj.iterations,
        "skipped_frames": traj.skipped_frames,
        "promotions": st.promotions,
        "round": st.round,
        "domain_index": st.domain_index,
        "domains_exhausted": bool(st.domains_exhausted),
        "deadlock": bool(traj.deadlock),
        "converged": bool(traj.converged),
        "conclusion": traj.conclusion["id"],
        "personas": len(traj.personas),
        "entropy": round(float(st.entropy), 6),
        "violations": dict(sorted(traj.violation_counts.items())),
    }


def _default_namer(ctx, data):
    """工具侧的默认命名器（表现层物件）—— 内核只把它当不透明句柄携带。"""
    from engine.namer import Namer
    return Namer(ctx, data.anchors)


def capture(ctx, data, frames, namer=None, start_state=None, start_frame=0):
    """跑一次并返回 (traj, [(frame, digest), ...])，用于逐迭代 diff。"""
    cap = []
    namer = namer if namer is not None else _default_namer(ctx, data)
    traj = run(ctx, data, max_frames=frames, trace=False,
               namer=namer, capture=cap,
               start_state=start_state, start_frame=start_frame)
    namer.bind_machines(traj.personas)      # 机器编号按登记次序一次发齐
    return traj, cap


def persona_identity(traj) -> list:
    """角色的【非名字】属性：用于证明换命名器不改变涌现结果。"""
    return [(p.serial, p.surfaced_frame, p.locus_order,
             tuple(sorted(p.capabilities)), p.fingerprint.hex())
            for p in traj.personas]


def diff_captures(a, b):
    """逐迭代比对两份捕获，返回第一条不一致（或 None）。"""
    da, db = dict(a), dict(b)
    keys = sorted(set(da) | set(db))
    for k in keys:
        if da.get(k) != db.get(k):
            return k, da.get(k), db.get(k)
    return None