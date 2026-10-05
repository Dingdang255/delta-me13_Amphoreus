#!/usr/bin/env python3
"""从考据规格生出预设的外部实体表（F3）。

    python tools/actors_from_spec.py                          # 打给 plot 看
    python tools/actors_from_spec.py --preset nullify          # 看别的预设
    python tools/actors_from_spec.py --preset plot --write      # 写回 actors.json
    python tools/actors_from_spec.py --preset plot --check      # 与现状比对（CI 用）

规格在 `docs/外部变量.json`（`docs/外部变量.md` 的机器可读版）。这样「考据」与
「引擎真读的那张表」是同一份东西的两个形态：改考据 → 重生成 → 单测核对，
不会出现「文档写了一套、actors.json 里是另一套」。
"""
from __future__ import annotations

import argparse
import io
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = os.path.join(ROOT, "docs", "外部变量.json")

COMMENT = ("外部实体表：谁在操作这个世界、各自握有哪些修改权限。名字只在这里，"
           "引擎不认识它们 —— 引擎只认「已登记的实体」与「它的权限表」。"
           "本文件由 docs/外部变量.json 派生（tools/actors_from_spec.py），请勿手改。")


def load_spec():
    with io.open(SPEC, encoding="utf-8") as f:
        return json.load(f)


def build(spec):
    """规格 → actors.json 的内容（只保留引擎真读的字段：id / label / grants）。"""
    actors = []
    for a in spec["actors"]:
        item = {"id": a["id"], "label": a["label"], "grants": list(a.get("grants") or [])}
        if a.get("note"):
            item["note"] = a["note"]
        actors.append(item)
    return {"_comment": COMMENT, "actors": actors}


def path_of(preset):
    return os.path.join(ROOT, "presets", preset, "actors.json")


def main():
    ap = argparse.ArgumentParser(description="从考据规格生成预设的外部实体表")
    ap.add_argument("--preset", default="plot")
    ap.add_argument("--write", action="store_true", help="写回 presets/<预设>/actors.json")
    ap.add_argument("--check", action="store_true", help="与现状比对，不一致则退出码 1")
    args = ap.parse_args()

    built = build(load_spec())
    text = json.dumps(built, ensure_ascii=False, indent=2) + "\n"
    target = path_of(args.preset)

    if args.write:
        with io.open(target, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print(f"已写入 {target}（{len(built['actors'])} 个实体）")
        return 0
    if args.check:
        if not os.path.exists(target):
            print(f"✗ {target} 不存在（该预设没有外部实体表）")
            return 1
        cur = io.open(target, encoding="utf-8").read()
        if json.loads(cur) == built:
            print(f"✓ {args.preset} 的外部实体表与考据一致（{len(built['actors'])} 个）")
            return 0
        print(f"✗ {target} 与 docs/外部变量.json 不一致 —— "
              f"跑 python tools/actors_from_spec.py --preset {args.preset} --write")
        return 1
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
