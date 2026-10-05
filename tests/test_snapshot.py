"""轨迹指纹（E1）：改动引擎后，单测这一层就能发现世界有没有被挪动。

`tools/snapshot.py --write` 生成 `tests/golden_fingerprints.json`。这里只核对
**快条目**（显式给了帧数的那些）—— 全量条目要跑满三千多万帧，属 `--full` 的事。

字段分层与比对口径**全部复用 `tools/snapshot.py`**（结构层逐位严格、数值层走容差、
digest 只在**参考环境**——OS / CPU 架构 / Python / numpy 四项全同——上比对）——
本文件不再各抄一份，免得扩字段时两边漂移。
"""
from __future__ import annotations

import json
import os
import sys
import unittest

from _support import ROOT

sys.path.insert(0, os.path.join(ROOT, "tools"))
from snapshot import compare, fingerprint               # noqa: E402

GOLDEN = os.path.join(ROOT, "tests", "golden_fingerprints.json")


class TrajectoryFingerprint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.path.exists(GOLDEN):
            raise unittest.SkipTest(
                "还没有轨迹指纹文件；先跑 python tools/snapshot.py --write")
        with open(GOLDEN, encoding="utf-8") as f:
            blob = json.load(f)
        cls.ref = blob.get("_reference_platform")
        cls.entries = [e for e in blob["entries"] if not e.get("slow")]

    def test_at_least_one_entry(self):
        self.assertTrue(self.entries, "指纹文件里没有快条目")

    def test_fingerprints_match(self):
        for e in self.entries:
            key = f"{e['preset']}@{e['seed']}@{e['frames']}"
            with self.subTest(entry=key):
                got = fingerprint(e["preset"], e["seed"], e["frames"])
                diffs, _notes = compare(e, got, self.ref)
                self.assertEqual(diffs, [], (
                    f"{key} 的轨迹变了：{diffs}\n"
                    f"  若这是有意的（改了轨道配置 / 预设），"
                    f"跑 `python tools/snapshot.py --write` 重写指纹并同步期望值。"))


class CompareLayers(unittest.TestCase):
    """`tools/snapshot.py::compare` 自身的分层口径（结构层 / 数值层 / 摘要层）。

    纯函数、不跑演算 —— 直接喂合成指纹，钉住「哪一层该报、哪一层该跳」。
    """

    #: 一个必然与本机不同的参考平台 ⇒ digest 应被跳过（不误报）。
    FOREIGN = {"system": "NotThisOS", "machine": "x", "python": "0", "numpy": "0"}

    @staticmethod
    def _pair():
        return ({"verdict": "a", "entropy": 1.0, "digest": "d"},
                {"verdict": "a", "entropy": 1.0, "digest": "d"})

    def test_structural_diff_detected(self):
        old, new = self._pair()
        new["verdict"] = "b"
        diffs, _ = compare(old, new, self.FOREIGN)
        self.assertEqual([f for f, _a, _b in diffs], ["verdict"])

    def test_numeric_within_tolerance_not_reported(self):
        old, new = self._pair()
        new["entropy"] = 1.0 + 1e-9
        diffs, _ = compare(old, new, self.FOREIGN)
        self.assertEqual(diffs, [])

    def test_structural_only_skips_numeric_and_digest(self):
        old, new = self._pair()
        new["entropy"], new["digest"] = 9.0, "zzz"
        diffs, notes = compare(old, new, self.FOREIGN, structural_only=True)
        self.assertEqual(diffs, [])
        self.assertTrue(notes, "只比结构层时应给出「跳过了什么」的说明")

    def test_digest_skipped_on_foreign_platform(self):
        old, new = self._pair()
        new["digest"] = "zzz"                     # 异平台：不该因此报差异
        diffs, notes = compare(old, new, self.FOREIGN)
        self.assertEqual(diffs, [])
        self.assertTrue(notes)


if __name__ == "__main__":
    unittest.main()
