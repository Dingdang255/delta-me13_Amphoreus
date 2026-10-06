#!/usr/bin/env python3
"""机制对照：一次「作用到指定席位」的投递，究竟是**结构性**的，还是只是**噪声**？

`presets/plot-mech` 把 6 条 `emit` 桥段升级成 `evict_holder`（另 1 条升级成 `parley`），
换代从 82 掉到 48。这看着
像"剧情生效了"。但世界本来是混沌的 —— 同样数量、同样帧位的扰动，随便换个目标席位，
换代就可能落到完全不同的地方。本工具就是把这件事量出来：

  基准组   不动（`--base`，默认 presets/plot）
  机制组   照 `--mech`（默认 presets/plot-mech）的帧位与席位原样跑
  噪声组   **同样帧位、同样次数**，只把目标席位换成与剧情无关的那些（跑 `--variants` 组）

判定：机制组的读数若落在噪声组的区间里 ⇒ **与任意等效扰动无法区分**，说明那是混沌放大，
不是"剧情语义生效"。反之（机制组明显在区间之外）才说明这次投递是结构性的。

    python tools/mech_control.py                     # 默认 plot vs plot-mech，3 组噪声
    python tools/mech_control.py --variants 5
    python tools/mech_control.py --seats 2,3,4,5,6,11 --out 对照.json

**只读**：三组世界都在**临时根**里跑（复制 config/data 到临时目录，预设也在那里生成），
仓库里的 `presets/` 一个字节都不会多、也不会少。删掉本文件，演算逐帧不变。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import BAR, ROOT, jsonl, rules, services      # noqa: E402

from engine.core import run                                 # noqa: E402
from engine.loader import Config, DataSet                    # noqa: E402


def varied_records(base_events, mech_events):
    """`mech` 相对 `base` **多出来的**那些投递 —— 就是要拿去做对照的那一批。

    按整条记录比对（帧 / 能力 / 选择器 / payload 全同才算"不是多出来的"），
    于是本工具对 `evict_holder` 之外的能力同样成立。
    """
    base = {json.dumps(r, sort_keys=True, ensure_ascii=False) for r in base_events}
    out = [r for r in mech_events
           if json.dumps(r, sort_keys=True, ensure_ascii=False) not in base]
    return out


def story_seats(records):
    """机制组点到的席位（`order:<n>`）集合 —— 噪声组要避开它们。"""
    seats = set()
    for r in records:
        expr = (r.get("selector") or {}).get("expr") or ""
        if expr.startswith("order:"):
            seats.add(int(expr.split(":", 1)[1]))
    return seats


def noise_plan(records, pool, variant, n_loci):
    """第 `variant` 组噪声的席位序列：同样帧位与次数，席位从 `pool` 里轮转取。

    用 `(k*(v+1)+v) % len(pool)` 这个确定式轮转 —— 各组互不相同、且都可复现。
    零预算：只读，不掷骰子。
    """
    seats = []
    for k, _r in enumerate(records):
        seats.append(pool[(k * (variant + 1) + variant) % len(pool)])
    return seats


def write_variant(tmp_root, name, mech_preset, records, plan):
    """在临时根里造一个预设：**机制预设**的副本，把 `records` 的选择器换成 `plan`。

    必须从 `--mech` 取事件表 —— 那 7 条投递只存在于机制预设里（基准预设里没有它们）。
    从基准取的话会一条都换不到，跑出来的"噪声组"其实等于基准，对照就成了空转
    （本工具初版就栽在这儿：三组噪声读数与基准逐位相同，却还报"落在区间之外"）。
    故这里对换到的条数做**硬校验**：对不上就当场报错，绝不静默出一张假表。
    """
    dst = os.path.join(tmp_root, "presets", name)
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(os.path.join(ROOT, "presets", mech_preset), dst)
    keys = [json.dumps(r, sort_keys=True, ensure_ascii=False) for r in records]
    idx = {k: i for i, k in enumerate(keys)}
    out, used = [], 0
    for r in jsonl(os.path.join(ROOT, "presets", mech_preset, "events.jsonl")):
        key = json.dumps(r, sort_keys=True, ensure_ascii=False)
        if key in idx:
            r = dict(r)
            r["selector"] = {"expr": "order:%d" % plan[used]}
            used += 1
        out.append(r)
    if used != len(records):
        raise ValueError(
            f"只换到 {used}/{len(records)} 条 —— 变体没造对，对照会变成空转")
    with open(os.path.join(dst, "events.jsonl"), "w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return used


def measure(root, preset, seed=None, frames=None):
    """跑一个预设，返回它的读数（只读）。"""
    ctx = Config(root)
    data = DataSet(root, preset=preset)
    traj = run(ctx, data, seed=seed, max_frames=frames, rules=rules(),
               runtime=services())
    return {
        "preset": preset,
        "promotions": int(traj.final.promotions),
        "iterations": int(traj.iterations),
        "reached_frame": int(traj.reached_frame),
        "verdict": traj.verdict,
        "entropy": round(float(traj.final.entropy), 6),
    }


def render(rows, tier):
    out = [BAR, "  δ-me13「翁法罗斯」机制对照（结构性 or 噪声？）", BAR]
    out.append(f"  {'组':<12}{'换代':>6}{'迭代':>9}{'走到帧':>12}{'裁决':>14}"
               f"{'熵':>10}")
    for r in rows:
        out.append(f"  {r['preset']:<12}{r['promotions']:>6}{r['iterations']:>9,}"
                   f"{r['reached_frame']:>12,}{str(r['verdict']):>14}"
                   f"{r['entropy']:>10.4f}")
    mech = next((r for r in rows if r["kind"] == "mech"), None)
    noise = [r["promotions"] for r in rows if r["kind"] == "noise"]
    base = next((r for r in rows if r["kind"] == "base"), None)
    out.append("")
    if base:
        # 防呆：噪声组若与基准**逐位相同**，多半是投递根本没生效（空转），不是"很稳"。
        blind = [r["preset"] for r in rows if r["kind"] == "noise"
                 and (r["promotions"], r["iterations"], r["entropy"])
                 == (base["promotions"], base["iterations"], base["entropy"])]
        if blind:
            out.append(f"  ⚠ {len(blind)} 组噪声读数与基准逐位相同（{'、'.join(blind)}）"
                       f"—— 投递可能没生效，这张表不可信")
    if mech and noise:
        lo, hi = min(noise), max(noise)
        inside = lo <= mech["promotions"] <= hi
        out.append(f"  机制组换代 {mech['promotions']}"
                   + (f"　基准组 {base['promotions']}" if base else "")
                   + f"　噪声组 {noise}（区间 {lo}–{hi}）")
        out.append("  ✗ 机制组落在噪声区间内 ⇒ **与任意等效扰动无法区分**："
                   "那是混沌放大，不是「剧情语义生效」" if inside else
                   "  ✓ 机制组落在噪声区间之外 ⇒ 这次投递是**结构性**的："
                   "换目标席位就复现不出同样的读数")
    out.append(f"  投递数 {tier['n_records']}（可换目标的 {tier['n_varied']} 条）"
               f"　噪声席位池 {tier['pool']}　基准 {tier['base']}　机制 {tier['mech']}")
    out.append(BAR)
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="机制对照：结构性 or 噪声（只读）")
    ap.add_argument("--base", default="plot", help="基准预设（不动）")
    ap.add_argument("--mech", default="plot-mech", help="机制预设（提供帧位与次数）")
    ap.add_argument("--variants", type=int, default=3, help="噪声组数（默认 3）")
    ap.add_argument("--seats", default=None,
                    help="噪声席位池，逗号分隔（默认取机制未用到的全部席位）")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--frames", type=int, default=None, help="帧预算（默认满预算）")
    ap.add_argument("--out", default=None, help="把读数写成 JSON")
    args = ap.parse_args()

    base_events = jsonl(os.path.join(ROOT, "presets", args.base, "events.jsonl"))
    mech_events = jsonl(os.path.join(ROOT, "presets", args.mech, "events.jsonl"))
    records = varied_records(base_events, mech_events)
    vary = [r for r in records if r.get("selector")]
    if not vary:
        print(f"✗ {args.mech} 相对 {args.base} 没有【带选择器】的多余投递，无事可对照。",
              file=sys.stderr)
        return 2

    n_loci = len(Config(ROOT).loci)
    used = story_seats(records)
    if args.seats:
        pool = [int(x) for x in str(args.seats).split(",")]
    else:
        pool = [i for i in range(n_loci) if i not in used]
    if not pool:
        print("✗ 噪声席位池是空的 —— 没有与剧情无关的席位可用。", file=sys.stderr)
        return 2

    tier = {"n_records": len(records), "n_varied": len(vary),
            "pool": pool, "base": args.base, "mech": args.mech}
    print(f"对照 {args.base}（基准） vs {args.mech}（机制）："
          f"{len(records)} 条多出的投递，其中 {len(vary)} 条带选择器可换目标")
    print(f"剧情占用的席位 {sorted(used)}　噪声席位池 {pool}　噪声组 {args.variants} 组\n")

    tmp = tempfile.mkdtemp(prefix="mech_control_")
    for name in ("config", "data"):
        shutil.copytree(os.path.join(ROOT, name), os.path.join(tmp, name))
    os.makedirs(os.path.join(tmp, "presets"))
    # 基准与机制：直接把真预设复制进临时根（读的是同一份配置），不污染仓库。
    for src in (args.base, args.mech):
        shutil.copytree(os.path.join(ROOT, "presets", src),
                        os.path.join(tmp, "presets", src))

    rows = []
    for kind, name in (("base", args.base), ("mech", args.mech)):
        t0 = time.time()
        row = measure(tmp, name, seed=args.seed, frames=args.frames)
        row["kind"], row["seconds"] = kind, round(time.time() - t0, 1)
        rows.append(row)
        print(f"  ✓ {name:<12}换代 {row['promotions']:>4}"
              f"　迭代 {row['iterations']:>8,}　({row['seconds']}s)")

    for v in range(max(0, int(args.variants))):
        name = f"noise{v + 1}"
        plan = noise_plan(vary, pool, v, n_loci)
        write_variant(tmp, name, args.mech, vary, plan)
        t0 = time.time()
        row = measure(tmp, name, seed=args.seed, frames=args.frames)
        row["kind"], row["seconds"] = "noise", round(time.time() - t0, 1)
        row["seats"] = plan
        rows.append(row)
        print(f"  ✓ {name:<12}换代 {row['promotions']:>4}"
              f"　迭代 {row['iterations']:>8,}　({row['seconds']}s)"
              f"　席位 {plan}")

    print()
    print(render(rows, tier))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({"tier": tier, "seed": args.seed, "frames": args.frames,
                       "rows": rows}, f, ensure_ascii=False, indent=1)
        print(f"  读数已写入 {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())