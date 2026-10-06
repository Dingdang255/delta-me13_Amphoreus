#!/usr/bin/env python3
"""参数敏感性热力图 —— 建议表 #8：把「结论有多少是参数挑出来的」量出来。

`tests/test_sensitivity.py` 守的是【单点】敏感度（换个 τ，结论就改判 ⇒ 不是查表）。
本工具补的是【扫描产物】：跨 参数 × 种子 跑一整片矩阵，看裁决 / 帧号各自落在哪里 ——
「拟合风险」由此可量化：**参数挪一点点结论就翻面**的世界是脆的，稳如磐石的是壮的。

    # 扫一个参数（5 个取值 × 8 个种子）
    python tools/sensitivity.py --param tau_falsify=0.5,0.75,1.0,1.25,1.5

    # 扫多个参数（各自一张矩阵），并导出热力页
    python tools/sensitivity.py --param mutation=0.005,0.01,0.02 \
        --param tau_falsify=0.5,1.0,1.5 --seeds 0:8 --frames 2000 \
        --html dashboard/敏感性热力图.html --out sensitivity.json

**只读**：参数只改内存里的 `ctx.params` 副本，不写回 `config/`；每个格子都是一次正常的
`run()`，不改引擎、不落盘。同一组输入跑两遍，矩阵逐格一致。

**参数白名单**：只认 `engine.operators.STAGE_TUNABLE` 里那些「运行时真会读」的数值旋钮。
写一个没人读的键（如 `drift`）会当场报错 —— 否则整张热力图会是一张「什么都没变的图」，
比不扫更危险。结构参数（`dim` / `pool_capacity`）与循环控制旋钮（`frames` / `attempt_*`）
不在表内：前者中途改不了，后者改了不作用于演算。

**截断**：撞上 `--iter-cap` 的世界没跑完，其裁决是兜底给的、不算数 —— 格子上标 `~`
并排在最末，不参与帧号统计。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# 并行时把 BLAS 线程钉死为单线程（与 tools/seed_probe.py 同一个理由）：
# N 个进程 × BLAS 线程会互相颠簸，实测能把每个世界拖慢好几倍。必须在 import numpy 之前。
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_v, "1")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from engine.core import run                                # noqa: E402
from engine.loader import Config, DataSet                   # noqa: E402
from engine.render import Renderer                          # noqa: E402

# 公共实现（分隔线 / 配色 / HTML 转义 / 数值解析 / 种子序列）统一在 `tools/_harness.py`。
from _harness import BAR, PALETTE as _PALETTE, esc as _esc, rules  # noqa: E402
from _harness import fmt as _fmt, num as _num, resolve_seeds as _resolve_seeds_common  # noqa: E402

#: 热力配色：按裁决【首次出现】的顺序分配，故同一份扫描总是同一套颜色（色表见
#: `_harness.PALETTE`，与 `engine/viz.py` 的时间线打点同一路数）。
_TENTATIVE = "#6b7280"      # 截断 / 未裁决：灰


# ------------------------------------------------------------------ 扫描
def tunable_names():
    """可扫描的参数名（运行时真会读的数值旋钮）。"""
    from engine.operators import STAGE_TUNABLE
    return tuple(STAGE_TUNABLE)


def check_param(name: str):
    """参数名必须真被读到 —— 写个没人读的键，整张热力图就是一张白图。"""
    names = tunable_names()
    if name not in names:
        raise ValueError(
            f"{name!r} 不是可扫描的参数（运行时无人读它，扫出来的图必定全同）。"
            f"可选：{'、'.join(names)}")


def run_cell(job):
    """跑一格：固定预设 / 种子 / 帧预算，只把 `param` 改成 `value`。只读、不落盘。"""
    preset, seed, param, value, frames, iter_cap = job
    check_param(param)
    data = DataSet(ROOT, preset=preset)
    ctx = Config(ROOT, lex_overlay=data.preset.get("lexicon"))
    ctx.params[param] = value                    # 只在内存里改，config/ 一个字不动
    traj = run(ctx, data, seed=int(seed), max_frames=frames, iter_cap=iter_cap,
               rules=rules())
    verdict = traj.verdict
    frame = traj.verdict_frame if traj.verdict_frame is not None else traj.reached_frame
    return {
        "seed": int(seed),
        "param": str(param),
        "value": value,
        "verdict": verdict,
        "label": (Renderer(ctx).verdict_label(verdict) if verdict else None),
        "frame": int(frame),
        "verdict_frame": (None if traj.verdict_frame is None else int(traj.verdict_frame)),
        "reached_frame": int(traj.reached_frame),
        "stop_reason": traj.stop_reason,
        "truncated": bool(traj.truncated),
        "promotions": int(traj.final.promotions),
        "personas": len(traj.personas),
    }


def scan(preset, seeds, params, frames=None, iter_cap=None, jobs=1):
    """跑一整片矩阵。`params` 是 `[(名字, [取值…]), …]`。

    返回的格子顺序是【参数 → 取值 → 种子】—— 与报告、热力图的行列口径一致。
    `jobs=1` 走串行（单测用，不必起进程池）；>1 才起 `ProcessPoolExecutor`。
    """
    todo = [(preset, s, name, v, frames, iter_cap)
            for name, values in params for v in values for s in seeds]
    if jobs and int(jobs) > 1:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=int(jobs)) as ex:
            return list(ex.map(run_cell, todo))
    return [run_cell(j) for j in todo]


# ------------------------------------------------------------------ 汇总
def rows_of(cells, param, seeds):
    """一张矩阵：每个取值一行，含逐种子的格子 + 一行统计。"""
    out = []
    for value in _values_of(cells, param):
        row = [c for c in cells if c["param"] == param and c["value"] == value]
        by_seed = {c["seed"]: c for c in row}
        ordered = [by_seed.get(s) for s in seeds]
        solid = [c for c in ordered if c and not c["truncated"] and c["verdict"]]
        frames = sorted(c["frame"] for c in solid)
        counts = {}
        for c in solid:
            counts[c["verdict"]] = counts.get(c["verdict"], 0) + 1
        out.append({
            "param": param,
            "value": value,
            "cells": ordered,
            "counts": counts,
            "stable": len(counts) <= 1 and len(solid) == len(ordered),
            "solid": len(solid),
            "frames": ({"min": frames[0], "median": frames[len(frames) // 2],
                        "max": frames[-1]} if frames else None),
        })
    return out


def _values_of(cells, param):
    seen = []
    for c in cells:
        if c["param"] == param and c["value"] not in seen:
            seen.append(c["value"])
    return seen


def _color_map(cells):
    """裁决 → 颜色：按首次出现顺序分配调色板（确定、可复现）。"""
    out = {}
    for c in cells:
        v = c["verdict"]
        if v is None or c["truncated"]:
            continue
        if v not in out:
            out[v] = _PALETTE[len(out) % len(_PALETTE)]
    return out


def _width(txt) -> int:
    """显示宽度：中日韩字符按两格算（`str.rjust` 只数码位，会把列对齐弄歪）。"""
    return sum(2 if ord(ch) > 0x2E80 else 1 for ch in str(txt))


def _rjust(txt, w) -> str:
    return " " * max(0, w - _width(txt)) + str(txt)


def parse_params(specs):
    """`["tau_falsify=0.5,1.0", …]` → `[("tau_falsify", [0.5, 1.0]), …]`。"""
    out = []
    for spec in specs or ():
        if "=" not in spec:
            raise ValueError(f"参数写法应为 名字=值1,值2…，收到 {spec!r}")
        name, raw = spec.split("=", 1)
        name = name.strip()
        vals = [_num(x) for x in raw.split(",") if x.strip()]
        if not vals:
            raise ValueError(f"参数 {name!r} 没有给取值")
        check_param(name)
        out.append((name, vals))
    return out


def resolve_seeds(txt):
    """种子序列：`A:B`（起:个数）或 `a,b,c`（默认 `0:8`）。口径见 `_harness.resolve_seeds`。"""
    return _resolve_seeds_common(txt, "0:8")


# ------------------------------------------------------------------ 渲染
def render_text(cells, params, seeds, meta, color=False):
    """终端热力图：取值 × 种子的裁决矩阵 + 帧号矩阵 + 统计行。"""
    cmap = _color_map(cells)
    out = [BAR, "  δ-me13「翁法罗斯」参数敏感性热力图", BAR]
    out.append(f"  预设 {meta['preset']}　帧预算 {_fmt(meta['frames'])}"
               f"　种子 {seeds[0]}…{seeds[-1]}（{len(seeds)} 个）")
    if meta.get("iter_cap"):
        out.append(f"  迭代上限 {_fmt(meta['iter_cap'])}（触顶的世界标 ~ ，其裁决不计）")
    out.append(f"  参数 {len(params)} 个 · 世界 {len(cells)} 个")
    out.append("")

    for name, _values in params:
        out.append(f"【{name}】")
        out.append("  " + _rjust("取值", 10) + "  "
                   + "".join(_rjust(f"种子 {s}", 10) for s in seeds))
        for row in rows_of(cells, name, seeds):
            labels = "".join(_pad(c, cmap, color) for c in row["cells"])
            frames = "".join(_rjust(_fmt(c["frame"]) if c else "—", 10)
                             for c in row["cells"])
            out.append("  " + _rjust(row["value"], 10) + "  " + labels)
            out.append("  " + _rjust("帧号", 10) + "  " + frames)
        out.append("")
        out.append("  统计（跨种子；帧号取【跑完的】那些世界）")
        for row in rows_of(cells, name, seeds):
            dist = "、".join(f"{_verdict_label(cells, v)}×{n}"
                             for v, n in sorted(row["counts"].items()))
            fr = row["frames"]
            span = (f"{_fmt(fr['min'])} / {_fmt(fr['median'])} / {_fmt(fr['max'])}"
                    if fr else "—")
            miss = (f"（{len(row['cells']) - row['solid']} 个未跑完）"
                    if row["solid"] < len(row["cells"]) else "")
            out.append("  " + _rjust(row["value"], 10) + f"  {dist or '（无）'}"
                       f"{miss}　帧号 最小/中位/最大 {span}")
        verdicts = sorted({c["verdict"] for c in cells
                           if c["param"] == name and c["verdict"]
                           and not c["truncated"]})
        if len(verdicts) > 1:
            out.append(f"  ⚠ 该参数在本区间内【改判】："
                       f"{' / '.join(_verdict_label(cells, v) for v in verdicts)}"
                       f" —— 结论对此参数敏感，属拟合风险点")
        else:
            out.append("  ✓ 该参数在本区间内【未改判】"
                       "（仍要看帧号是否漂移 —— 结论稳不等于轨迹稳）")
        out.append("")

    out.append("  图例　" + "　".join(
        f"{_verdict_label(cells, v)}" for v in cmap) + "　~ 未跑完")
    out.append(BAR)
    return "\n".join(out)


def _label(cell):
    if cell is None:
        return "—"
    if cell["truncated"] or not cell["verdict"]:
        return "~"
    return cell["label"] or cell["verdict"]


def _verdict_label(cells, verdict):
    for c in cells:
        if c["verdict"] == verdict and c["label"]:
            return c["label"]
    return str(verdict)


def _pad(cell, cmap, color):
    """把一个格子塞进 10 格（中文按两格宽算），并按裁决染色。"""
    txt = _label(cell)
    pad = " " * max(0, 10 - _width(txt))
    if not color:
        return f"{txt}{pad}"
    col = (_TENTATIVE if (cell is None or cell["truncated"] or not cell["verdict"])
           else cmap.get(cell["verdict"], _TENTATIVE))
    return f"{_ansi(txt, col)}{pad}"


def _ansi(txt, hexcol):
    r, g, b = _rgb(hexcol)
    return f"\x1b[38;2;{r};{g};{b}m{txt}\x1b[0m"


def _rgb(hexcol):
    h = hexcol.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _readable_on(hexcol):
    r, g, b = _rgb(hexcol)
    lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "#111111" if lum > 0.6 else "#f5f5f5"


def render_html(cells, params, seeds, meta):
    """自包含热力页（零外链、零 JS）：一张矩阵一张表，格子带悬浮说明。"""
    cmap = _color_map(cells)
    out = ["<!DOCTYPE html>", '<html lang="zh-CN"><head><meta charset="utf-8">',
           "<title>δ-me13 参数敏感性热力图</title>", "<style>",
           "body{margin:0;padding:32px;background:#14161c;color:#e6e8ee;"
           "font:14px/1.6 'Segoe UI',system-ui,sans-serif}",
           "h1{font-size:20px;font-weight:600;margin:0 0 6px}",
           "h2{font-size:15px;font-weight:600;margin:26px 0 8px;color:#aab2c8}",
           ".meta{color:#8b93a8;margin:0 0 4px}",
           "table{border-collapse:separate;border-spacing:4px}",
           "th{font-weight:500;color:#8b93a8;font-size:12px;padding:0 6px}",
           "td{padding:6px 10px;border-radius:6px;text-align:center;"
           "min-width:64px;font-size:12px}",
           "td small{opacity:.75;display:block;font-size:11px}",
           ".v{color:#aab2c8;text-align:right;padding-right:10px}",
           ".legend{margin-top:22px;display:flex;gap:14px;flex-wrap:wrap;"
           "color:#aab2c8;font-size:12px}",
           ".legend i{display:inline-block;width:10px;height:10px;border-radius:3px;"
           "margin-right:6px;vertical-align:middle}",
           "</style></head><body>"]
    out.append("<h1>δ-me13「翁法罗斯」参数敏感性热力图</h1>")
    out.append(f'<p class="meta">预设 {_esc(meta["preset"])} · 帧预算 '
               f'{_fmt(meta["frames"])} · 种子 {seeds[0]}…{seeds[-1]}'
               f'（{len(seeds)} 个）· 世界 {len(cells)} 个</p>')
    if meta.get("iter_cap"):
        out.append(f'<p class="meta">迭代上限 {_fmt(meta["iter_cap"])}'
                   ' —— 标 ~ 的世界未跑完，其裁决不计</p>')

    for name, _values in params:
        out.append(f"<h2>{_esc(name)}</h2>")
        out.append("<table><tr><th></th>"
                   + "".join(f"<th>种子 {s}</th>" for s in seeds) + "</tr>")
        for row in rows_of(cells, name, seeds):
            out.append(f'<tr><td class="v">{_esc(str(row["value"]))}</td>')
            for c in row["cells"]:
                if c is None:
                    out.append('<td style="background:#2a2e3a">—</td>')
                    continue
                tent = c["truncated"] or not c["verdict"]
                col = _TENTATIVE if tent else cmap.get(c["verdict"], _TENTATIVE)
                txt = "~" if tent else _esc(c["label"] or c["verdict"])
                tip = (f'种子 {c["seed"]} · {_esc(str(c["value"]))} · {txt} · '
                       f'帧 {_fmt(c["frame"])} · {_esc(str(c["verdict"]))}'
                       + ("（未跑完）" if tent else ""))
                out.append(f'<td style="background:{col};'
                           f'color:{_readable_on(col)}" title="{tip}">'
                           f'{txt}<small>{_fmt(c["frame"])}</small></td>')
            out.append("</tr>")
        out.append("</table>")
        stable = all(r["stable"] for r in rows_of(cells, name, seeds))
        note = ("本区间内未改判" if stable else
                "⚠ 本区间内出现改判 —— 结论对此参数敏感")
        out.append(f'<p class="meta">{note}</p>')

    out.append('<div class="legend">')
    for v, col in cmap.items():
        out.append(f'<span><i style="background:{col}"></i>'
                   f'{_esc(_verdict_label(cells, v))}</span>')
    out.append(f'<span><i style="background:{_TENTATIVE}"></i>未跑完</span>')
    out.append("</div></body></html>")
    return "\n".join(out)


# ------------------------------------------------------------------ 主流程
def main():
    ap = argparse.ArgumentParser(
        description="参数敏感性热力图（只读：只改内存里的 params 副本）",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--param", action="append", required=True,
                    metavar="名字=值1,值2…",
                    help="要扫的参数（可重复）；参数名须在 STAGE_TUNABLE 白名单内")
    ap.add_argument("--preset", default="emergent")
    ap.add_argument("--seeds", default="0:8", help="A:B（起:个数）或 a,b,c")
    ap.add_argument("--frames", type=int, default=2000)
    ap.add_argument("--iter-cap", type=int, default=60000,
                    help="迭代次数上限（安全阀）；触顶的世界标 ~ 且不计入统计")
    ap.add_argument("-j", "--jobs", type=int, default=None,
                    help="并行进程数（默认 min(8, 核数)）")
    ap.add_argument("--out", default=None, help="把完整结果写成 JSON")
    ap.add_argument("--html", default=None, help="写一份自包含的热力页")
    ap.add_argument("--no-color", action="store_true", help="终端输出不上色")
    ap.add_argument("--list-params", action="store_true", help="列出可扫描的参数后退出")
    args = ap.parse_args()

    if args.list_params:
        print("可扫描的参数（engine.operators.STAGE_TUNABLE —— 运行时真会读的旋钮）：")
        for n in tunable_names():
            print("  " + n)
        return 0

    try:
        params = parse_params(args.param)
    except ValueError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 2
    seeds = resolve_seeds(args.seeds)
    jobs = args.jobs if args.jobs is not None else min(8, os.cpu_count() or 1)

    meta = {"preset": args.preset, "frames": args.frames,
            "iter_cap": args.iter_cap, "seeds": seeds}
    total = sum(len(v) for _n, v in params) * len(seeds)
    print(f"扫描 {total} 个世界（{len(params)} 参数 × 取值 × {len(seeds)} 种子）"
          f"　帧预算 {_fmt(args.frames)}　并行 {jobs}\n")

    cells = scan(args.preset, seeds, params, frames=args.frames,
                 iter_cap=args.iter_cap, jobs=jobs)

    color = (not args.no_color) and sys.stdout.isatty()
    print(render_text(cells, params, seeds, meta, color=color))

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({"meta": meta,
                       "params": [{"name": n, "values": v} for n, v in params],
                       "colors": _color_map(cells),
                       "cells": cells}, f, ensure_ascii=False, indent=1)
        print(f"  完整结果已写入 {args.out}")
    if args.html:
        os.makedirs(os.path.dirname(os.path.abspath(args.html)), exist_ok=True)
        with open(args.html, "w", encoding="utf-8") as f:
            f.write(render_html(cells, params, seeds, meta))
        print(f"  热力页已写入 {args.html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())