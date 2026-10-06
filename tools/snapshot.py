#!/usr/bin/env python3
"""轨迹指纹：把「同一组输入跑出来的世界」压成几个读数，改动引擎后一眼看出有没有动。

    python tools/snapshot.py                 # 核对全部条目（含慢条目）
    python tools/snapshot.py --fast          # 只核对快条目
    python tools/snapshot.py --write         # 重算并写回指纹（只在你确认轨迹该变时用）

指纹内容：裁决 / 结论 id / 走的帧 / 迭代数 / 换代次数 / 涌现人数 / 最终状态摘要 /
十二席在位者编号。其中 **摘要（digest）是逐位校验**：向量、席位占用、被压制的位、
门、演算方向、熵、换代计数全在里面 —— 它一变，说明演算真的变了。

为什么需要它：这个项目的验收靠「断言 + 时间线」，那是**点位**核对；指纹是**逐位**
核对，且不需要跑满预算就能发现漂移。改完引擎先跑它，再跑 tools/selfcheck.py。

**字段分层（跨平台）**：指纹分三层比对，这一层划分让 CI 不必锁死某个操作系统 ——

  · 结构层（`STRUCTURAL_FIELDS`）：整数 / 枚举 / 席位编号，逐位相等，跨平台成立；
  · 数值层（`NUMERIC_FIELDS`）：`entropy` / `noise`，按容差相等，吸收 BLAS / SIMD
    归约顺序带来的末位差异；
  · 摘要层（`digest`）：量化过的 float32 向量哈希，**只在写入本指纹的同一环境上**
    逐位可比 —— `_reference_platform` 记着 OS / CPU 架构 / Python / numpy 四项，
    **四项全同**才比 digest，任何一项不同即降级（并在输出里说明是哪一项）。

于是同一环境上仍是逐位严格（能抓真回归），换机器 / 换 numpy / 换 CI runner 都不会误报。
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.conditions import evaluate           # noqa: E402
from engine.core import run                      # noqa: E402
from engine.loader import Config, DataSet        # noqa: E402
from engine.services import default as default_services  # noqa: E402

GOLDEN = os.path.join(ROOT, "tests", "golden_fingerprints.json")

#: 结构层：整数 / 枚举 / 席位编号 —— 逐位相等，跨平台成立（CI 门禁靠它）。
STRUCTURAL_FIELDS = ("verdict", "conclusion", "stop_reason", "reached_frame",
                     "iterations", "skipped_frames", "promotions", "personas",
                     "population", "destruction_events", "ascended", "seats")
#: 数值层：浮点读数 —— 容差相等，吸收 BLAS / SIMD 的末位差异。
NUMERIC_FIELDS = ("entropy", "noise")
#: 摘要层：量化 float32 的哈希 —— 只在参考平台上逐位可比。
DIGEST_FIELD = "digest"
#: 记录参考平台的键（golden 顶层）。异平台据此跳过 digest 逐位比对。
REFERENCE_KEY = "_reference_platform"
#: 数值层的相对容差（相对量级，见 `_close`）。
_NUM_TOL = 1e-6


def _close(a, b, tol: float = _NUM_TOL) -> bool:
    """容差相等：相对量级比较，两端都按 max(1, |a|, |b|) 归一。"""
    if a is None or b is None:
        return a == b
    scale = max(1.0, abs(float(a)), abs(float(b)))
    return abs(float(a) - float(b)) <= tol * scale


def _current_reference() -> dict:
    return {
        "system": platform.system(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "note": ("digest 是量化 float32 向量的哈希，只在四项（system/machine/python/numpy）"
                 "全同的环境上逐位可比；否则以结构层（STRUCTURAL_FIELDS）为准，"
                 "数值层走容差。"),
    }


#: 参与 digest 可比性判定的四项 —— 顺序即报错时的呈现顺序。
_REF_KEYS = ("system", "machine", "python", "numpy")


def _mine(key: str) -> str:
    return {"system": platform.system(), "machine": platform.machine(),
            "python": platform.python_version(), "numpy": np.__version__}[key]


def digest_comparable(ref) -> tuple[bool, str]:
    """digest 能否与本机逐位比对？返回 `(可比?, 说明)`。

    digest 是量化 float32 向量的哈希，同时受 **OS / CPU 架构 / Python / numpy(BLAS)**
    影响 —— 任何一项不同，末位都可能漂。故逐项比对 `_reference_platform` 里**记了的**
    那一项：全同才比 digest；任一不同即降级为结构层，并说明是差在哪一项（旧指纹缺项
    不算不同，以兼容历史指纹）。
    """
    ref = ref or {}
    if not ref.get("system"):
        return False, "指纹未记录参考平台 ⇒ 跳过 digest 逐位比对"
    for key in _REF_KEYS:
        want = ref.get(key)
        if want is None:
            continue
        mine = _mine(key)
        if str(want) != str(mine):
            return False, (f"{key} 不一致（参考 {want} / 当前 {mine}）"
                           f"⇒ 跳过 digest 逐位比对")
    return True, ""

# 默认条目：快条目几十秒内跑完，慢条目是三个既有世界的完整验收。
ENTRIES = [
    {"preset": "emergent", "seed": 0, "frames": 1500, "slow": False},
    {"preset": "plot", "seed": 0, "frames": 3000, "slow": False},
    {"preset": "nullify", "seed": 0, "frames": 3000, "slow": False},
    {"preset": "tide", "seed": 0, "frames": 6000, "slow": False},
    {"preset": "plot", "seed": 7, "frames": 3000, "slow": False},
    {"preset": "destruction", "seed": 0, "frames": 8000, "slow": False},  # R3 后接管「毁灭」演示位
    {"preset": "plot", "seed": 0, "frames": None, "slow": True},     # 全量
    {"preset": "nullify", "seed": 0, "frames": None, "slow": True},  # 全量
]


def fingerprint(preset, seed, frames):
    """跑一次并压成指纹。只读 —— 不写回任何 data/ 文件。"""
    data = DataSet(ROOT, preset=preset)
    ctx = Config(ROOT, lex_overlay=data.preset.get("lexicon"))
    traj = run(ctx, data, seed=int(seed), rules=evaluate,
               runtime=default_services(),
               max_frames=None if frames is None else int(frames))
    st = traj.final
    return {
        "preset": preset,
        "seed": int(seed),
        "frames": frames,
        "verdict": traj.verdict,
        "conclusion": traj.conclusion["id"],
        "stop_reason": traj.stop_reason,
        "reached_frame": int(traj.reached_frame),
        "iterations": int(traj.iterations),
        "skipped_frames": int(traj.skipped_frames),
        "promotions": int(st.promotions),
        "personas": len(traj.personas),
        "entropy": round(float(st.entropy), 6),
        "noise": round(float(st.noise), 6),
        "population": len(st.pool),
        "destruction_events": int(st.destruction_events),
        "ascended": bool(traj.ascended),
        "seats": [s.owner for s in st.register.slots],
        "digest": st.digest(),
    }


def load_golden():
    if not os.path.exists(GOLDEN):
        return None
    with open(GOLDEN, encoding="utf-8") as f:
        return json.load(f)


def key_of(entry):
    return f"{entry['preset']}@{entry['seed']}@{entry['frames']}"


def compare(old, new, ref=None, structural_only=False):
    """按【字段分层】比对一份旧指纹与一份新指纹。返回 (diffs, notes)。

    结构层逐位严格；数值层按容差；digest 只在**参考环境**（见 `digest_comparable`：
    OS / CPU / Python / numpy 四项全同）上逐位比对。`structural_only` 强制只比结构层
    （最保守，供异平台 CI 用）。返回的 notes 说明本次【跳过了什么、为什么】。
    """
    diffs, notes = [], []
    for field in STRUCTURAL_FIELDS:
        a, b = old.get(field), new.get(field)
        if a != b:
            diffs.append((field, a, b))

    if structural_only:
        notes.append("结构层比对：已跳过数值层与 digest")
        return diffs, notes

    for field in NUMERIC_FIELDS:
        a, b = old.get(field), new.get(field)
        if not _close(a, b):
            diffs.append((field, a, b))

    ok, why = digest_comparable(ref)
    if not ok:
        notes.append(why)
    elif old.get(DIGEST_FIELD) != new.get(DIGEST_FIELD):
        diffs.append((DIGEST_FIELD, old.get(DIGEST_FIELD), new.get(DIGEST_FIELD)))
    return diffs, notes


def main():
    ap = argparse.ArgumentParser(description="轨迹指纹：单次核对 / 重写")
    ap.add_argument("--write", action="store_true", help="重算并写回指纹文件")
    ap.add_argument("--fast", action="store_true", help="只处理快条目")
    ap.add_argument("--structural", action="store_true",
                    help="只比对结构层（跳过数值层与 digest）—— 异平台 CI 用")
    args = ap.parse_args()

    golden = load_golden() or {"_comment": "轨迹指纹。重算：python tools/snapshot.py --write",
                               "entries": []}
    recorded = {key_of(e): e for e in golden.get("entries", [])}
    ref = None if args.structural else golden.get(REFERENCE_KEY)
    digest_ok = (not args.structural) and digest_comparable(ref)[0]

    wanted = [e for e in ENTRIES if not (args.fast and e["slow"])]
    out, failures = [], 0
    for spec in wanted:
        key = key_of(spec)
        t0 = time.time()
        new = fingerprint(spec["preset"], spec["seed"], spec["frames"])
        dt = time.time() - t0
        old = recorded.get(key)
        if args.write:
            new["slow"] = bool(spec["slow"])
            out.append(new)
            print(f"  [写入] {key:<28} {dt:>7.1f}s  digest {new['digest'][:16]}")
            continue
        if old is None:
            new["slow"] = bool(spec["slow"])
            out.append(new)
            print(f"  [新条目] {key:<26} {dt:>7.1f}s  digest {new['digest'][:16]}")
            continue
        diffs, notes = compare(old, new, ref, structural_only=args.structural)
        if diffs:
            failures += 1
            print(f"  [变了] {key:<28} {dt:>7.1f}s")
            for field, a, b in diffs:
                print(f"        {field}: {a!r} → {b!r}")
        else:
            tag = (f"  digest {new['digest'][:16]}" if digest_ok
                   else "（结构层 + 数值层；digest 已跳过）")
            print(f"  [一致] {key:<28} {dt:>7.1f}s{tag}")
        for nt in notes:
            print(f"        · {nt}")
        new["slow"] = bool(spec["slow"])
        out.append(new)

    if args.write:
        # 整体重写：本次覆盖的条目换成刚算出来的，其余旧条目原样留着。
        merged = {k: v for k, v in recorded.items()
                  if k not in {key_of(e) for e in out}}
        merged.update({key_of(e): e for e in out})
        golden["entries"] = [merged[k] for k in sorted(merged)]
        # 记下【参考平台】：digest 只在它上面逐位可比，异平台据此自动跳过。
        golden[REFERENCE_KEY] = _current_reference()
        with open(GOLDEN, "w", encoding="utf-8") as f:
            json.dump(golden, f, ensure_ascii=False, indent=1)
        print(f"\n  ✓ 指纹已写入 {GOLDEN}（{len(out)} 条）"
              f" · 参考平台 {golden[REFERENCE_KEY]['system']}")
        return 0

    if len(out) > len(recorded):
        merged = dict(recorded)
        merged.update({key_of(e): e for e in out})
        golden["entries"] = [merged[k] for k in sorted(merged)]
        with open(GOLDEN, "w", encoding="utf-8") as f:
            json.dump(golden, f, ensure_ascii=False, indent=1)
        print(f"\n  （新条目已补进 {GOLDEN}）")

    print()
    if failures:
        print(f"  ✗ 有 {failures} 个条目的轨迹变了。"
              f"若这是有意的（例如改了轨道配置），跑 --write 重写并同步更新期望值。")
        return 1
    print("  ✓ 指纹与记录一致")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
