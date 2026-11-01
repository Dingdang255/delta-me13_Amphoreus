#!/usr/bin/env python3
"""同 seed 对比两组初始变量，找出轨迹第一处分叉。

    python tools/init_diff.py --a A --b B --frames 3000
    python tools/init_diff.py --a A --b B --seed 0 --frames 200   # 仅当 init 里没写 seed
    python tools/init_diff.py --a A --b B --preset plot --root worlds/generated/s7

初始变量集（完整初始状态，含 seed）由 `run.py --init-set` 读同一套文件
（`presets/<预设>/init-<X>.json` → `presets/scepter/init-<X>.json`），覆盖只发生在
内存里。`--seed` 只是回退：init 文件写了 seed 就以它为准，两份 init 的 seed 必须一致
（用来隔离初始变量），不一致直接报错。

本工具只读：不写 config/、不写状态、不落任何文件。

输出（stdout，JSON）：
    seed                    本次对照实际使用的抽样键（来自 init 文件）
    first_divergence_frame  第一个逐帧签名不同的帧；全程相同则为 null
    dimension_diff          各 knob 在 A/B 下解析出的实际值
    event_diff              事件计数（按 kind）
    final_diff              末帧读数 / 裁决 / 摘要

会话装配复用 run.py 的 `load_session()`，主循环仍是内核的 `Session.step()` ——
这里不复制任何一帧的演化逻辑。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# BLAS 线程数必须钉在 import numpy 之前（与 tests/_support.py 同一套变量）。
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_v, "1")

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError):
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import run as runner  # noqa: E402
from kernel.loader import Config, DataSet  # noqa: E402


def _signature(st):
    """逐帧可比的世界读数。只读 state，不推进任何东西。"""
    return {
        "pool": int(len(st.pool)),
        "noise": round(float(st.noise), 6),
        "promotions": int(st.promotions),
        "domain_index": int(st.domain_index),
        "domains_exhausted": bool(st.domains_exhausted),
        "seats": [[None if s.owner is None else int(s.owner),
                   round(float(s.value), 6)] for s in st.register.slots],
        "progress": [round(float(l.progress), 6) for l in st.loci],
        "deaths": int(st.death_events),
        "destruction": int(st.destruction_events),
        "solver": str(st.solver),
    }


def _event_counts(traj):
    counts = {}
    for _frame, kind, _payload in traj.records:
        key = str(kind)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _final_readout(traj):
    final = traj.final
    conclusion = traj.conclusion if isinstance(traj.conclusion, dict) else {}
    return {
        "verdict": traj.verdict,
        "verdict_frame": traj.verdict_frame,
        "stop_reason": traj.stop_reason,
        "reached_frame": int(traj.reached_frame),
        "iterations": int(traj.iterations),
        "deadlock": bool(traj.deadlock),
        "converged": bool(traj.converged),
        "promotions": int(final.promotions) if final is not None else None,
        "deaths": int(final.death_events) if final is not None else None,
        "destruction": int(final.destruction_events) if final is not None else None,
        "digest": final.digest() if final is not None else None,
        "conclusion": conclusion.get("id"),
        "progress": ([round(float(l.progress), 6) for l in final.loci]
                     if final is not None else None),
    }


def run_init(name, seed=None, frames=300, world_root=ROOT, preset="emergent"):
    """同 run.py 的装配口径跑一组初始变量；返回签名 / 事件 / 末帧读数。

    seed 属于初始变量集：init 文件写了就用它，没写才回退到 `seed`（再不行才用
    预设 / genesis 的口径）。
    """
    data = DataSet(world_root, preset=preset)
    ctx = Config(world_root, lex_overlay=data.preset.get("lexicon"))
    data.apply_params(ctx)
    path, doc = runner.resolve_init_set(world_root, preset, name)
    init_seed = runner.init_set_seed(path, doc)
    if init_seed is not None:
        seed = init_seed
    elif seed is None:
        seed = runner.resolve_seed(None, None, data)
    signatures = []

    def watch(frame, st, _traj):
        signatures.append([int(frame), _signature(st)])
        return True

    sess, meta = runner.load_session(
        ctx, data, seed, watch=watch, init_set=name, world_root=world_root)
    traj = sess.step(frames)
    return {"signatures": signatures, "events": _event_counts(traj),
            "final": _final_readout(traj), "init": meta, "seed": int(seed)}


def first_divergence(signatures_a, signatures_b):
    """第一个签名不同的帧；一条先结束也算分叉（返回那条的下一帧）。"""
    common = min(len(signatures_a), len(signatures_b))
    for i in range(common):
        if signatures_a[i] != signatures_b[i]:
            return int(signatures_a[i][0])
    if len(signatures_a) != len(signatures_b):
        longer = (signatures_a if len(signatures_a) > common else signatures_b)
        return int(longer[common][0])
    return None


def _map_diff(a, b):
    keys = sorted(set(a) | set(b), key=str)
    return {
        "a": a,
        "b": b,
        "changed": {k: [a.get(k), b.get(k)] for k in keys if a.get(k) != b.get(k)},
    }


def compare(a, b):
    """把 run_init() 的两份结果整理成报告。"""
    knob_a = (a.get("init") or {}).get("knobs") or {}
    knob_b = (b.get("init") or {}).get("knobs") or {}
    return {
        "first_divergence_frame": first_divergence(a["signatures"], b["signatures"]),
        "dimension_diff": _map_diff(knob_a, knob_b),
        "event_diff": _map_diff(a["events"], b["events"]),
        "final_diff": _map_diff(a["final"], b["final"]),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="compare two initial-variable sets")
    ap.add_argument("--a", default="A", help="初始变量集 A（默认 A）")
    ap.add_argument("--b", default="B", help="初始变量集 B（默认 B）")
    ap.add_argument("--seed", type=int, default=None,
                    help="抽样键回退：仅在 init 文件没有写 seed 时使用"
                         "（A/B 必须解析出同一个 seed）")
    ap.add_argument("--frames", type=int, default=300)
    ap.add_argument("--preset", default="emergent")
    ap.add_argument("--root", default=None, metavar="DIR",
                    help="世界根目录（含 config/ 与 presets/）；默认项目根")
    args = ap.parse_args(argv)

    world_root = os.path.abspath(args.root) if args.root else ROOT
    try:
        left = run_init(args.a, seed=args.seed, frames=args.frames,
                        world_root=world_root, preset=args.preset)
        right = run_init(args.b, seed=args.seed, frames=args.frames,
                         world_root=world_root, preset=args.preset)
    except runner.InitSetError as err:
        print(f"错误：{err}", file=sys.stderr)
        return 2
    if left["seed"] != right["seed"]:
        print(f"错误：A/B 解析出的 seed 不同（{left['seed']} vs {right['seed']}）——"
              "初始变量对照必须同一个抽样键，否则分不清差异来自哪里",
              file=sys.stderr)
        return 2

    out = compare(left, right)
    out["seed"] = int(left["seed"])
    out["frames"] = int(args.frames)
    out["a"] = {"label": (left.get("init") or {}).get("label"),
                "path": (left.get("init") or {}).get("path")}
    out["b"] = {"label": (right.get("init") or {}).get("label"),
                "path": (right.get("init") or {}).get("path")}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
