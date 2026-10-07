#!/usr/bin/env python3
"""判据 3：数据替换。

把整个 worlds 换掉——只剩 5 个位、命题改成"秩序从何而来"、连"毁灭"这个概念都没有，
给同一台引擎喂进去。它应当照跑，只是讲出另一个故事。

做法：以主 config/ 为底，程序化改写 dim/loci/mapping/conclusions/lexicon，
再配上 tools/alt_world/presets/ 的替代数据（默认机器规格落在 presets/_default/）。

    python3 tools/alt_world/run_alt.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

from engine.conditions import evaluate           # noqa: E402
from engine.core import run                      # noqa: E402
from engine.loader import Config, DataSet        # noqa: E402
from engine.services import default as default_services  # noqa: E402


def _w(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def build_alt_root():
    root = tempfile.mkdtemp(prefix="alt_world_")
    shutil.copytree(os.path.join(ROOT, "config"), os.path.join(root, "config"))
    shutil.copytree(os.path.join(HERE, "presets"), os.path.join(root, "presets"))
    cfg = os.path.join(root, "config")

    # 5 个位
    loci = [
        {"id": "L00", "order": 0, "capacity": 1.00, "decay": 0.020,
         "couplings": [0.0, 0.9, -0.3, 0.2, -0.1]},
        {"id": "L01", "order": 1, "capacity": 1.00, "decay": 0.026,
         "couplings": [0.9, 0.0, 0.8, -0.2, 0.1]},
        {"id": "L02", "order": 2, "capacity": 0.95, "decay": 0.018,
         "couplings": [-0.3, 0.8, 0.0, 0.3, -0.4]},
        {"id": "L03", "order": 3, "capacity": 1.05, "decay": 0.030,
         "couplings": [0.2, -0.2, 0.3, 0.0, 0.7]},
        {"id": "L04", "order": 4, "capacity": 0.90, "decay": 0.034,
         "couplings": [-0.1, 0.1, -0.4, 0.7, 0.0]},
    ]
    _w(os.path.join(cfg, "loci.json"),
       {"_comment": "替代位表：只有 5 个位。", "loci": loci})

    _w(os.path.join(cfg, "mapping.json"), {
        "_comment": "5×4 泛函矩阵。",
        "observables": ["order", "strife", "wealth", "faith"],
        "matrix": [[0.6, -0.2, 0.3, 0.5], [0.2, 0.1, 0.1, 0.3],
                   [0.3, 0.2, 0.4, 0.1], [0.5, -0.1, 0.2, 0.4],
                   [0.1, 0.4, 0.3, -0.1]],
    })

    _w(os.path.join(cfg, "conclusions.json"), {
        "_comment": "结论模板：这里没有'毁灭'，只有'第一因'。裁决短名与停因长句也在这里 ——"
                    "报告层不维护任何写死的枚举表。",
        "proved": {"id": "C_FIRST_CAUSE", "template": "{a} = {b}",
                   "label": "first cause", "stop": "PROVED",
                   "stop_label": "proposition proved",
                   "args": ["first_cause", "first_effect"]},
        "refuted": {"id": "C_UNDECIDED", "template": "inconclusive",
                    "label": "inconclusive", "stop": "REFUTED",
                    "stop_label": "proposition refuted", "args": []},
        "undecided": {"id": "C_UNDECIDED", "template": "inconclusive",
                      "label": "inconclusive", "stop": "UNDECIDED",
                      "stop_label": "not decided", "args": []},
    })

    lex = json.load(open(os.path.join(cfg, "lexicon.json"), encoding="utf-8"))
    lex["regions"] = {"L00": "第一域", "L01": "第二域", "L02": "第三域",
                      "L03": "第四域", "L04": "第五域"}
    lex["events"] = {"OP_SOLVE_ENTROPY": "熵减算子", "OP_SOLVE_DISORDER": "失序算子",
                     "OP_MEMORY_INHERIT": "记忆继承机制", "OP_BIFURCATE": "分化机制",
                     "OP_PROMOTION": "迭代机制", "OP_MEMORY_CONVERGE": "记忆收敛算子",
                     "WRITE_MEMORY": "收拢记忆", "SUPPRESS_SLOT": "压制位"}
    _w(os.path.join(cfg, "lexicon.json"), lex)

    p = json.load(open(os.path.join(cfg, "params.json"), encoding="utf-8"))
    p.update({"dim": 5, "observables": 4, "frames": 12000,
              "pool_capacity": 200, "min_population": 30,
              "capability_names": [None, "suppress_slot", None, "write_memory", None],
              # 这个世界没有「毁灭」这个概念，故判据表也只留两条 ——
              # 判据表里的每一条都必须在 conclusions.json 里查得到文案。
              "verdict_rules": [
                  {"id": "proved", "when": "all_falsified"},
                  {"id": "refuted", "when": "stalled_and_exhausted"},
              ]})
    _w(os.path.join(cfg, "params.json"), p)
    return root


def main():
    root = build_alt_root()
    ctx = Config(root)
    data = DataSet(root)
    traj = run(ctx, data, rules=evaluate, runtime=default_services())

    from engine.assertions import AssertionRunner
    results = AssertionRunner(ctx, data).run(traj)

    st = traj.final
    print(f"替代世界：{len(ctx.loci)} 个位 · 命题 {data.genesis['proposition']['id']}")
    print(f"  迭代 {traj.iterations:,}  再创世 {st.promotions}  涌现 {len(traj.personas)} 位  "
          f"死循环 {traj.deadlock}  收敛 {traj.converged}")
    print(f"  结论 {traj.conclusion['id']}")
    npass = 0
    for r in results:
        print(f"    [{'PASS' if r.ok else 'FAIL'}] {r.name:<28} expect={r.expect!r} got={r.got!r}")
        npass += r.ok
    shutil.rmtree(root, ignore_errors=True)
    if npass == len(results):
        print("✓ 判据 3 通过：同一台引擎，换一套世界，依然跑出另一个自洽的故事。")
        return 0
    print(f"✗ 判据 3：{npass}/{len(results)} 通过。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())