#!/usr/bin/env python3
"""席位承继表：算出「本届十二席」与「上一世十二席」的个体编号。

`presets/*/anchors.jsonl` 里的 `serial:<n>` 是**实测**所得 —— 编号跟着个体走，
所以引擎一旦改了轨迹，锚定就会静默失效（名字退回音位层现生成，不报错）。
这个工具把新编号打出来，直接替换 anchors.jsonl 里各条的 `key` 即可。

    python3 tools/seat_incumbents.py [--preset plot] [--seed N]

两条口径（与剧情对齐，务必照此读）：
  本届    最后一次再创世**之前**在位的那一批。再创世会把十二席清空重占，
          读终局位表读到的是重占上来的新人 —— 那是下一世的开头，不是本届。
  上一世  本届那位**从他手里承位**的上一任；若中间隔着空缺（岁月被仪式剑抹除
          就是这种情形），取那段空缺之前最后一位在位者。

与 anchors.jsonl 的配对靠各条的 `seat` / `era` 字段（`era` 取 curr / prev）。
缺这两个字段的旧条目会单独列出编号，供人工对照。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import jsonl, load, seat_spans               # noqa: E402

#: 每席的在位史【全留】—— 早先这里只留最近 6 段（`KEEP`），对 plot 够用（它的参考帧
#: ——末次再创世前一帧——离跑尾只差 155 帧），但对 nullify 不成立：它的末次再创世离跑尾
#: 还有 3300 多万帧（中间整个永劫回归），凡是在参考帧之后换手 ≥6 次的席位，盖住那一帧的
#: 段就会被裁掉 ⇒ 工具谎报「本次没量到在位者，沿用原条目」（实测 nullify 24 条里只量到 3 条）。
#: 段数与换代次数同量级（几百条），全留的代价可以忽略。


def scan(ctx, data, seed=None):
    """跑一遍，返回 (spans, last_promotion_frame, traj)。口径统一在 `_harness.seat_spans`。

    spans[i] = [{"start":帧, "end":帧或None, "serial":编号}, …]（只记有人坐的段）。
    """
    return seat_spans(ctx, data, seed=seed)


def tenure_at(spans, frame):
    """该席在 frame 那一帧的在位段下标。None = 那一帧空着。"""
    hit = None
    for j, t in enumerate(spans):
        if t["start"] <= frame and (t["end"] is None or frame < t["end"]):
            hit = j
    return hit


def title_of(ctx, locus):
    """职位名（负世 / 岁月…）。取不到就退回位次编号。"""
    cal = (ctx.phonology.get("title_calibration") or {}).get(locus.id)
    return cal[1] if cal else locus.id


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preset", default="plot")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--fast", nargs="?", type=int, const=100, default=0,
                    metavar="K", help="测试提速：时间刻度按 K 压缩（只用于冒烟）")
    args = ap.parse_args()

    ctx, data, root = load(preset=args.preset, fast=args.fast)
    spans, prom_frame, traj = scan(ctx, data, seed=args.seed)
    if prom_frame is None:
        print("本次演算没有发生过再创世 —— 定位不到「本届」那一批。")
        return 1

    at = prom_frame - 1                              # 末次再创世之前那一帧
    path = os.path.join(root, "presets", args.preset, "anchors.jsonl")
    anchors = jsonl(path)
    # 已被别的名字占着的编号（受难之名、以及不属于 curr/prev 的手工绑定）。
    bound = {a.get("key") for a in anchors
             if not (a.get("seat") and a.get("era") in ("curr", "prev"))}

    def prev_of(i, j):
        """上一任：本届那位之前最近的那一段在位。

        若那一位已被别的名字占着（岁月那一席就是这种：本届之前是自逝入剑的昔涟，
        另有一条专门绑定），就继续往前找 —— 于是岁月会落到「原职」欧洛尼斯身上。
        """
        if j is None:
            return None
        for k in range(j - 1, -1, -1):
            if f"serial:{spans[i][k]['serial']}" not in bound:
                return spans[i][k]
        return None

    curr, prev = [], []
    for i in range(len(ctx.loci)):
        j = tenure_at(spans[i], at)
        curr.append(spans[i][j] if j is not None else None)
        prev.append(prev_of(i, j))

    print(f"预设 {args.preset}   种子 {ctx.seed}   末次再创世@{prom_frame:,}"
          f"（本届＝该帧之前在位者）")
    if args.fast and int(args.fast) > 1:
        print(f"⚠ 测试提速 ×{args.fast}：编号只对提速轨迹成立，勿写回预设")
    print()
    print(f"  {'席位':<6}{'本届在位':>10}  {'':<12}{'上一任':>10}")
    for i, l in enumerate(ctx.loci):
        c, p = curr[i], prev[i]
        cn = f"{c['serial']}" if c else "—"
        pn = f"{p['serial']}" if p else "—"
        when = (f"（{p['end']:,} 交位）" if (c and p and p.get("end") is not None)
                else "")
        print(f"  {title_of(ctx, l):<6}{cn:>10}  {'←':<12}{pn:>10}{when}")

    by_slot = {(a.get("seat"), a.get("era")): a
               for a in anchors if a.get("seat") and a.get("era")}
    # 本工具只管 curr（末年那一位）与 prev（他从其手里承位的上一任）两类；
    # 其余条目 —— 受难之名、不属于这两代的手工绑定 —— 原样带出，免得被一次重测冲掉。
    kept = [json.dumps(a, ensure_ascii=False) for a in anchors
            if not (a.get("seat") and a.get("era") in ("curr", "prev"))]
    lines, missing = [], []
    for i, l in enumerate(ctx.loci):
        for era, rec in (("curr", curr[i]), ("prev", prev[i])):
            a = by_slot.get((l.id, era))
            if a is None:
                if rec is not None:
                    missing.append((l.id, era, rec["serial"]))
                continue
            if rec is None:
                print(f"⚠ {l.id}/{era}：本次没量到在位者，沿用原条目")
                lines.append(json.dumps(a, ensure_ascii=False))
                continue
            out = dict(a)
            out["key"] = f"serial:{rec['serial']}"
            lines.append(json.dumps(out, ensure_ascii=False))
    managed = list(lines)
    lines = lines + kept

    print()
    if not by_slot:
        print("（anchors.jsonl 里没有带 seat/era 字段的条目 —— 新编号如下，请人工对照）")
        for i, l in enumerate(ctx.loci):
            for era, rec in (("curr", curr[i]), ("prev", prev[i])):
                if rec is not None:
                    print(f"  {l.id:<5}{era:<6}serial:{rec['serial']}")
        return 0

    old = {a.get("key") for a in anchors if a.get("era") in ("curr", "prev")}
    new = {json.loads(s).get("key") for s in managed}
    print("可直接粘贴的行（" + os.path.relpath(path, root) + "）：")
    for s in lines:
        print(s)
    print()
    for lid, era, serial in missing:
        print(f"注：{lid}/{era}（编号 {serial}）在 anchors.jsonl 里没有对应条目")
    print("✓ 与现有锚定一致" if new == old else
          f"✍ 需要更新：{len(new ^ old)} 个 serial: 键有变动")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
