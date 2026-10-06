#!/usr/bin/env python3
"""遗迹勘测 —— 建议表 #2（遗迹标记）+ #3（考古报告）：同一份数据，一批做。

**遗迹标记**：`RuinSurvey` 挂在 `run(watch=...)` 上逐帧观测十二席，把每一席的历史
压成一份「遗迹档案」——始建 / 终焉帧、累计在位帧数、易主次数、空置次数与帧数、
承位个体编号、峰值承载，以及由阈值派生的标记（未启用 / 终局空置 / 频繁易主 / 长驻）。
不依赖任何专有名词：只有位次、编号与帧号。

**考古报告**：`build_report(...)` 把遗迹档案 + 涌现 + 裁决聚合成三段 ——
【一】遗址总览 ·【二】逐处遗迹 ·【三】终局结论。取词一律经 `engine.render.Renderer`，
本文件不写死任何一个世界内名词 —— 换一份预设 / 词表，同一段演算就被讲成另一个世界。

**红线：只读**。`RuinSurvey` 只往自己的列表里写、返回值恒 `True`（从不剪枝）；
删掉本文件，演算逐帧不变（`tests/test_excavation.py` 有一条专门盯它）。
峰值承载只在【到访帧】上观测 —— 死循环复用期不重算，故那一段的读数可能不完整。

    python tools/excavation.py [--preset plot] [--seed N] [--frames N] [--json]
                               [--churn-min N] [--endure-frac F] [--fast K]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import BAR, fmt, load                          # noqa: E402

from engine.core import run                                  # noqa: E402
from engine.namer import Namer                               # noqa: E402
from engine.render import renderer_for                       # noqa: E402

#: 遗迹标记的显示名。条件写在 `marks_of`，这里只管怎么讲 —— 都是通用词，不含专名。
MARK_LABELS = {
    "never": "未启用",
    "vacant_end": "终局空置",
    "churn": "频繁易主",
    "enduring": "长驻",
}


def _when(R, frame):
    """历法 / 循环读数的括注；这一档还没有历法时 `locale` 返回空串 —— 不摆一对空括号。"""
    txt = R.locale(int(frame))
    return f"（{txt}）" if txt else ""


class RuinSurvey:
    """只读遗迹勘测：逐帧观测十二席的在位史与承载量。

    挂在 `run(watch=...)` 上；只读、只写自己的列表、恒返回 `True`。删掉它，轨迹逐帧不变。
    `spans[i]` 是第 i 席的【有人坐】的段（`{"start", "end", "serial"}`，`end=None`
    表示终局仍在位）；空着的时段不进段表，于是「上一任」就是上一段有人坐的段。

    「有人坐」按 `world_signature()` 的口径：**被压制的位记作空** —— 名册里可能还留着
    原主，但当下这一席没人在位。两条口径若不一致，「终局空置」就会与演算自己的判定打架。
    """

    def __init__(self, locus_ids):
        self.ids = [str(x) for x in locus_ids]
        self.n = len(self.ids)
        self.spans = [[] for _ in range(self.n)]
        self.peak_load = [0.0] * self.n       # 峰值承载量
        self.peak_frame = [None] * self.n     # 峰值所在帧
        self.last_frame = 0                   # 最后一个到访帧
        self.reached_frame = 0
        self._cur = [None] * self.n           # 上一帧的在位者（用于检测换手）

    def __call__(self, frame, st, traj):
        n = int(frame)
        self.last_frame = n
        slots = getattr(getattr(st, "register", None), "slots", ()) or ()
        loci = getattr(st, "loci", ()) or ()
        suppressed = set(getattr(st, "suppressed", ()) or ())
        for i in range(self.n):
            if i < len(slots):
                owner = getattr(slots[i], "owner", None)
                if i in suppressed:          # 被压制的位 = 此刻无人在位（与签名同口径）
                    owner = None
                if owner != self._cur[i]:
                    if self._cur[i] is not None and self.spans[i]:
                        self.spans[i][-1]["end"] = n
                    self._cur[i] = owner
                    if owner is not None:
                        self.spans[i].append({"start": n, "end": None,
                                              "serial": int(owner)})
            if i < len(loci):
                v = float(getattr(loci[i], "load", 0.0))
                if self.peak_frame[i] is None or v > self.peak_load[i]:
                    self.peak_load[i] = v
                    self.peak_frame[i] = n
        return True

    def observe_final(self, traj):
        """把【真终局】补进观测。

        主循环里裁决检查排在 `watch` 之前，一旦裁决即 `break` ⇒ 最后那一步的演化
        没有被观测到（与 `Sampler.ensure_final` 是同一个动机：曲线的右端必须是真终局，
        不是最后一个采样点）。这里再把 `traj.final` 喂一眼，只读、幂等。
        """
        st = getattr(traj, "final", None)
        if st is not None:
            self(int(traj.reached_frame), st, traj)
        return self

    def finalize(self, reached_frame):
        """收口：`reached_frame` 取自 Trajectory（不是最后一个到访帧 —— 复用期会跳跃）。"""
        self.reached_frame = max(int(reached_frame), self.last_frame)
        return self

    def archives(self):
        """每席一份遗迹档案（纯数据）。`end` 是「这一段落幕的那一帧」（排他），
        故末位在位者坐到 `end - 1`。"""
        last = int(self.reached_frame)
        total = last + 1
        out = []
        for i in range(self.n):
            spans = self.spans[i]
            born = int(spans[0]["start"]) if spans else None
            seated_at_end = bool(spans) and spans[-1]["end"] is None
            died = None if (seated_at_end or not spans) else int(spans[-1]["end"])
            tenured = sum(((int(sp["end"]) if sp["end"] is not None else total)
                           - int(sp["start"])) for sp in spans)
            carried = sorted({int(sp["serial"]) for sp in spans})
            # 空置次数：段与段之间的空档，外加末段之后若还剩时间的那一段空档。
            vacant_runs = 0
            prev_end = None
            for sp in spans:
                if prev_end is not None and int(sp["start"]) > prev_end:
                    vacant_runs += 1
                prev_end = int(sp["end"]) if sp["end"] is not None else total
            if not spans:
                vacant_runs = 1                       # 从未启用 = 一直空着
            elif prev_end is not None and prev_end < total:
                vacant_runs += 1
            out.append({
                "locus_id": self.ids[i],
                "born": born,
                "died": died,
                "seated_at_end": seated_at_end,
                "tenured": int(tenured),
                "vacant_frames": int(total - tenured),
                "vacant_runs": int(vacant_runs),
                "changes": int(max(0, len(spans) - 1)),
                "carried": carried,
                "peak_load": round(float(self.peak_load[i]), 4),
                "peak_load_frame": self.peak_frame[i],
            })
        return out


def marks_of(arch, reach, churn_min=8, endure_frac=0.5):
    """一份遗迹档案 → 标记列表。判据都是客观事实 + 两个可调阈值：

    · `never`      从未有人承此位；
    · `vacant_end` 曾有人坐，但走到最后一帧时已空；
    · `churn`      易主次数 ≥ `churn_min`（默认 8）；
    · `enduring`   在位帧数 ≥ 全程 × `endure_frac`（默认 0.5）。
    """
    if arch["born"] is None:
        return ["never"]
    tags = []
    if not arch["seated_at_end"]:
        tags.append("vacant_end")
    if arch["changes"] >= int(churn_min):
        tags.append("churn")
    if int(reach) > 0 and arch["tenured"] >= float(endure_frac) * (int(reach) + 1):
        tags.append("enduring")
    return tags


def survey(ctx, data, seed=None, frames=None):
    """跑一次并返回 (survey, traj)。survey 已 finalize 到 `traj.reached_frame`。"""
    sv = RuinSurvey([l.id for l in ctx.loci])
    traj = run(ctx, data, seed=seed, max_frames=frames,
               namer=Namer(ctx, data.anchors), watch=sv)
    sv.observe_final(traj).finalize(traj.reached_frame)
    return sv, traj


def _vacant_after(archives) -> int:
    """「启用之后」的空置帧：扣掉尚未启用的那段 —— 遗迹出生前的空座不算它的空置。"""
    return sum((a["vacant_frames"] - a["born"]) if a["born"] is not None else 0
               for a in archives)


def _totals(archives, traj):
    opened = [a for a in archives if a["born"] is not None]
    return {
        "seats": len(archives),
        "opened": len(opened),
        "seated_end": sum(1 for a in opened if a["seated_at_end"]),
        "vacant_end": sum(1 for a in opened if not a["seated_at_end"]),
        "never": sum(1 for a in archives if a["born"] is None),
        "tenured": sum(a["tenured"] for a in archives),
        "changes": sum(a["changes"] for a in archives),
        "vacant_runs": sum(a["vacant_runs"] for a in archives),
        "vacant_frames": sum(a["vacant_frames"] for a in archives),
        "vacant_after": _vacant_after(archives),
        "carried": sum(len(a["carried"]) for a in archives),
        "personas": len(getattr(traj, "personas", []) or []),
    }


def build_report(ctx, data, traj, archives, churn_min=8, endure_frac=0.5):
    """遗迹档案 + 涌现 + 裁决 → 三段式考古报告（纯文本）。只读、可复现。"""
    R = renderer_for(ctx, traj)
    namer = traj.namer
    frame = int(traj.reached_frame)
    reach = frame + 1

    def seat_of(a):
        return R.seat(namer, frame, a["locus_id"])

    marks = {a["locus_id"]: marks_of(a, frame, churn_min, endure_frac)
             for a in archives}
    t = _totals(archives, traj)
    # max 取【首个】最大者 ⇒ 并列时按位次先后，确定可复现（不用哈希做并列键）。
    long = max(archives, key=lambda a: a["tenured"])
    churny = max(archives, key=lambda a: a["changes"])
    per_seat = Counter()
    for p in getattr(traj, "personas", []) or []:
        if p.locus_order is not None:
            per_seat[ctx.loci[p.locus_order].id] += 1

    out = [BAR]
    out.append("  δ-me13「翁法罗斯」遗迹勘测 · 考古报告")
    out.append(BAR)
    out.append(f"  预设        {data.preset.get('name')}")
    out.append(f"  世界种子    {ctx.seed}")
    now = R.locale(frame)
    out.append(f"  走到帧      {fmt(frame)}" + (f" → {now}" if now else ""))
    out.append("")
    out.append("【一】遗址总览")
    out.append(f"  遗址        {t['seats']} 处 · 启用 {t['opened']} · 终局仍有人守 "
               f"{t['seated_end']} · 归于空寂 {t['vacant_end']} · 从未启用 {t['never']}")
    out.append(f"  累计       在位 {fmt(t['tenured'])} 帧"
               f"（十二席全程 {t['tenured'] / max(1, t['seats'] * reach):.0%}）"
               f" · 易主 {fmt(t['changes'])} 次")
    out.append(f"  空置       启用后 {fmt(t['vacant_runs'])} 次"
               f"（共 {fmt(t['vacant_after'])} 帧）"
               f" · 承位个体 {fmt(t['carried'])} 位（涌现登记 {t['personas']} 位）")
    out.append(f"  之最       最久「{seat_of(long)}」{fmt(long['tenured'])} 帧"
               f" · 最繁「{seat_of(churny)}」易主 {fmt(churny['changes'])} 次")
    out.append("")
    out.append("【二】逐处遗迹")
    for i, a in enumerate(archives):
        city = R.city(a["locus_id"]) or "—"
        out.append(f"  {i + 1:>2}. {seat_of(a)} · {city} · {R.region(a['locus_id'])}")
        if a["born"] is None:
            out.append("      从未有人承此位 —— 无始无终，只有空座")
            continue
        if a["seated_at_end"]:
            end_txt = "仍在位"
        else:
            last_seated = max(0, a["died"] - 1)
            end_txt = f"终焉 帧{fmt(last_seated)}{_when(R, last_seated)}"
        out.append(f"      始建 帧{fmt(a['born'])}{_when(R, a['born'])} → {end_txt}")
        out.append(f"      在位 {fmt(a['tenured'])} 帧"
                   f"（{a['tenured'] / max(1, reach):.0%}）"
                   f" · 易主 {fmt(a['changes'])} 次 · 空置 {fmt(a['vacant_runs'])} 次"
                   f" · 承位 {len(a['carried'])} 位")
        tags = "、".join(MARK_LABELS.get(m, m) for m in marks[a["locus_id"]]) or "—"
        peak = ("—" if a["peak_load_frame"] is None
                else f"{a['peak_load']:.3f}（帧{fmt(a['peak_load_frame'])}）")
        out.append(f"      峰值承载 {peak} · 涌现角色 {per_seat.get(a['locus_id'], 0)} 位"
                   f" · 标记 {tags}")
    out.append("")
    out.append("【三】终局结论")
    cn = R.verdict_label(traj.verdict)
    when = (f"，判定于第 {fmt(traj.verdict_frame)} 帧"
            if traj.verdict_frame is not None else "")
    out.append(f"  裁决        {cn}（{traj.verdict}）  {R.stop_label(traj.stop_reason)}{when}")
    out.append(f"  {traj.conclusion['template']}   [{traj.conclusion['id']}]")
    out.append(f"  遗迹        {t['seats']} 处遗址中，{t['seated_end']} 处仍有人守、"
               f"{t['vacant_end']} 处归于空寂、{t['never']} 处从未启用；"
               f"最久的是「{seat_of(long)}」（{fmt(long['tenured'])} 帧），"
               f"易主最多的是「{seat_of(churny)}」（{fmt(churny['changes'])} 次）。")
    framing = (getattr(ctx, "conclusions", None) or {}).get("_framing")
    if framing:
        out.append(f"  议题框架    {framing}")
    out.append(BAR)
    return "\n".join(out)


def as_json(ctx, data, traj, archives, marks):
    """机器可读的遗迹勘测结果（供并排比对 / 单测消费）。"""
    R = renderer_for(ctx, traj)
    frame = int(traj.reached_frame)
    rows = []
    for a in archives:
        row = dict(a)
        row["seat"] = R.seat(traj.namer, frame, a["locus_id"])
        row["region"] = R.region(a["locus_id"])
        row["city"] = R.city(a["locus_id"])
        row["marks"] = list(marks.get(a["locus_id"], []))
        rows.append(row)
    return {
        "preset": data.preset.get("name"),
        "seed": int(ctx.seed),
        "reached_frame": frame,
        "verdict": traj.verdict,
        "conclusion": traj.conclusion["id"],
        "stop_reason": traj.stop_reason,
        "totals": _totals(archives, traj),
        "ruins": rows,
    }


def main():
    ap = argparse.ArgumentParser(description="遗迹勘测 + 考古报告（只读后处理）")
    ap.add_argument("--preset", default="plot")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--frames", type=int, default=None)
    ap.add_argument("--fast", nargs="?", type=int, const=100, default=0,
                    metavar="K", help="测试提速：时间刻度按 K 压缩（只用于冒烟）")
    ap.add_argument("--churn-min", type=int, default=8,
                    help="易主次数 ≥ 此值即打「频繁易主」标记（默认 8）")
    ap.add_argument("--endure-frac", type=float, default=0.5,
                    help="在位帧数 ≥ 全程 × 此比例即打「长驻」标记（默认 0.5）")
    ap.add_argument("--json", action="store_true", help="输出机器可读的遗迹档案")
    args = ap.parse_args()

    ctx, data, _root = load(preset=args.preset, fast=args.fast)
    sv, traj = survey(ctx, data, seed=args.seed, frames=args.frames)
    archives = sv.archives()
    marks = {a["locus_id"]: marks_of(a, traj.reached_frame,
                                     args.churn_min, args.endure_frac)
             for a in archives}
    if args.json:
        blob = as_json(ctx, data, traj, archives, marks)
        print(json.dumps(blob, ensure_ascii=False, indent=1))
        return 0
    print(build_report(ctx, data, traj, archives, args.churn_min, args.endure_frac))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())