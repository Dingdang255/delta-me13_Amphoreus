#!/usr/bin/env python3
"""种子探针：填入你想要的剧情要素，扫描种子序列，找出「可能符合」的世界。

引擎本身不认识剧情——它只是在种子给定的世界里逐帧演算。
本工具做的是【事后检索】：把每个种子跑出来的可观测量抽成特征向量，
再按你填的约束筛种子，并把连号的种子归并成一段段「种子序列」。

    # ① 看有哪些可填的要素
    python3 tools/seed_probe.py --features

    # ② 用预设的【时间线】当要素（最常用：找符合剧情时间线的世界）
    python3 tools/seed_probe.py --preset plot --seeds 0:64 --jobs 8

    # ③ 命令行直接填要素（可重复 --want；zsh 下记得给 >= 加引号）
    python3 tools/seed_probe.py --seeds 0:64 \
        --want 'promotion_count>=100' \
        --want 'converged==true' \
        --want 'verdict==proved' \
        --jobs 8

    # ④ 用一份 spec 文件把要素全填进去（模板见 tools/probe_spec.example.json）
    python3 tools/seed_probe.py --spec tools/probe_spec.example.json

要素比较算符： >= <= > < == != in contains between
（in 写 a,b,c：取值属于该集合；contains 写 x：特征串里含 x；between 写 a..b）

预设（--preset）：
    plot       剧情锚定版：并入它的外生事件，并用它的 timeline.json 当要素。
    别的名字   读 presets/<名>/preset.json（可带 events.jsonl 与 timeline.json）。
    none       涌现版：不并事件、不加时间线要素（等价于只跑 --want）。
预设只是【外部绑定与期望】，不含任何演算规则 —— 换预设不会改轨迹。

剪枝（--prune，默认开）：
    时间线节点若带 `by`（最晚帧），到点还没发生就提前毙掉该种子。
    它只让运行提前停下、不写状态，因此停下前走过的每一帧与全程一致；
    被剪掉的种子直接判否，绝不会因此把一个本该命中的种子判成命中。
    此外：被剪枝 / 被 --iter-cap 截断的世界都【没跑完】，一律不算命中 ——
    免得把"没跑出来"当成"跑出来了"。命中只认跑完并给出裁决的世界。

开销：一个满预算世界要逐帧跑到 33,550,560 帧（约 4 万次迭代）。
先用小 --frames（如 60000）做粗筛，再对候选种子跑满预算精筛，最省时间。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from concurrent.futures import ProcessPoolExecutor

# 并行时把 BLAS 线程钉死为单线程：否则 N 个进程 × BLAS 线程会互相颠簸，
# 实测能把每个世界拖慢好几倍。必须在 import numpy 之前设置。
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_v, "1")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from _harness import load, num as _num, resolve_seeds, rules  # noqa: E402

from engine.core import run                                # noqa: E402
from engine.features import DEFAULT_COLS, extract          # noqa: E402
from engine.loader import Config, DataSet                   # noqa: E402
from engine.timeline import check as check_timeline         # noqa: E402
from engine.timeline import compare as _cmp                 # noqa: E402
from engine.timeline import make_watch, nodes_to_constraints  # noqa: E402

# 特征提取已收进 engine/features.py —— 报告与探针共用同一份，避免两处口径漂移。

# ------------------------------------------------------------------ 约束
OPS = {"==": "eq", "=": "eq", "!=": "ne", ">": "gt", ">=": "ge", "<": "lt", "<=": "le"}

# 断言名 → 特征名的别名（少数几个叫法不同 / 不是种子要素的）
_ALIAS = {
    "deadlock_ever": ("deadlock", "eq"),
    "deadlock_length_at_least": ("deadlock_total_frames", "ge"),
}


def spec_from_assertions(data, valid):
    """把当前世界的【剧情断言】直接翻译成要素约束。

    这样「用剧情去挑种子」就不用手抄：剧情怎么写，探针就怎么筛。
    """
    cons, skipped = [], []
    for a in data.assertions:
        name = str(a["assert"])
        exp, where = a["expect"], (a.get("where") or {})
        if name in _ALIAS:
            al = _ALIAS[name]
            if al is None:
                skipped.append(name)
                continue
            cons.append({"feature": al[0], "op": al[1], "value": exp})
            continue
        if name == "persona_with_capability":
            cons.append({"feature": "persona_capabilities", "op": "contains",
                         "value": str(where.get("capability"))})
            continue
        op, base = "eq", name
        for suf, o in (("_at_least", "ge"), ("_at_most", "le")):
            if name.endswith(suf):
                base, op = name[: -len(suf)], o
        cons.append({"feature": base, "op": op, "value": exp})
    return [(c, c["feature"] in valid) for c in cons], skipped


def _scalar(txt):
    txt = txt.strip()
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        return txt


def parse_want(text: str) -> dict:
    m = re.match(r"^\s*(\w+)\s*(>=|<=|==|!=|>|<|=)\s*(.+?)\s*$", text)
    if m:
        feat, op, raw = m.group(1), OPS[m.group(2)], m.group(3)
        return {"feature": feat, "op": op, "value": _scalar(raw)}
    m = re.match(r"^\s*(\w+)\s+between\s+([\d.+-]+)\s*\.\.\s*([\d.+-]+)\s*$", text)
    if m:
        return {"feature": m.group(1), "op": "between",
                "value": [_num(m.group(2)), _num(m.group(3))]}
    m = re.match(r"^\s*(\w+)\s+in\s+(.+?)\s*$", text)
    if m:
        return {"feature": m.group(1), "op": "in",
                "value": [_scalar(x) for x in m.group(2).split(",")]}
    raise ValueError(f"看不懂的要素写法: {text!r}（示例 promotion_count>=100）")


def matches(feat: dict, cons: list) -> bool:
    for c in cons:
        if not _cmp(feat.get(c["feature"]), c["op"], c["value"]):
            return False
    return True


# ------------------------------------------------------------------ 并行执行
def _worker(job):
    seed, frames, constraints, iter_cap, preset, prune = job
    ctx = Config(ROOT)
    data = DataSet(ROOT, preset=preset)
    # 剪枝：只让明显不合的轨道提前停下（不改任何状态），被剪掉的种子直接判否。
    watch = make_watch(data.timeline_nodes) if prune else None
    traj = run(ctx, data, seed=seed, max_frames=frames, trace=True,
               iter_cap=iter_cap, watch=watch, rules=rules())
    f = extract(traj, ctx)
    f["_pruned"] = traj.stop_reason == "PRUNED"
    if f["_pruned"]:
        # 没跑完 ⇒ 没有裁决可言。抹掉暂定值，免得表格里出现一个看着像结论的东西。
        f["verdict"] = None
        f["conclusion"] = None
    # 被剪枝 / 被迭代上限截断的世界都【没有跑完】，其可观测量是暂定的：
    # 一律不算命中，免得把"没跑出来"当成"跑出来了"。
    f["_ok"] = (not f["_pruned"]) and (not f["truncated"]) and matches(f, constraints)
    return f


def _runs(seeds: list) -> list:
    """把连号的种子归并成 [起, 止] 序列段。"""
    out = []
    for s in sorted(seeds):
        if out and s == out[-1][1] + 1:
            out[-1][1] = s
        else:
            out.append([s, s])
    return [(a, b) for a, b in out]


def _fmt(v):
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "是" if v else "否"
    if isinstance(v, float):
        return f"{v:.3f}"
    if isinstance(v, int):
        return f"{v:,}"
    return str(v)


# ------------------------------------------------------------------ 主流程
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", help="JSON 规格文件（把要素全填进去）")
    ap.add_argument("--seeds", help="种子序列：A:B（起:个数）或 a,b,c")
    ap.add_argument("--frames", type=int, default=None, help="每个世界的帧预算")
    ap.add_argument("--iter-cap", type=int, default=None,
                    help="迭代次数上限（安全阀，默认 60000）。防某些种子不陷入"
                         "死循环、真跑满 3350 万帧而挂住。")
    ap.add_argument("--want", action="append", default=[], help="要素约束，可重复")
    ap.add_argument("--preset", default=None,
                    help="预设名（默认 plot）。预设的 timeline.json 会被拿来当要素，"
                         "events.jsonl 会被并进扰动流；写 none 表示涌现版。")
    ap.add_argument("--no-timeline", action="store_true",
                    help="只并预设的外生事件，不用它的时间线当要素")
    ap.add_argument("--no-prune", action="store_true",
                    help="关掉剪枝（默认按时间线的 by 提前毙掉不合的种子）")
    ap.add_argument("--assertions", action="store_true",
                    help="直接把当前世界的断言当作要素")
    ap.add_argument("-j", "--jobs", type=int, default=None,
                    help="并行进程数（默认 min(8, 核数)）。每个种子一个进程；"
                         "进程内把 BLAS 线程钉为 1，免得 N 个进程 × BLAS 线程互相颠簸")
    ap.add_argument("--sort-by", default=None, help="按哪个要素排序")
    ap.add_argument("--desc", action="store_true", help="降序")
    ap.add_argument("--top", type=int, default=25, help="最多列出的行数")
    ap.add_argument("--out", default=None, help="把完整结果写成 JSON")
    ap.add_argument("--features", action="store_true", help="列出所有可填的要素后退出")
    args = ap.parse_args()

    spec = {}
    if args.spec:
        with open(args.spec, "r", encoding="utf-8") as f:
            spec = json.load(f)

    if args.features:
        names = _probe_feature_names()
        print("可填要素（--want <要素><算符><值>）：")
        for n in names:
            print("  " + n)
        return 0

    frames = args.frames or spec.get("frames") or 33550560
    iter_cap = args.iter_cap or spec.get("iter_cap") or 60000
    preset = args.preset if args.preset is not None else (spec.get("preset") or "plot")
    prune = not (args.no_prune or bool(spec.get("no_prune")))
    seeds = resolve_seeds(args.seeds or spec.get("seeds"), "0:16")
    constraints = []
    for w in (spec.get("constraints") or []):
        constraints.append({"feature": w["feature"], "op": w.get("op", "eq"),
                            "value": w.get("value")})
    constraints += [parse_want(w) for w in args.want]
    sort_by = args.sort_by or spec.get("sort_by") or "promotion_count"
    desc = args.desc or bool(spec.get("descending"))
    jobs = args.jobs or spec.get("jobs") or min(8, os.cpu_count() or 1)

    # 预设：并入它的外生事件；并把它 timeline.json 里的期望拿来当要素。
    pdata = DataSet(ROOT, preset=preset)
    n_events = len(pdata.preset.get("events") or [])
    valid = set(_probe_feature_names())

    print(f"预设 {pdata.preset['name']}"
          + (f"（并入 {n_events} 条外生事件）" if n_events else ""))
    if pdata.timeline_nodes and not args.no_timeline:
        tl = nodes_to_constraints(pdata.timeline_nodes)
        constraints = tl + constraints
        by_n = sum(1 for n in pdata.timeline_nodes if n.get("by") is not None)
        print(f"时间线要素 {len(tl)} 条（其中 {by_n} 条带最晚帧，可剪枝"
              + ("，已启用" if prune else "，已关闭") + "）：")
        for n in pdata.timeline_nodes:
            by = f"  ≤{n['by']:,}帧" if n.get("by") is not None else ""
            print(f"    {n.get('id', n['feature']):<22} {n['feature']} "
                  f"{n.get('op', 'eq')} {n.get('value')!r}{by}"
                  + (f"   {n['label']}" if n.get("label") else ""))
        print()

    if args.assertions:
        trans, skipped = spec_from_assertions(pdata, valid)
        constraints += [c for c, ok in trans if ok]
        miss = [c["feature"] for c, ok in trans if not ok]
        print(f"以剧情断言为要素：翻译 {len(constraints)} 条"
              + (f"，跳过 {len(skipped)} 条非种子要素 {skipped}" if skipped else "")
              + (f"，无法映射的要素 {miss}" if miss else ""))
        for c in constraints:
            print(f"    {c['feature']} {c['op']} {c['value']!r}")
        print()

    bad = [c["feature"] for c in constraints if c["feature"] not in valid]
    if bad:
        print(f"✗ 未知要素: {', '.join(bad)}  （用 --features 看清单）", file=sys.stderr)
        return 2

    print(f"扫描 {len(seeds)} 个种子  帧预算 {frames:,}  迭代上限 {iter_cap:,}  "
          f"并行 {jobs}  约束 {len(constraints)} 条\n")

    rows = []
    with ProcessPoolExecutor(max_workers=jobs) as ex:
        jobs_iter = ((s, frames, constraints, iter_cap, preset, prune) for s in seeds)
        for i, f in enumerate(ex.map(_worker, jobs_iter), 1):
            rows.append(f)
            mark = "✓" if f["_ok"] else " "
            cut = "（剪枝）" if f.get("_pruned") else ("（截断）" if f["truncated"] else "")
            print(f"  [{mark}] 种子 {f['seed']:<6} 再创世 {f['promotion_count']:<5} "
                  f"死循环 {f['deadlock_count']}×/{_fmt(f['deadlock_total_frames'])} "
                  f"空缺@{_fmt(f['vacancy_first_frame'])} "
                  f"黑潮@{_fmt(f['black_tide_first_frame'])} "
                  f"角色 {f['persona_count']:<4} 锚定 {'是' if f['converged'] else '否'} "
                  f"首名 {f['first_name_hanzi']}{cut}")

    hit = [r for r in rows if r["_ok"]]
    hit_seeds = sorted(r["seed"] for r in hit)

    print("\n" + "─" * 72)
    if hit:
        seq = _runs(hit_seeds)
        print(f"符合要素的世界：{len(hit)} / {len(rows)}")
        print("命中的种子序列：")
        for a, b in seq:
            print(f"  种子 {a} … {b}" if a != b else f"  种子 {a}")
        print("种子全集：" + ",".join(str(s) for s in hit_seeds))
    else:
        print("没有种子符合全部要素。可放宽某条约束，或扩大 --seeds 范围。")

    if hit and pdata.timeline_nodes and not args.no_timeline:
        one = hit[0]
        print(f"\n命中种子的时间线逐条明细（以种子 {one['seed']} 为例）：")
        for r in check_timeline(pdata.timeline_nodes, one):
            dl = f"  最晚帧 {r.deadline:,}" if r.deadline is not None else ""
            print(f"    [{'PASS' if r.ok else 'FAIL'}] {r.id:<22} "
                  f"got={_fmt(r.got)}{dl}   {r.label}")

    cols = []
    for c in constraints:
        if c["feature"] not in cols:
            cols.append(c["feature"])
    for c in DEFAULT_COLS:
        if c not in cols:
            cols.append(c)
    show = sorted(rows, key=lambda r: (r.get(sort_by) is None, r.get(sort_by)), reverse=desc)
    print("\n特征表（按 " + sort_by + ("↓" if desc else "↑") + " 排序）：")
    print("  " + "  ".join(f"{c[:12]:>12}" for c in cols))
    for r in show[:args.top]:
        mark = "✓" if r["_ok"] else " "
        print(f"{mark} " + "  ".join(f"{_fmt(r.get(c)):>12}" for c in cols))
    if len(show) > args.top:
        print(f"  …… 共 {len(show)} 行")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({"preset": pdata.preset["name"],
                       "frames": frames, "iter_cap": iter_cap, "constraints": constraints,
                       "timeline": pdata.timeline_nodes,
                       "matched_seeds": hit_seeds, "table": rows},
                      f, ensure_ascii=False, indent=2)
        print(f"\n完整结果已写入 {args.out}")

    return 0 if hit else 1


def _probe_feature_names():
    ctx, data, _ = load()
    traj = run(ctx, data, seed=int(data.genesis.get("seed", 0)), max_frames=1,
               trace=True, rules=rules())
    return list(extract(traj, ctx).keys())


if __name__ == "__main__":
    raise SystemExit(main())