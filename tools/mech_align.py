#!/usr/bin/env python3
"""锚定对齐表 —— 让「剧情桥段」与「点名角色」在同一帧上对上的那张表。

为什么需要它（B6-L2 的实测结论）：

  `plot-mech` 把 6 条桥段升级成了真机制（`evict_holder`），机制**确实执行了**，但
  12,000–36,000 帧那几帧坐在目标席上的是**无名个体**，而锚定层点名的那些角色首次就位
  要晚得多（**现测：41,899 帧之后**）—— 于是"机制作用到席位"并不等于"作用到那位角色"。
  ⚠ 具体编号与帧号随每次锚定重测而变，一律以**本工具现测**为准。

  而 `plot` 自己那条 42,000 帧的 `suppress_slot order:1` 是唯一对得上的一处：那一刻坐在
  岁月席上的是**已点名角色**（现测为 **欧洛尼斯 serial:25220**）。**帧号一对齐，机制就打在
  了点名的那位身上。**

本工具就是把这件事量成一张表：**逐席列出每个锚定角色各自在哪些帧坐在哪儿**，并可选地
把一份剧本里的机制投递逐条对上去，判定「对齐 / 错位」。

    python tools/mech_align.py                          # 逐席的锚定角色在位窗口
    python tools/mech_align.py --check plot-mech        # 顺带核对它的机制投递对不对得上
    python tools/mech_align.py --frames 100000          # 先粗看（默认满预算）

**只读**：只跑一次演算、只读锚定层与剧本，不写回任何文件。删掉本文件，演算逐帧不变。

**两条口径，务必知悉**：

* 「谁坐在这一席」按 `register.slots[i].owner` 算 —— 因为**逐出 / 接掌这类扰动看的正是这个
  字段**（压制只把位封住，不清 owner）。于是本表回答的是"机制会打在谁身上"。
* 对齐表按**基准预设**的轨道算。机制一旦改动了世界，轨道就会漂 ⇒ 本表是**设计参考**，
  不是"改了之后仍然成立"的保证。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import BAR, jsonl, load, seat_spans, serial_of  # noqa: E402


def scan(ctx, data, seed=None, frames=None):
    """逐席扫在位段（只记【有人坐】的段）。口径统一在 `_harness.seat_spans`。"""
    spans, _prom, traj = seat_spans(ctx, data, seed=seed, frames=frames)
    return spans, traj


def anchors_of(root, preset):
    """锚定层里所有带 `serial:` 键的条目 —— 点过名的那些个体。"""
    out = {}
    for a in jsonl(os.path.join(root, "presets", preset, "anchors.jsonl")):
        serial = serial_of(a.get("key"))
        if serial is None:
            continue
        out[serial] = a
    return out


def windows(spans, anchors):
    """{席位下标: [(serial, start, end|None), …]}，只留锚定层点过名的那些 serial。"""
    out = {}
    for i, segs in enumerate(spans):
        rows = [(sp["serial"], int(sp["start"]),
                 None if sp["end"] is None else int(sp["end"]))
                for sp in segs if sp["serial"] in anchors]
        if rows:
            out[i] = rows
    return out


def owner_at(spans, seat, frame):
    """该席在 `frame` 那一帧的在位者（按 `slot.owner` 口径）。空席返回 None。"""
    hit = None
    for sp in spans[seat]:
        if sp["start"] <= frame and (sp["end"] is None or frame < sp["end"]):
            hit = int(sp["serial"])
    return hit


def name_of(anchors, serial):
    a = anchors.get(serial)
    if not a:
        return f"serial:{serial}（未点名）"
    who = a.get("hanzi") or a.get("latin") or f"serial:{serial}"
    tail = "（场外）" if a.get("external") else ""
    return f"{who} serial:{serial}{tail}"


def judge(anchors, incumbent, payload):
    """这一条机制「打的是谁」，以及那个人有没有被点名。返回 (显示名, 是否点名角色)。

    `evict_holder` / `suppress_slot` 作用在**在位者**身上；`bind_participant` 则是把
    `payload.participant` 那个场外参与者**放上席**（顺带让现任让位）—— 故后者要看
    装上去的那个人，否则会把 plot 那条「丹恒接住大地权能」误判成"错位"
    （那一刻在位的是无名个体 26443，而机制真正装上去的是场外参与者 -3 = 丹恒）。
    """
    part = (payload or {}).get("participant")
    if part is not None:
        part = int(part)
        return name_of(anchors, part), part in anchors
    if incumbent is None:
        return "空席", False
    return name_of(anchors, incumbent), incumbent in anchors


def mechanisms_of(root, preset):
    """一份剧本里**真改世界**的投递（非 emit、且带选择器）—— 就是要对齐的那些桥段。"""
    d = os.path.join(root, "presets", preset)
    recs = (jsonl(os.path.join(d, "disturbances.jsonl"))
            + jsonl(os.path.join(d, "events.jsonl")))
    return [r for r in sorted(recs, key=lambda r: int(r["frame"]))
            if r.get("capability") != "emit" and (r.get("selector") or {}).get("expr")]


def render(ctx, traj, anchors, win, checks, preset, reach):
    from engine.render import renderer_for
    R = renderer_for(ctx, traj)
    frame = int(traj.reached_frame)

    def seat(i):
        return f"{R.seat(traj.namer, frame, ctx.loci[i].id)}（{ctx.loci[i].id}）"

    out = [BAR, "  δ-me13「翁法罗斯」锚定对齐表", BAR]
    now = R.locale(frame)
    out.append(f"  预设 {preset}　种子 {ctx.seed}　走到帧 {reach:,}"
               + (f"（{now}）" if now else ""))
    out.append(f"  锚定条目 {len(anchors)} 条（点过名的个体）")
    out.append("")
    out.append("【一】逐席 · 锚定角色在位窗口（机制打在这一席，就会打在这些人身上）")
    missed, placed = [], []
    for serial, a in anchors.items():
        hits = [(i, s, e) for i, rows in win.items()
                for (sr, s, e) in rows if sr == serial]
        if hits:
            placed.append((min(s for _i, s, _e in hits), serial, hits))
        else:
            missed.append((serial, a))
    placed.sort()                       # 按【首次就位帧】排 —— 顺时序读最直观
    for _first, serial, hits in placed:
        for i, s, e in hits:
            stop = reach if e is None else e - 1
            span = (f"帧 {s:,} – {stop:,}"
                    + ("（终局仍在位）" if e is None else ""))
            out.append(f"  · {name_of(anchors, serial):<30}{seat(i)}"
                       f"　{span}（{stop - s + 1:,} 帧）")
    if not win:
        out.append("  （本轨没有任何锚定角色落座过）")
    if placed:
        starts = [min(s for _i, s, _e in hits) for _f, _s, hits in placed]
        out.append(f"  ⇒ 锚定角色的【首次就位】集中在帧 {min(starts):,} – {max(starts):,}"
                   f"（跨度 {max(starts) - min(starts):,} 帧）。"
                   f"桥段要打在点名角色身上，就该落在**该角色自己那一段**窗口内（见上）。")
        out.append("    注意：窗口是**逐角色各自**的，不是共同区间 —— 各条彼此错开，"
                   "要按角色分别定位。")
    out.append("")
    out.append("【二】未在本轨就位的锚定条目（占了名字、却一次都没坐上席）")
    if missed:
        for serial, a in missed:
            out.append(f"  · {name_of(anchors, serial):<30}预期席位 "
                       f"{a.get('seat') or '—'}")
    else:
        out.append("  （无 —— 所有点名过名的个体都落过座）")
    out.append("")
    if checks is not None:
        out.append("【三】剧情桥段对齐核对 —— 这一条机制会打在谁身上")
        out.append(f"  {'帧号':>12}  {'目标席':<18}{'机制':<16}"
                   f"{'那一刻的在位者':<28}{'经手/接手':<28}判定")
        aligned = 0
        for c in checks:
            mark = "✓ 点名角色" if c["anchored"] else "✗ 另有其人"
            aligned += 1 if c["anchored"] else 0
            out.append(f"  {c['frame']:>12,}  {seat(c['seat']):<18}"
                       f"{c['capability']:<16}{c['who']:<28}{c['subject']:<28}{mark}")
        out.append("")
        out.append(f"  → {aligned}/{len(checks)} 条打在了点名角色身上；"
                   f"错位的那些，把帧号挪进该席的窗口（见【一】）即可。"
                   if checks else "  （这份剧本里没有可对齐的机制投递）")
    out.append(BAR)
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="锚定对齐表（只读）")
    ap.add_argument("--preset", default="plot", help="基准预设（算窗口用）")
    ap.add_argument("--check", default=None,
                    help="额外核对这份剧本里的机制投递对不对得上点名角色（如 plot-mech）")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--frames", type=int, default=None,
                    help="帧预算（默认满预算；粗看时可调小）")
    ap.add_argument("--fast", nargs="?", type=int, const=100, default=0, metavar="K")
    ap.add_argument("--out", default=None, help="把对齐表写成 JSON")
    args = ap.parse_args()

    ctx, data, root = load(preset=args.preset, fast=args.fast)
    spans, traj = scan(ctx, data, seed=args.seed, frames=args.frames)
    anchors = anchors_of(root, args.preset)
    win = windows(spans, anchors)
    reach = int(traj.reached_frame)

    checks = None
    if args.check:
        checks = []
        for r in mechanisms_of(root, args.check):
            seat = int(r["selector"]["expr"].split(":", 1)[1])
            frame = int(r["frame"])
            serial = owner_at(spans, seat, frame)
            subject, anchored = judge(anchors, serial, r.get("payload") or {})
            checks.append({
                "frame": frame,
                "seat": seat,
                "capability": str(r.get("capability")),
                "serial": serial,
                "who": ("空席" if serial is None else name_of(anchors, serial)),
                "subject": subject,
                "anchored": anchored,
            })

    print(render(ctx, traj, anchors, win, checks, args.preset, reach))
    if args.out:
        blob = {
            "preset": args.preset, "seed": int(ctx.seed), "reached_frame": reach,
            "anchors": {str(k): v for k, v in anchors.items()},
            "windows": {ctx.loci[i].id: [{"serial": s, "start": a, "end": b}
                                         for s, a, b in rows]
                        for i, rows in win.items()},
            "checks": checks,
        }
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(blob, f, ensure_ascii=False, indent=1)
        print(f"  对齐表已写入 {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())