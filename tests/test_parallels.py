"""平行世界对照（建议表 #4）—— 只读红线 + 对照页自洽。

三条要求：
  ① 只读：挂了「采样器 + 遗迹勘测」的组合观测器，演算逐帧不变（`digest` 逐位相同）；
  ② 对照数据自洽：曲线非空、遗迹与席位一一对应、涌现帧单调；
  ③ 对照页自包含（零外链）且把每个世界都摆进去了。
"""
from __future__ import annotations

import os
import sys
import unittest

from _support import ROOT, load

sys.path.insert(0, os.path.join(ROOT, "tools"))
import parallels  # noqa: E402


class ParallelsIsReadOnly(unittest.TestCase):
    """红线：对照只是旁观 —— 挂了观测器，演算必须逐帧不变。"""

    def test_collect_does_not_change_trajectory(self):
        _ctx, _data, plain = load("emergent", frames=60, seed=0)
        got = parallels.collect("emergent", 0, frames=60)
        self.assertEqual(got["digest"], plain.final.digest())
        self.assertEqual(got["verdict"], plain.verdict)
        self.assertEqual(got["reached_frame"], plain.reached_frame)
        self.assertEqual(got["iterations"], plain.iterations)
        self.assertEqual(got["personas"], len(plain.personas))

    def test_combined_watch_never_prunes(self):
        """组合观测器只汇总只读观测器 —— 必须恒返回 True（否则会截断世界）。"""
        seen = []

        class _Spy:
            def __call__(self, frame, st, traj):
                seen.append(int(frame))
                return True

        w = parallels._Watches(_Spy(), _Spy())
        class _St:  # 观测器不看状态，给个占位就行
            pass
        self.assertTrue(w(7, _St(), None))
        self.assertEqual(seen, [7, 7])


class ParallelsData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.worlds = [parallels.collect("emergent", s, frames=60) for s in (0, 1)]

    def test_shape_of_each_world(self):
        for w in self.worlds:
            self.assertTrue(w["curve"], "曲线不该是空的")
            self.assertEqual(len(w["ruins"]), len(w["seats"]))
            self.assertEqual(len(w["ruins"]), len(w["locus_ids"]))
            self.assertEqual(w["emergence"], sorted(w["emergence"]))
            self.assertIn(w["verdict"], (None, "proved", "refuted", "undecided",
                                         "destruction", "annihilation", "overwritten"))

    def test_curve_is_frame_ordered(self):
        for w in self.worlds:
            frames = [row[0] for row in w["curve"]]
            self.assertEqual(frames, sorted(frames))

    def test_collect_is_deterministic(self):
        a = parallels.collect("emergent", 0, frames=60)
        b = parallels.collect("emergent", 0, frames=60)
        self.assertEqual(a, b)

    def test_worlds_are_distinct_by_seed(self):
        """种子不同 ⇒ 世界不同（至少唤起结果不同）—— 否则「对照」没有对象。"""
        self.assertNotEqual(self.worlds[0]["digest"], self.worlds[1]["digest"])


class ParallelsHtml(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.worlds = [parallels.collect("emergent", s, frames=60) for s in (0, 1)]
        cls.html = parallels.render_html(cls.worlds, {"frames": 60, "fast": 0})

    def test_is_self_contained(self):
        for bad in ("http://", "https://", "<script"):
            self.assertNotIn(bad, self.html)

    def test_has_all_four_panels(self):
        for marker in ("对照表", "熵曲线", "黑潮强度", "遗迹分布", "涌现时序"):
            self.assertIn(marker, self.html)

    def test_every_world_is_shown(self):
        for w in self.worlds:
            self.assertIn(w["name"], self.html)

    def test_ruin_matrix_has_one_cell_per_seat(self):
        # 每行「世界名 + 每席一格」⇒ 格子数是 世界数 × 席位数
        seats = len(self.worlds[0]["seats"])
        self.assertEqual(
            self.html.count("rgba(127,208,255"), len(self.worlds) * seats)

    def test_charts_have_polylines(self):
        self.assertEqual(self.html.count("<polyline"),
                         len(self.worlds) * 2)      # 熵 + 黑潮 各一条

    def test_text_view_lists_worlds(self):
        text = parallels.render_text(self.worlds, {"frames": 60, "fast": 0})
        for w in self.worlds:
            self.assertIn(w["name"], text)


class ParallelsArgs(unittest.TestCase):
    def test_world_specs_take_priority(self):
        got = parallels.parse_worlds(["tide:3", "emergent:0"], "plot", [0, 1])
        self.assertEqual(got, [("tide", 3), ("emergent", 0)])

    def test_falls_back_to_preset_and_seeds(self):
        self.assertEqual(parallels.parse_worlds([], "plot", [4, 5]),
                         [("plot", 4), ("plot", 5)])

    def test_world_spec_without_seed_defaults_to_zero(self):
        self.assertEqual(parallels.parse_worlds(["tide"], "plot", []), [("tide", 0)])

    def test_seed_ranges(self):
        self.assertEqual(parallels.resolve_seeds("2:3"), [2, 3, 4])
        self.assertEqual(parallels.resolve_seeds("1,7"), [1, 7])


if __name__ == "__main__":
    unittest.main()