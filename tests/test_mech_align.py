"""锚定对齐表（`tools/mech_align.py`）—— 口径对了，这张表才有用。

这个工具的价值全在口径上，而它的两个坑我都亲身踩过：

  ① 「谁坐在这一席」必须按 `register.slots[i].owner` 算 —— 逐出 / 接掌这类**机制看的正是
     这个字段**（压制只把位封住，不清 owner）。用渲染层"有没有人在位"那套口径会得出另一张表。
  ② `bind_participant` **不作用在在位者身上** —— 它把指定的场外参与者放上席（顺带让现任让位）。
     初版按"在位者是否点名角色"判，于是把 plot 那条「丹恒接住大地权能」误判成"错位"
     （那一刻在位的是无名个体 26443，而机制真正装上去的是场外参与者 -3 = 丹恒）。

本文件盯住这两条，外加"对齐判定真的区分得开"。全部不跑引擎。
"""
from __future__ import annotations

import os
import sys
import unittest

from _support import ROOT

sys.path.insert(0, os.path.join(ROOT, "tools"))
import mech_align  # noqa: E402


def _anchors():
    return {24997: {"hanzi": "昔涟", "key": "serial:24997"},
            -3: {"hanzi": "丹恒·腾荒", "key": "serial:-3", "external": True},
            26359: {"hanzi": "阿那克萨戈拉斯", "key": "serial:26359"}}


class OwnerAt(unittest.TestCase):
    """① 在位者口径：段是 [start, end) 半开区间。"""

    SPANS = [[{"start": 100, "end": 200, "serial": 7},
              {"start": 300, "end": None, "serial": 9}]]

    def test_inside_a_closed_span(self):
        self.assertEqual(mech_align.owner_at(self.SPANS, 0, 100), 7)
        self.assertEqual(mech_align.owner_at(self.SPANS, 0, 199), 7)

    def test_end_is_exclusive(self):
        """`end` 那一帧已经换人了 —— 半开区间，不含右端。"""
        self.assertIsNone(mech_align.owner_at(self.SPANS, 0, 200))

    def test_gap_and_open_tail(self):
        self.assertIsNone(mech_align.owner_at(self.SPANS, 0, 250))
        self.assertEqual(mech_align.owner_at(self.SPANS, 0, 99999), 9)

    def test_before_anything(self):
        self.assertIsNone(mech_align.owner_at(self.SPANS, 0, 0))


class Names(unittest.TestCase):
    def test_named_and_unnamed(self):
        a = _anchors()
        self.assertIn("昔涟", mech_align.name_of(a, 24997))
        self.assertIn("场外", mech_align.name_of(a, -3))
        self.assertIn("serial:5102", mech_align.name_of(a, 5102))


class RealPresets(unittest.TestCase):
    """真配置上跑：锚定条目、剧本里的机制投递。不跑引擎。"""

    @classmethod
    def setUpClass(cls):
        cls.anchors = mech_align.anchors_of(ROOT, "plot")

    def test_anchors_carry_serials(self):
        self.assertIn(24997, self.anchors)          # 昔涟
        self.assertIn(26632, self.anchors)          # 阿那克萨戈拉斯（L07 本届）
        self.assertIn(-2, self.anchors)             # 开拓者（场外）

    def test_mechanisms_of_finds_plot_mech_deliveries(self):
        recs = mech_align.mechanisms_of(ROOT, "plot-mech")
        caps = [r.get("capability") for r in recs]
        # 全部真机制 = plot 原有的 3 条（1 封印 + 2 接掌）+ 本预设升级的 7 条
        # （6 条暴力逐出 + 1 条交涉归还）。不绑死能力名，只钉住"手段不止一种"。
        self.assertEqual(len(recs), 10)
        self.assertEqual(caps.count("evict_holder"), 6)
        self.assertEqual(caps.count("parley"), 1)
        self.assertEqual(caps.count("suppress_slot"), 1)
        self.assertEqual(caps.count("bind_participant"), 2)
        # emit 是镜头，不该进来
        self.assertNotIn("emit", caps)

    def test_frames_are_sorted(self):
        frames = [int(r["frame"]) for r in mech_align.mechanisms_of(ROOT, "plot-mech")]
        self.assertEqual(frames, sorted(frames))


class AlignmentJudgement(unittest.TestCase):
    """② 判定：`evict_holder` 看在位者，`bind_participant` 看它装上去的那个人。

    直接测工具里的 `judge()` —— 不复制逻辑（复制出来的测试只能证明"副本自洽"）。
    """

    def setUp(self):
        self.a = _anchors()

    def test_evict_holder_judges_the_incumbent(self):
        who, ok = mech_align.judge(self.a, 24997, {})
        self.assertTrue(ok)
        self.assertIn("昔涟", who)

    def test_unnamed_incumbent_is_not_aligned(self):
        _who, ok = mech_align.judge(self.a, 5102, {})
        self.assertFalse(ok)

    def test_bind_participant_judges_the_installed_outsider(self):
        """在位者是无名个体，但装上去的是丹恒（-3）—— 这条必须算【对齐】。

        初版按在位者判，于是把 plot 自己的这条桥段误报成错位。
        """
        who, ok = mech_align.judge(self.a, 26443, {"participant": -3})
        self.assertTrue(ok)
        self.assertIn("丹恒", who)

    def test_bind_participant_to_an_unknown_outsider(self):
        _who, ok = mech_align.judge(self.a, 24997, {"participant": -999})
        self.assertFalse(ok)

    def test_empty_seat_is_not_aligned(self):
        who, ok = mech_align.judge(self.a, None, {})
        self.assertFalse(ok)
        self.assertEqual(who, "空席")


if __name__ == "__main__":
    unittest.main()