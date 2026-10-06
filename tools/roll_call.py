#!/usr/bin/env python3
"""逐火点名录 —— 把「席位级的机制」讲成一张「有人死、有人活的逐火史」。

这是个体史（运行期账本 `State.tombstones` / `State.chronicle`）的第一个消费者。

在个体史之前，引擎只把个体当**统计样本**：`kill()` 之后槽位立刻可被 `alloc()` 复用并
覆盖，于是"谁死了、因何、被谁"在下一个补种之后就查不到；而"谁从谁手里接的位"从未记录。
现在这两样都在账本里，且**跑完之后还在** —— 所以本工具事后就能点名。

    python tools/roll_call.py                       # 默认 plot-mech（逐火之旅）
    python tools/roll_call.py --preset plot
    python tools/roll_call.py --out 点名录.json

**只读**：只跑一次演算、只读账本与渲染词表，不写回任何文件。删掉本文件，演算逐帧不变。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import BAR, load, rules, services             # noqa: E402

from engine.core import run                                 # noqa: E402
from engine.render import renderer_for                      # noqa: E402
from engine.state import DEATH_CAUSES, EXTERNAL_CAUSES      # noqa: E402

#: 死因 → 人话。都是通用词（引擎侧只记枚举名，中文只在这一层）。键集取自引擎的
#: `DEATH_CAUSES` —— 少一条文案会在 import 时 KeyError（不静默漏字）。
_CAUSE_TEXT = {
    "aged": "寿终",
    "isolated": "被孤立",
    "homogenized": "被同化",
    "dethroned": "被夺席",
    "evicted": "被逐出",
    "displaced": "为接掌者让位",
}
CAUSE_LABELS = {c: _CAUSE_TEXT[c] for c in DEATH_CAUSES}
#: 「外生干预」类死因 —— 逐火之旅的伤亡就是它们。
EXTERNAL = EXTERNAL_CAUSES


def _by_text(cause, by) -> str:
    if by is not None:
        return str(by)
    return "（外生·未记名）" if cause in EXTERNAL else "—"


def collect(traj, ctx):
    """把账本整理成可渲染的结构。只读。"""
    st = traj.final
    stones = list(st.tombstones)
    rec = st.chronicle
    born = len(rec)
    # 死因分布
    causes = Counter(c for _f, _s, _fa, c, _b in stones)
    # 承位链：谁从谁手里接的
    lineage = [(s, r["from_serial"]) for s, r in rec.items()
               if r.get("from_serial") is not None]
    return {
        "born": born,
        "died": len(stones),
        "alive": born - len(stones),
        "causes": causes,
        "stones": stones,
        "lineage": lineage,
        "external": [row for row in stones if row[3] in EXTERNAL],
        "dethroned": [row for row in stones if row[3] == "dethroned"],
        "factor_of": {s: r["factor"] for s, r in rec.items()},
    }


def build_report(ctx, data, traj, blob, top: int = 40):
    R = renderer_for(ctx, traj)
    frame = int(traj.reached_frame)

    def seat_of(factor):
        if 0 <= int(factor) < len(ctx.loci):
            return R.seat(traj.namer, frame, ctx.loci[int(factor)].id)
        return f"第 {factor} 号"

    out = [BAR, "  δ-me13「翁法罗斯」逐火点名录", BAR]
    now = R.locale(frame)
    out.append(f"  预设 {data.preset.get('name')}　种子 {ctx.seed}　走到帧 {frame:,}"
               + (f"（{now}）" if now else ""))
    out.append(f"  裁决 {R.verdict_label(traj.verdict)}"
               f"　{R.stop_label(traj.stop_reason)}")
    out.append("")
    out.append("【一】总账（个体史账本：只增不减，跑完之后仍在）")
    out.append(f"  登场 {blob['born']:,} 位 · 陨落 {blob['died']:,} 位"
               f" · 落幕时仍在 {blob['alive']:,} 位")
    dist = "　".join(f"{CAUSE_LABELS.get(c, c)} {n:,}"
                     for c, n in blob["causes"].most_common()) or "（无）"
    out.append(f"  死因　{dist}")
    out.append("")
    out.append("【二】外生干预下的伤亡 —— 逐火之旅里「谁被谁动了」")
    ext = blob["external"]
    if not ext:
        out.append("  （本次世界没有任何席位被外生逐出 / 接掌）")
    else:
        out.append(f"  {'帧':>12}  {'席位':<18}{'编号':>10}  {'死因':<12}由谁")
        for f, serial, factor, cause, by in sorted(ext):
            out.append(f"  {f:>12,}  {seat_of(factor):<18}{serial:>10}  "
                       f"{CAUSE_LABELS.get(cause, cause):<12}{_by_text(cause, by)}")
    out.append("")
    out.append("【三】承位链 —— 引擎里唯一真实的「传承关系」"
               "（本世的承位者顶掉上一世的在位者）")
    lin = blob["lineage"]
    if not lin:
        out.append("  （本次世界没有发生过世代之内的夺席）")
    else:
        out.append(f"  共 {len(lin):,} 次承位"
                   f"（被夺席者 {len(blob['dethroned']):,} 位，全部记 `被夺席`）")
        for serial, src in sorted(lin)[:top]:
            out.append(f"    {src:>8} ──▶ {serial:<8}"
                       f"（接自 {seat_of(blob['factor_of'].get(src, -1))}）")
        if len(lin) > top:
            out.append(f"    …… 共 {len(lin):,} 条")
    out.append(BAR)
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="逐火点名录（只读）")
    ap.add_argument("--preset", default="plot-mech")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--frames", type=int, default=None)
    ap.add_argument("--fast", nargs="?", type=int, const=100, default=0, metavar="K")
    ap.add_argument("--top", type=int, default=40, help="承位链最多列出的条数")
    ap.add_argument("--out", default=None, help="把点名录写成 JSON")
    args = ap.parse_args()

    ctx, data, _root = load(preset=args.preset, fast=args.fast)
    traj = run(ctx, data, seed=args.seed, max_frames=args.frames, rules=rules(),
               runtime=services())
    blob = collect(traj, ctx)

    print(build_report(ctx, data, traj, blob, top=args.top))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({
                "preset": data.preset.get("name"), "seed": int(ctx.seed),
                "reached_frame": int(traj.reached_frame),
                "born": blob["born"], "died": blob["died"],
                "causes": dict(blob["causes"]),
                "external": [{"frame": f, "serial": s, "factor": fa,
                              "cause": c, "by": b}
                             for f, s, fa, c, b in sorted(blob["external"])],
                "lineage": [{"heir": h, "from": o} for h, o in blob["lineage"]],
            }, f, ensure_ascii=False, indent=1)
        print(f"  点名录已写入 {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())