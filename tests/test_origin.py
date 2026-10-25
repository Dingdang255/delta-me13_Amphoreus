"""原初目标只读探针（`apps/origin.py`）：自我度、采样、闭合、反事实、只读。

探针是纯观测：这里用假 `st` / 假 `traj` 验数值与枚举，不跑长演算。
"""
from __future__ import annotations

import json
import os
import types
import unittest

import numpy as np

from _support import ROOT      # noqa: F401  （挂 sys.path + 钉 BLAS 线程）

from apps.origin import DEFAULTS, OriginProbe, render, selfhood


def _slot(vec, filled=True):
    return types.SimpleNamespace(filled=lambda: filled,
                                 vector=np.asarray(vec, dtype=np.float32))


def _st(vectors, empty=()):
    """造一个只有寄存器与账本读数的假状态。`empty` 是额外空置的席位数。"""
    slots = [_slot(v) for v in vectors] + [_slot([0.0], filled=False) for _ in empty]
    return types.SimpleNamespace(register=types.SimpleNamespace(slots=slots),
                                 score={},
                                 memory_bank=np.zeros((0, 12), dtype=np.float32))


def _final(rows=0, repaired=0.0, override=None):
    return types.SimpleNamespace(
        memory_bank=np.zeros((rows, 12), dtype=np.float32),
        score={"memory_repaired": repaired} if repaired else {},
        conclusion_override=override)


def _traj(verdict="undecided", reached=0, rows=0, repaired=0.0, override=None):
    return types.SimpleNamespace(verdict=verdict, reached_frame=reached,
                                 final=_final(rows, repaired, override))


class SelfhoodTest(unittest.TestCase):
    def test_same_vectors_are_about_one(self):
        st = _st([[1.0, 2.0, 3.0]] * 3)
        self.assertAlmostEqual(selfhood(st), 1.0, places=5)

    def test_orthogonal_axes_balance_to_zero(self):
        # 指标是「各席与均值向量」的余弦：两条正交轴各取正反，均值向量为零，
        # 余弦分子随之归零（分母为 0 时按 1 处理）⇒ 0.0。
        st = _st([[1.0, 0.0], [-1.0, 0.0], [0.0, 1.0], [0.0, -1.0]])
        self.assertAlmostEqual(selfhood(st), 0.0, places=5)

    def test_opposite_vectors_cancel(self):
        st = _st([[1.0, 0.0], [-1.0, 0.0]])
        self.assertAlmostEqual(selfhood(st), 0.0, places=5)

    def test_fewer_than_two_filled_is_zero(self):
        self.assertEqual(selfhood(_st([[1.0, 0.0]])), 0.0)
        self.assertEqual(selfhood(_st([])), 0.0)
        self.assertEqual(selfhood(_st([[1.0, 0.0]], empty=[1, 2])), 0.0)

    def test_zero_norm_is_safe(self):
        st = _st([[0.0, 0.0], [0.0, 0.0]])
        self.assertEqual(selfhood(st), 0.0)


class SamplingTest(unittest.TestCase):
    def test_default_samples_every_visited_frame(self):
        probe = OriginProbe()
        st = _st([[1.0, 0.0, 0.0]] * 3)
        for frame in range(5):
            self.assertIs(probe(frame, st, None), True)
        self.assertEqual(probe.summary(_traj())["selfhood_samples"], 5)
        self.assertEqual(probe._frames, {0, 1, 2, 3, 4})

    def test_period_two_samples_zero_two_four(self):
        probe = OriginProbe(period=2)
        st = _st([[1.0, 0.0, 0.0]] * 3)
        for frame in range(5):
            self.assertIs(probe(frame, st, None), True)
        self.assertEqual(probe.summary(_traj())["selfhood_samples"], 3)
        self.assertEqual(probe._frames, {0, 2, 4})

    def test_first_frame_always_sampled(self):
        probe = OriginProbe(period=256)
        st = _st([[1.0, 0.0, 0.0]] * 3)
        probe(3, st, None)
        probe(4, st, None)
        self.assertEqual(probe.summary(_traj())["selfhood_samples"], 1)

    def test_close_adds_last_frame_once(self):
        probe = OriginProbe(period=2)
        st = _st([[1.0, 0.0, 0.0]] * 3)
        for frame in (0, 2):
            probe(frame, st, None)
        traj = _traj(reached=5, rows=0)
        traj.final = st
        probe.close(traj)
        probe.close(traj)
        self.assertEqual(probe.summary(traj)["selfhood_samples"], 3)
        self.assertIn(5, probe._frames)

    def test_close_skips_already_sampled_last_frame(self):
        probe = OriginProbe(period=1)
        st = _st([[1.0, 0.0, 0.0]] * 3)
        for frame in range(5):
            probe(frame, st, None)
        traj = _traj(reached=4)
        traj.final = st
        probe.close(traj)
        self.assertEqual(probe.summary(traj)["selfhood_samples"], 5)

    def test_peak_and_peak_frame(self):
        probe = OriginProbe(period=1)
        probe(0, _st([[1.0, 0.0], [0.0, 1.0]]), None)    # 0.0
        probe(1, _st([[1.0, 2.0]] * 3), None)           # 1.0
        probe(2, _st([[1.0, 0.0], [1.0, 0.0]]), None)   # 1.0
        out = probe.summary(_traj())
        self.assertAlmostEqual(out["selfhood_peak"], 1.0, places=5)
        self.assertEqual(out["selfhood_peak_frame"], 1)

    def test_no_samples_summarises_to_zero(self):
        out = OriginProbe().summary(_traj())
        self.assertEqual(out["selfhood_mean"], 0.0)
        self.assertEqual(out["selfhood_peak"], 0.0)
        self.assertEqual(out["selfhood_samples"], 0)


class SummaryTest(unittest.TestCase):
    def test_memory_empty(self):
        out = OriginProbe().summary(_traj(rows=0, repaired=0.0))
        self.assertEqual(out["memory_rows"], 0)
        self.assertEqual(out["memory_repaired"], 0)
        self.assertEqual(out["closure"], "empty")

    def test_memory_closed_by_rows(self):
        self.assertEqual(OriginProbe().summary(_traj(rows=3))["closure"], "closed")

    def test_memory_closed_by_repaired(self):
        out = OriginProbe().summary(_traj(rows=0, repaired=2.0))
        self.assertEqual(out["memory_repaired"], 2)
        self.assertEqual(out["closure"], "closed")

    def test_counterfactual_destruction(self):
        self.assertEqual(OriginProbe().summary(_traj(verdict="destruction"))
                         ["counterfactual"], "destruction")

    def test_counterfactual_overwritten_by_verdict(self):
        self.assertEqual(OriginProbe().summary(_traj(verdict="overwritten"))
                         ["counterfactual"], "overwritten")

    def test_counterfactual_overwritten_by_override(self):
        out = OriginProbe().summary(_traj(verdict="destruction", override="overwritten"))
        self.assertEqual(out["counterfactual"], "overwritten")

    def test_counterfactual_undecided(self):
        self.assertEqual(OriginProbe().summary(_traj(verdict="undecided"))
                         ["counterfactual"], "undecided")


class ReadOnlyTest(unittest.TestCase):
    def test_call_is_always_true_and_writes_nothing(self):
        st = _st([[1.0, 2.0]] * 2)
        st.score["memory_repaired"] = 1.0
        st.memory_bank = np.zeros((2, 12), dtype=np.float32)
        score = json.dumps(st.score, sort_keys=True)
        bank = st.memory_bank.copy()
        probe = OriginProbe(period=1)
        for frame in range(6):
            self.assertIs(probe(frame, st, None), True)
        self.assertEqual(json.dumps(st.score, sort_keys=True), score)
        np.testing.assert_array_equal(st.memory_bank, bank)

    def test_summary_does_not_write_traj(self):
        traj = _traj(verdict="destruction", reached=9, rows=1, repaired=1.0)
        score = json.dumps(traj.final.score, sort_keys=True)
        OriginProbe().summary(traj)
        self.assertEqual(json.dumps(traj.final.score, sort_keys=True), score)
        self.assertEqual(traj.verdict, "destruction")


class RenderTest(unittest.TestCase):
    SUMMARY = {
        "selfhood_mean": 0.5,
        "selfhood_peak": 0.75,
        "selfhood_peak_frame": 12,
        "selfhood_samples": 4,
        "memory_rows": 2,
        "memory_repaired": 1,
        "closure": "closed",
        "counterfactual": "destruction",
    }

    def test_defaults_without_lexicon(self):
        lines = render(self.SUMMARY, None)
        self.assertEqual(len(lines), 3)
        for line in lines:
            self.assertTrue(line.startswith("  "))
        self.assertIn(DEFAULTS["selfhood"], lines[0])
        self.assertIn("均值 0.5000", lines[0])
        self.assertIn("峰值 0.7500 @ 帧 12", lines[0])
        self.assertIn("采样 4 次", lines[0])
        self.assertIn(DEFAULTS["closed"], lines[1])
        self.assertIn("缓冲区 2 行 · 再造 1 席", lines[1])
        self.assertIn(DEFAULTS["destruction"], lines[2])

    def test_lexicon_words_are_used(self):
        lex = {"origin": {
            "title": "T", "selfhood": "S", "memory": "M", "counterfactual": "C",
            "closed": "CL", "empty": "EM", "destruction": "DE",
            "overwritten": "OV", "undecided": "UN",
        }}
        lines = render(dict(self.SUMMARY, counterfactual="overwritten"), lex)
        self.assertIn("S", lines[0])
        self.assertIn("M", lines[1])
        self.assertIn("CL", lines[1])
        self.assertIn("C", lines[2])
        self.assertIn("OV", lines[2])

    def test_empty_branch_uses_empty_word(self):
        lines = render(dict(self.SUMMARY, closure="empty", counterfactual="undecided"),
                       {"origin": {"empty": "EM", "undecided": "UN"}})
        self.assertIn("EM", lines[1])
        self.assertIn("UN", lines[2])


class ConfigGuardTest(unittest.TestCase):
    def test_dim_is_still_twelve(self):
        with open(os.path.join(ROOT, "config", "params.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["dim"], 12)

    def test_loci_are_still_twelve(self):
        with open(os.path.join(ROOT, "config", "loci.json"), encoding="utf-8") as f:
            self.assertEqual(len(json.load(f)["loci"]), 12)


if __name__ == "__main__":
    unittest.main()
