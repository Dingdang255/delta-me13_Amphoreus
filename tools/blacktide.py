#!/usr/bin/env python3
"""黑潮爆发探测 —— 建议表 #5：把「帧级溢出」细化成「区域塌陷 + 周边抬升」。

`engine/features.py` 里的 `black_tide_*` 是【粗判】：它数的是 `OVERFLOW` 违规——
哪一帧席位被压垮了。那是**帧级**的（这一帧满没满），看不见**区域级**的形状：
一整块区域被抽空、压力外溢到别的区域，才是一场「黑潮」。

**区域怎么定**：`config/loci.json` 的 `couplings` 里，正值成簇（本项目是 4 簇 × 3 区）。
区域 = `couplings > 0` 的**连通分量** —— 结构里本来就写着谁和谁同区，不是外部硬塞的。

> ⚠ 一个实测校准出来的口径：**「周边」必须按【簇】读，不能按单区读。**
> 同簇三区在动力学上是同进同退的（实测：单区跌 0.13 时，它的同簇邻区合计跌 0.16），
> 故「单区塌陷而邻区抬升」在结构上恒不成立 —— 那样扫只会得到一张空表。
> 真正成立的形状是**整簇塌陷、簇外抬升**。本工具即按此实现。

判据（四条同时成立才算一次爆发）：

  · **区域塌陷**：某簇的总承载占比在窗口内跌 ≥ `--drop-min`；
  · **内部一致**：簇内**过半**成员各自都在跌 —— 黑潮吞掉的是整块区域，不是被单点拖累；
  · **周边抬升**：簇外总占比升 ≥ `--rise-min`（由守恒与「内部一致」可推出 ≈ 跌幅，
    故它更像一个**读数**：报告里那个「外溢 +x.xxx」就是它）；
  · **世界更集中**：全局熵在窗口内降 ≥ `--entropy-drop`（默认 0，即只要求不升）。

窗口把时间分辨率定死：一段爆发的时长读数不会短于窗口。

    python tools/blacktide.py --preset tide --seed 0 --frames 3000
    python tools/blacktide.py --preset plot --drop-min 0.05 --out 黑潮.json

**只读**：`TideSurvey` 挂在 `run(watch=...)` 上逐帧记录每席承载占比，只写自己的列表、
恒返回 `True`（从不剪枝）。删掉本文件，演算逐帧不变。
"""
from __future__ import annotations

import argparse
import bisect
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import BAR, load                              # noqa: E402

from engine.core import run                                 # noqa: E402
from engine.namer import Namer                              # noqa: E402
from engine.render import renderer_for                      # noqa: E402

#: 基线最远可离窗口多少倍 —— 超出即视为「采样过稀、测不准」，跳过而不是硬算。
_GAP_TOL = 4.0


class TideSurvey:
    """只读黑潮勘测：逐帧记下【每席的承载占比】与全局熵 / 黑潮强度。

    挂在 `run(watch=...)` 上。**只读、恒返回 `True`**，从不剪枝。

    逐帧全留会随长轨道线性涨内存，故带一个抽稀：点数触顶就把已存的隔点丢掉、步长翻倍
    （经典的等距抽稀）—— 形状不变、内存封顶。抽稀只影响时间分辨率；精确的逐帧比对
    仍以 `traj` 为准（本勘测不进指纹、不参与演算）。
    """

    def __init__(self, cap: int = 400_000):
        self.series = []            # (frame, shares, entropy, noise)
        self.cap = max(2, int(cap))
        self.stride = 1
        self._seen = 0

    def __call__(self, frame, st, traj):
        self._seen += 1
        if self._seen % self.stride:
            return True
        loci = getattr(st, "loci", ()) or ()
        loads = [float(getattr(l, "load", 0.0)) for l in loci]
        total = sum(loads)
        shares = tuple((v / total if total > 0.0 else 0.0) for v in loads)
        self.series.append((int(frame), shares,
                            float(getattr(st, "entropy", 0.0)),
                            float(getattr(st, "noise", 0.0))))
        if len(self.series) >= self.cap:
            self.series = self.series[::2]
            self.stride *= 2
        return True


def clusters_of(ctx, thr: float = 0.0):
    """区域 = `couplings > thr` 的连通分量（并查集）。按最小位次排序 ⇒ 结果确定可复现。"""
    n = len(ctx.loci)
    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for i, locus in enumerate(ctx.loci):
        for j, v in enumerate(locus.couplings):
            if j < n and j != i and float(v) > thr:
                parent[find(i)] = find(j)
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return sorted((sorted(g) for g in groups.values()), key=lambda g: g[0])


def _window_miss(survey, clusters, window, drop_min, rise_min, entropy_drop_min):
    """最接近命中、却没过的那个候选 —— 零命中时用它说明「差在哪」。"""
    best = None
    for cand in _candidates(survey, clusters, window):
        if best is None or cand["drop"] > best["drop"]:
            best = cand
    if best is None:
        return None
    best["reasons"] = []
    if best["drop"] < drop_min:
        best["reasons"].append(f"跌幅 {best['drop']:.3f} < {drop_min:g}")
    if not best["coherent"]:
        best["reasons"].append("簇内不足半数在跌")
    if best["rise"] < rise_min:
        best["reasons"].append(f"簇外升幅 {best['rise']:.3f} < {rise_min:g}")
    if best["entropy_drop"] < entropy_drop_min:
        best["reasons"].append(
            f"全局熵降 {best['entropy_drop']:.4f} < {entropy_drop_min:g}")
    return best


def _candidates(survey, clusters, window):
    """滑窗枚举：每个时间点取【跌得最狠】的那个簇，产出一条候选读数。

    **基线必须真的落在窗口内**：永劫回归期沿参考轨道复用，采样帧距可达数千帧，
    `frame - window` 会落到好几个到访帧之前 —— 那样算出来的"跌幅"是跨大段跳越的，
    不可比。这类点一律跳过（用 `sparse_points()` 单独计数、在报告里说明），
    免得把「测不准」当成「没有爆发」。
    """
    series = survey.series
    if len(series) < 2 or not clusters:
        return
    frames = [p[0] for p in series]
    n = len(series[0][1])
    for k, (frame, shares, ent, _nz) in enumerate(series):
        j = bisect.bisect_right(frames, frame - window) - 1
        if j < 0 or j >= k:
            continue
        base = series[j]
        if frame - base[0] > window * _GAP_TOL:
            continue
        best = None
        for g in clusters:
            drop = sum(base[1][t] for t in g) - sum(shares[t] for t in g)
            fell = sum(1 for t in g if base[1][t] - shares[t] > 0.0)
            if best is None or drop > best[0]:
                best = (drop, fell, g)
        drop, fell, g = best
        gset = set(g)
        rise = sum(shares[t] - base[1][t] for t in range(n) if t not in gset)
        yield {"frame": int(frame), "cluster": tuple(g),
               "drop": round(float(drop), 6),
               "fell": int(fell), "size": len(g),
               "coherent": fell > len(g) / 2.0,
               "rise": round(float(rise), 6),
               "entropy_drop": round(float(base[2] - ent), 6)}


def sparse_points(series, window, tol: float = _GAP_TOL) -> int:
    """有多少个采样点因为【基线落在窗口之外】而无法判定（复用期帧距过大）。

    这不是"没有爆发"，而是"这段测不准"。报告要把这个数摆出来。
    """
    frames = [p[0] for p in series]
    n = 0
    for k, (frame, _s, _e, _z) in enumerate(series):
        j = bisect.bisect_right(frames, frame - window) - 1
        if j < 0 or j >= k:
            continue
        if frame - frames[j] > window * tol:
            n += 1
    return n


def detect(survey, clusters, window: int = 64, drop_min: float = 0.15,
           rise_min: float = 0.05, entropy_drop_min: float = 0.0):
    """滑窗探测：四条判据同时成立才记一笔。返回逐点命中（未合并）。"""
    hits = []
    for c in _candidates(survey, clusters, window):
        if c["drop"] < drop_min or not c["coherent"]:
            continue
        if c["rise"] < rise_min or c["entropy_drop"] < entropy_drop_min:
            continue
        hits.append(c)
    return hits


def merge(hits, gap: int):
    """把相邻命中的点并成【爆发段】。`gap` 一般取窗口长度：窗口内的点属同一次爆发。"""
    segs = []
    for h in hits:
        if segs and h["frame"] - segs[-1]["end"] <= int(gap) \
                and h["cluster"] == segs[-1]["cluster"]:
            s = segs[-1]
            s["end"] = h["frame"]
            s["hits"] += 1
            if h["drop"] > s["drop"]:
                s["peak_frame"] = h["frame"]
                s["drop"] = h["drop"]
                s["rise"] = h["rise"]
            s["entropy_drop"] = max(s["entropy_drop"], h["entropy_drop"])
        else:
            segs.append({"start": h["frame"], "end": h["frame"],
                         "peak_frame": h["frame"], "hits": 1,
                         "cluster": h["cluster"],
                         "drop": h["drop"], "rise": h["rise"],
                         "entropy_drop": h["entropy_drop"]})
    for s in segs:
        s["span"] = s["end"] - s["start"]
    return segs


def survey_run(ctx, data, seed=None, frames=None):
    """跑一次并返回 (survey, traj)。"""
    sv = TideSurvey()
    traj = run(ctx, data, seed=seed, max_frames=frames,
               namer=Namer(ctx, data.anchors), watch=sv)
    return sv, traj


def _coarse(traj):
    """粗判口径（`engine/features.py` 那套）的读数，用来对照细化的增益。

    `frames` 取 `violation_counts`（与 features 的 `black_tide_frames` 同源）；
    `first_frame` 取首条【含 OVERFLOW 的违规播报】帧（与 features 的
    `black_tide_first_frame` 同一约定：`VIOLATION_STATE` 只在码集变化时播报）。
    """
    first = None
    for f, kind, payload in traj.records:
        if kind == "VIOLATION_STATE" and "OVERFLOW" in payload.get("codes", ()):
            first = int(f)
            break
    return {"frames": int(traj.violation_counts.get("OVERFLOW", 0)),
            "first_frame": first}


def build_report(ctx, data, traj, segs, clusters, thresholds, miss=None, sparse=0):
    """黑潮报告：口径 · 总览 · 逐段明细。取词全走 Renderer，不写死任何专名。"""
    R = renderer_for(ctx, traj)
    frame = int(traj.reached_frame)

    def seat(i):
        return R.seat(traj.namer, frame, ctx.loci[i].id)

    def zone(g):
        return "／".join(seat(t) for t in g)

    coarse = _coarse(traj)
    out = [BAR, "  δ-me13「翁法罗斯」黑潮爆发探测", BAR]
    out.append(f"  预设        {data.preset.get('name')}　种子 {ctx.seed}")
    now = R.locale(frame)
    out.append(f"  走到帧      {frame:,}" + (f"　→ {now}" if now else ""))
    out.append("")
    out.append("【一】探测口径")
    out.append(f"  窗口        {thresholds['window']:,} 帧（时间分辨率不低于它）")
    out.append(f"  区域        couplings > 0 的连通分量：{len(clusters)} 簇")
    for i, g in enumerate(clusters, 1):
        out.append(f"              簇 {i}（{len(g)} 区）：{zone(g)}")
    out.append(f"  四条件      区域塌陷 Δshare ≥ {thresholds['drop_min']:g}"
               f" · 簇内过半在跌 · 簇外抬升 ≥ {thresholds['rise_min']:g}"
               f" · 全局熵降 ≥ {thresholds['entropy_drop_min']:g}")
    if sparse:
        out.append(f"  采样        {sparse:,} 个采样点的基线落在窗口外"
                   f"（超窗口 {_GAP_TOL:g} 倍 —— 复用期帧距过大）"
                   f"⇒ 已排除在判定之外，那几段是【测不准】，不是【没有】")
    out.append("")
    out.append("【二】爆发总览")
    out.append(f"  细化探测    {len(segs)} 段爆发"
               + (f"，跨 {sum(s['span'] for s in segs):,} 帧" if segs else ""))
    if segs:
        worst = max(segs, key=lambda s: s["drop"])
        out.append(f"  最烈       帧 {worst['peak_frame']:,}　{zone(worst['cluster'])}"
                   f"（Δshare {worst['drop']:.3f} · 外溢 +{worst['rise']:.3f}）")
        out.append(f"  首 / 末    帧 {segs[0]['start']:,} … 帧 {segs[-1]['end']:,}")
    elif miss is not None:
        out.append("  本次世界没有区域级爆发。最接近的一次："
                   f"帧 {miss['frame']:,}　{zone(miss['cluster'])}")
        out.append(f"              跌幅 {miss['drop']:.3f}（簇内 {miss['fell']}/{miss['size']} 在跌）"
                   f" · 外溢 +{miss['rise']:.3f}"
                   f" · 全局熵降 {miss['entropy_drop']:+.4f}")
        out.append(f"              未过判据：{'；'.join(miss['reasons'])}")
    out.append(f"  粗判对照    OVERFLOW 违规 {coarse['frames']:,} 帧"
               + (f"（首帧 {coarse['first_frame']:,}）" if coarse["first_frame"] is not None
                  else "（从未触发）")
               + "　—— 那是帧级的「满了」，本工具看的是区域级的「被抽空」")
    out.append("")
    if segs:
        out.append("【三】逐段明细")
        for i, s in enumerate(segs[:40], 1):
            out.append(f"  {i:>3}. 帧 {s['start']:,}–{s['end']:,}"
                       f"（{s['span']:,} 帧 · 峰值 {s['peak_frame']:,}）"
                       f"　{zone(s['cluster'])}")
            out.append(f"       塌陷 Δshare {s['drop']:.3f}"
                       f" · 外溢 +{s['rise']:.3f}"
                       f" · 全局熵降 {s['entropy_drop']:+.4f}"
                       f" · 命中 {s['hits']:,} 点")
        if len(segs) > 40:
            out.append(f"  …… 共 {len(segs)} 段")
        out.append("")
    out.append(BAR)
    return "\n".join(out)


def as_json(ctx, data, traj, segs, clusters, thresholds, miss=None):
    R = renderer_for(ctx, traj)
    frame = int(traj.reached_frame)

    def seat(i):
        return R.seat(traj.namer, frame, ctx.loci[i].id)

    def row(s):
        out = {k: v for k, v in s.items() if k != "cluster"}
        out["cluster"] = [ctx.loci[t].id for t in s["cluster"]]
        out["seats"] = [seat(t) for t in s["cluster"]]
        return out

    return {
        "preset": data.preset.get("name"),
        "seed": int(ctx.seed),
        "reached_frame": frame,
        "thresholds": thresholds,
        "clusters": [{ctx.loci[i].id: seat(i) for i in g} for g in clusters],
        "bursts": [row(s) for s in segs],
        "closest_miss": row(miss) if miss is not None else None,
        "coarse": _coarse(traj),
    }


def main():
    ap = argparse.ArgumentParser(description="黑潮爆发探测（只读）")
    ap.add_argument("--preset", default="plot")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--frames", type=int, default=None)
    ap.add_argument("--fast", nargs="?", type=int, const=100, default=0,
                    metavar="K", help="测试提速：时间刻度按 K 压缩（只用于冒烟）")
    ap.add_argument("--window", type=int, default=64,
                    help="滑窗长度（帧，默认 64）—— 也是爆发时长读数的时间分辨率")
    ap.add_argument("--drop-min", type=float, default=0.15,
                    help="区域（簇）总占比跌幅阈值（默认 0.15）")
    ap.add_argument("--rise-min", type=float, default=0.05,
                    help="簇外总占比升幅阈值（默认 0.05）")
    ap.add_argument("--entropy-drop", type=float, default=0.0,
                    help="全局熵降幅阈值（默认 0，即只要求不升）")
    ap.add_argument("--out", default=None, help="把探测结果写成 JSON")
    args = ap.parse_args()

    ctx, data, _root = load(preset=args.preset, fast=args.fast)
    sv, traj = survey_run(ctx, data, seed=args.seed, frames=args.frames)
    clusters = clusters_of(ctx)
    thresholds = {"window": args.window, "drop_min": args.drop_min,
                  "rise_min": args.rise_min,
                  "entropy_drop_min": args.entropy_drop}
    hits = detect(sv, clusters, window=args.window, drop_min=args.drop_min,
                  rise_min=args.rise_min, entropy_drop_min=args.entropy_drop)
    segs = merge(hits, gap=args.window)
    sparse = sparse_points(sv.series, args.window)
    miss = (None if segs else
            _window_miss(sv, clusters, args.window, args.drop_min,
                         args.rise_min, args.entropy_drop))

    print(build_report(ctx, data, traj, segs, clusters, thresholds, miss, sparse))
    if args.out:
        blob = as_json(ctx, data, traj, segs, clusters, thresholds, miss)
        blob["sparse_points"] = sparse
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(blob, f, ensure_ascii=False, indent=1)
        print(f"  探测结果已写入 {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())