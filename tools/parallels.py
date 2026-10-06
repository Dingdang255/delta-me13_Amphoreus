#!/usr/bin/env python3
"""平行世界对照 —— 建议表 #4：把几个世界并排摆开，看同一套机制在不同世界里跑成了什么。

单跑一个世界的看板回答不了「换个种子会怎样」；`tools/seed_probe.py` 能批量跑、能出表，
但那是【逐种子的数表】，看不出形状。本工具补的正是这块：把 N 个世界摆成一张对照页 ——

  · **熵曲线**：N 条熵 / 黑潮强度曲线叠在同一张坐标上（横轴帧号，纵轴各自归一）；
  · **遗迹分布**：每世界 × 每席的在位比例矩阵（深浅一眼看出哪个世界的席位更稳）；
  · **涌现时序**：每世界一条时间轴，涌现帧在上面打点。

    python tools/parallels.py --preset plot --seeds 0:4 --frames 3000 --html 平行世界.html
    python tools/parallels.py --world tide:0 --world nullify:0 --world emergent:0 --out 对照.json

**只读**：每个世界都是正常的 `run()`，只多挂了两个只读观测器（采样器 + 遗迹勘测）；
参数不落盘、`config/` 一个字不动。同一组输入跑两遍，对照页逐字节一致。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import (BAR, load, ROOT, PALETTE as _PALETTE,  # noqa: E402
                      esc as _esc, resolve_seeds as _resolve_seeds_common,
                      rules, services)

from engine.core import run                                # noqa: E402
from engine.render import renderer_for                     # noqa: E402
from engine.viz import Sampler                             # noqa: E402

import excavation                                          # noqa: E402

#: 每个世界的配色（按世界序号取；超过就循环）—— 色表见 `_harness.PALETTE`。
_W, _H, _PAD = 900, 220, 34


class _Watches:
    """把多个只读观测器合成一个 `watch`。

    **只在观测器恒返回 True 时可用**（`all()` 会短路，一个 `False` 后面的就收不到帧了）。
    本工具挂的采样器与遗迹勘测都恒返回 True，从不剪枝。
    """

    def __init__(self, *watches):
        self.watches = watches

    def __call__(self, frame, st, traj):
        return all(w(frame, st, traj) for w in self.watches)


def collect(preset, seed, frames=None, fast=0):
    """跑一个世界，返回它的对照数据（曲线 / 遗迹 / 涌现 / 裁决）。只读。"""
    ctx, data, _root = load(preset=preset, fast=fast)
    total = int(frames if frames is not None else ctx.params.get("frames", 20000))
    sampler = Sampler(total)
    survey = excavation.RuinSurvey([l.id for l in ctx.loci])
    traj = run(ctx, data, seed=seed, max_frames=frames,
               watch=_Watches(sampler, survey), rules=rules(), runtime=services())
    survey.observe_final(traj).finalize(traj.reached_frame)
    R = renderer_for(ctx, traj)
    archives = survey.archives()
    return {
        "preset": preset,
        "seed": int(seed),
        "name": f"{preset}:{seed}",
        "verdict": traj.verdict,
        "label": (R.verdict_label(traj.verdict) if traj.verdict else None),
        "frame": int(traj.verdict_frame if traj.verdict_frame is not None
                     else traj.reached_frame),
        "reached_frame": int(traj.reached_frame),
        "iterations": int(traj.iterations),
        "skipped_frames": int(traj.skipped_frames),
        "truncated": bool(traj.truncated),
        "stop_reason": traj.stop_reason,
        "entropy": round(float(traj.final.entropy), 6),
        "noise": round(float(traj.final.noise), 6),
        "promotions": int(traj.final.promotions),
        "personas": len(traj.personas),
        "digest": traj.final.digest(),
        "curve": [[int(f), float(e), float(nz), int(pop)]
                  for f, e, nz, pop, _pr, _fl, _ow in sampler.points],
        "ruins": archives,
        "emergence": sorted(int(p.surfaced_frame) for p in traj.personas),
        "seats": [R.seat(traj.namer, traj.reached_frame, l.id) for l in ctx.loci],
        "locus_ids": [l.id for l in ctx.loci],
    }


def _axis_max(worlds, key, fallback=1.0):
    hi = 0.0
    for w in worlds:
        for row in w["curve"]:
            hi = max(hi, float(row[key]))
    return hi if hi > 0 else fallback


def _polyline(series, frames_max, val_max):
    """把 (帧, 值) 序列折成 SVG 折线点串。x 归一到 [pad, W-pad]，y 反过来。"""
    if not series or frames_max <= 0:
        return ""
    span = max(1.0, float(val_max))
    pts = []
    for frame, val in series:
        x = _PAD + (_W - 2 * _PAD) * (frame / frames_max)
        y = _H - _PAD - (_H - 2 * _PAD) * (max(0.0, val) / span)
        pts.append(f"{x:.1f},{y:.1f}")
    return " ".join(pts)


def _curve_svg(worlds, key, title):
    frames_max = max((w["reached_frame"] for w in worlds), default=1) or 1
    val_max = _axis_max(worlds, key)
    out = [f'<svg viewBox="0 0 {_W} {_H}" class="chart" '
           f'role="img" aria-label="{_esc(title)}">',
           f'<rect x="{_PAD}" y="{_PAD}" width="{_W - 2 * _PAD}" '
           f'height="{_H - 2 * _PAD}" fill="#1b1e26" rx="4"/>',
           f'<text x="{_PAD}" y="20" class="ct">{_esc(title)}</text>']
    for i, w in enumerate(worlds):
        pts = _polyline([(r[0], r[key]) for r in w["curve"]],
                        frames_max, val_max)
        if not pts:
            continue
        col = _PALETTE[i % len(_PALETTE)]
        out.append(f'<polyline points="{pts}" fill="none" stroke="{col}" '
                   f'stroke-width="1.6" opacity="0.9"/>')
        out.append(f'<circle cx="{_PAD}" cy="{26 + 14 * i}" r="4" fill="{col}"/>')
        out.append(f'<text x="{_PAD + 12}" y="{30 + 14 * i}" class="lg">'
                   f'{_esc(w["name"])}</text>')
    out.append(f'<text x="{_PAD}" y="{_H - 10}" class="ax">帧 0</text>')
    out.append(f'<text x="{_W - _PAD}" y="{_H - 10}" class="ax" '
               f'text-anchor="end">帧 {frames_max:,}</text>')
    out.append(f'<text x="{_PAD - 6}" y="{_PAD + 4}" class="ax" '
               f'text-anchor="end">峰值 {val_max:.3f}</text>')
    out.append("</svg>")
    return "".join(out)


def _ruin_table(worlds):
    """遗迹分布：行 = 世界，列 = 席位，格子深浅 = 在位比例。"""
    out = ['<table class="ruins"><tr><th class="v">世界</th>']
    for name in worlds[0]["seats"] if worlds else ():
        out.append(f"<th>{_esc(name)}</th>")
    out.append("</tr>")
    for w in worlds:
        out.append(f'<tr><td class="v">{_esc(w["name"])}</td>')
        reach = w["reached_frame"] + 1
        for a in w["ruins"]:
            frac = a["tenured"] / max(1, reach)
            alpha = 0.12 + 0.88 * min(1.0, frac)
            tip = (f'{_esc(w["name"])} · {_esc(a["locus_id"])} · 在位 '
                   f'{a["tenured"]:,}/{reach:,} 帧（{frac:.0%}）· 易主 '
                   f'{a["changes"]} 次')
            out.append(f'<td style="background:rgba(127,208,255,{alpha:.2f})" '
                       f'title="{tip}">{frac:.0%}</td>')
        out.append("</tr>")
    out.append("</table>")
    return "".join(out)


def _emergence_strips(worlds):
    """涌现时序：每世界一条时间轴，涌现帧打点。"""
    frames_max = max((w["reached_frame"] for w in worlds), default=1) or 1
    row_h = 26
    height = row_h * len(worlds) + 24
    out = [f'<svg viewBox="0 0 {_W} {height}" class="chart" role="img" '
           f'aria-label="涌现时序">']
    for i, w in enumerate(worlds):
        y = 20 + row_h * i
        col = _PALETTE[i % len(_PALETTE)]
        out.append(f'<line x1="{_PAD}" y1="{y}" x2="{_W - _PAD}" y2="{y}" '
                   f'stroke="#333947" stroke-width="1"/>')
        out.append(f'<text x="{_PAD - 8}" y="{y + 4}" class="ax" '
                   f'text-anchor="end">{_esc(w["name"])}</text>')
        for f in w["emergence"]:
            x = _PAD + (_W - 2 * _PAD) * (f / frames_max)
            out.append(f'<circle cx="{x:.1f}" cy="{y}" r="2.4" fill="{col}" '
                       f'opacity="0.75"/>')
        out.append(f'<text x="{_W - _PAD}" y="{y + 4}" class="ax" '
                   f'text-anchor="end">{len(w["emergence"])} 位</text>')
    out.append(f'<text x="{_PAD}" y="{height - 6}" class="ax">帧 0</text>')
    out.append(f'<text x="{_W - _PAD}" y="{height - 6}" class="ax" '
               f'text-anchor="end">帧 {frames_max:,}</text>')
    out.append("</svg>")
    return "".join(out)


def _summary_table(worlds):
    cols = ("世界", "裁决", "判定帧", "走到帧", "迭代", "复用帧", "换代", "涌现", "熵", "黑潮")
    out = ['<table class="sum"><tr>'
           + "".join(f"<th>{_esc(c)}</th>" for c in cols) + "</tr>"]
    for i, w in enumerate(worlds):
        col = _PALETTE[i % len(_PALETTE)]
        label = (w["label"] or "—") + ("（未跑完）" if w["truncated"] else "")
        out.append(
            f'<tr><td style="color:{col}">{_esc(w["name"])}</td>'
            f'<td>{_esc(label)}</td>'
            f'<td>{w["frame"]:,}</td><td>{w["reached_frame"]:,}</td>'
            f'<td>{w["iterations"]:,}</td><td>{w["skipped_frames"]:,}</td>'
            f'<td>{w["promotions"]:,}</td><td>{w["personas"]:,}</td>'
            f'<td>{w["entropy"]:.4f}</td><td>{w["noise"]:.4f}</td></tr>')
    out.append("</table>")
    return "".join(out)


def render_html(worlds, meta):
    """自包含对照页（零外链、零 JS）。"""
    out = ["<!DOCTYPE html>", '<html lang="zh-CN"><head><meta charset="utf-8">',
           "<title>δ-me13 平行世界对照</title>", "<style>",
           "body{margin:0;padding:32px;background:#14161c;color:#e6e8ee;"
           "font:14px/1.6 'Segoe UI',system-ui,sans-serif}",
           "h1{font-size:20px;font-weight:600;margin:0 0 6px}",
           "h2{font-size:15px;font-weight:600;margin:28px 0 10px;color:#aab2c8}",
           ".meta{color:#8b93a8;margin:0 0 4px}",
           ".chart{width:100%;max-width:960px;display:block;margin:6px 0 4px}",
           ".ct{fill:#aab2c8;font-size:12px}.lg{fill:#c9cfe0;font-size:11px}",
           ".ax{fill:#6f7688;font-size:11px}",
           "table{border-collapse:collapse;margin:6px 0 10px;font-size:12px}",
           "th,td{padding:5px 9px;border-bottom:1px solid #262a34;text-align:right}",
           "th{color:#8b93a8;font-weight:500;text-align:right}",
           "td.v,th.v{text-align:left;color:#c9cfe0}",
           "table.ruins td{min-width:52px;text-align:center;color:#0d1016;"
           "font-size:11px;border:2px solid #14161c;border-radius:4px}",
           "</style></head><body>"]
    out.append("<h1>δ-me13「翁法罗斯」平行世界对照</h1>")
    out.append(f'<p class="meta">{len(worlds)} 个世界 · 帧预算 '
               f'{meta["frames"]:,}'
               + (f' · 测试提速 ×{meta["fast"]}' if meta.get("fast", 0) > 1 else "")
               + "</p>")
    out.append("<h2>对照表</h2>" + _summary_table(worlds))
    out.append("<h2>熵曲线</h2>" + _curve_svg(worlds, 1, "熵（纵轴按本图峰值归一）"))
    out.append("<h2>黑潮强度</h2>" + _curve_svg(worlds, 2, "黑潮强度（同上）"))
    out.append("<h2>遗迹分布</h2><p class=\"meta\">格子 = 该席在全程中有人坐的帧数占比"
               "（色越深越稳）。</p>" + _ruin_table(worlds))
    out.append("<h2>涌现时序</h2><p class=\"meta\">每个点是一个个体第一次涌现的帧。"
               "</p>" + _emergence_strips(worlds))
    out.append("</body></html>")
    return "\n".join(out)


def render_text(worlds, meta):
    out = [BAR, "  δ-me13「翁法罗斯」平行世界对照", BAR]
    out.append(f"  帧预算 {meta['frames']:,}"
               + (f"　测试提速 ×{meta['fast']}" if meta.get("fast", 0) > 1 else ""))
    out.append("")
    out.append(f"  {'世界':<14}{'裁决':<8}{'判定帧':>10}{'走到帧':>10}"
               f"{'迭代':>9}{'换代':>6}{'涌现':>6}{'熵':>9}")
    for w in worlds:
        label = (w["label"] or "—") + ("~" if w["truncated"] else "")
        out.append(f"  {w['name']:<14}{label:<8}{w['frame']:>10,}"
                   f"{w['reached_frame']:>10,}{w['iterations']:>9,}"
                   f"{w['promotions']:>6,}{w['personas']:>6,}{w['entropy']:>9.4f}")
    if worlds:
        out.append("")
        out.append("  遗迹分布（在位帧占比 · 行=世界 · 列=席位）")
        out.append("    " + " " * 14 + "".join(f"{i + 1:>5}" for i in range(len(worlds[0]["seats"]))))
        for w in worlds:
            reach = w["reached_frame"] + 1
            cells = "".join(f"{a['tenured'] / max(1, reach):>5.0%}"
                            for a in w["ruins"])
            out.append(f"    {w['name']:<14}{cells}")
    out.append(BAR)
    return "\n".join(out)


def parse_worlds(specs, preset, seeds):
    """`--world 预设:种子` 优先；没给就用 `--preset` + `--seeds` 生成。"""
    if specs:
        out = []
        for s in specs:
            if ":" in s:
                name, seed = s.split(":", 1)
            else:
                name, seed = s, "0"
            out.append((name.strip(), int(seed)))
        return out
    return [(preset, s) for s in seeds]


def resolve_seeds(txt):
    """种子序列：`A:B`（起:个数）或 `a,b,c`（默认 `0:4`）。口径见 `_harness.resolve_seeds`。"""
    return _resolve_seeds_common(txt, "0:4")


def main():
    ap = argparse.ArgumentParser(description="平行世界对照（只读）")
    ap.add_argument("--world", action="append", default=[], metavar="预设:种子",
                    help="一个世界（可重复）；优先级高于 --preset/--seeds")
    ap.add_argument("--preset", default="emergent")
    ap.add_argument("--seeds", default="0:4", help="A:B（起:个数）或 a,b,c")
    ap.add_argument("--frames", type=int, default=3000)
    ap.add_argument("--fast", nargs="?", type=int, const=100, default=0,
                    metavar="K", help="测试提速：时间刻度按 K 压缩（只用于冒烟）")
    ap.add_argument("--out", default=None, help="把对照数据写成 JSON")
    ap.add_argument("--html", default=None, help="写一份自包含的对照页")
    ap.add_argument("--no-color", action="store_true", help="终端不上色（本工具暂未上色）")
    args = ap.parse_args()

    worlds = parse_worlds(args.world, args.preset, resolve_seeds(args.seeds))
    if not worlds:
        print("✗ 没有世界可对照", file=sys.stderr)
        return 2
    meta = {"frames": args.frames, "fast": args.fast}

    print(f"对照 {len(worlds)} 个世界　帧预算 {args.frames:,}"
          + (f"　提速 ×{args.fast}" if args.fast > 1 else "") + "\n")
    rows = []
    for preset, seed in worlds:
        w = collect(preset, seed, frames=args.frames, fast=args.fast)
        rows.append(w)
        print(f"  ✓ {w['name']:<14}{w['label'] or '—':<8}"
              f"判定@{w['frame']:,}　涌现 {w['personas']:,}　换代 {w['promotions']:,}")

    print()
    print(render_text(rows, meta))

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({"meta": meta, "worlds": rows}, f, ensure_ascii=False, indent=1)
        print(f"  对照数据已写入 {args.out}")
    if args.html:
        os.makedirs(os.path.dirname(os.path.abspath(args.html)), exist_ok=True)
        with open(args.html, "w", encoding="utf-8") as f:
            f.write(render_html(rows, meta))
        print(f"  对照页已写入 {args.html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())