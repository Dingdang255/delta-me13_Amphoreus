"""机制对照工具（`tools/mech_control.py`）—— **变体造得对不对，比结论更重要**。

这个工具初版栽过一次，而且栽得很隐蔽：变体从【基准】预设取事件表，可那 7 条投递
只存在于【机制】预设里 —— 于是一条都换不到，跑出来的"噪声组"其实**就是基准**
（三组读数与基准逐位相同），它却还兴高采烈地报"机制组落在噪声区间之外 ⇒ 结构性"。
一张完全空转的表，配上一条完全错误的结论。

故本文件的重点不是"对照跑出来什么"，而是**变体真的被改过**：换到几条、换成什么、
换不到时会不会当场炸。全部不跑引擎，快。
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

from _support import ROOT

sys.path.insert(0, os.path.join(ROOT, "tools"))
import mech_control  # noqa: E402
from _harness import jsonl  # noqa: E402

#: 剧情版占用的席位（由 plot-mech 的 events.jsonl 实测而来）。
STORY_SEATS = {1, 7, 8, 9, 10}


def _events(preset):
    return jsonl(os.path.join(ROOT, "presets", preset, "events.jsonl"))


class VariantConstruction(unittest.TestCase):
    """造变体：这是唯一会静默出错的地方。"""

    @classmethod
    def setUpClass(cls):
        cls.records = mech_control.varied_records(_events("plot"), _events("plot-mech"))
        cls.vary = [r for r in cls.records if r.get("selector")]

    def test_finds_exactly_the_upgraded_deliveries(self):
        """7 条真机制投递（不绑具体能力名 —— 手段可以是逐出、也可以是交涉）。"""
        self.assertEqual(len(self.records), 7)
        self.assertTrue(all(r.get("capability") != "emit" for r in self.records))
        self.assertEqual(len(self.vary), 7)

    def test_story_seats_are_what_the_preset_uses(self):
        self.assertEqual(mech_control.story_seats(self.records), STORY_SEATS)

    def test_noise_pool_excludes_story_seats(self):
        pool = [i for i in range(12) if i not in STORY_SEATS]
        self.assertEqual(pool, [0, 2, 3, 4, 5, 6, 11])

    def test_noise_plan_is_deterministic_and_off_story(self):
        pool = [0, 2, 3, 4, 5, 6, 11]
        a = mech_control.noise_plan(self.vary, pool, 0, 12)
        b = mech_control.noise_plan(self.vary, pool, 0, 12)
        self.assertEqual(a, b)
        self.assertEqual(len(a), len(self.vary))
        self.assertTrue(set(a) <= set(pool))
        self.assertEqual(set(a) & STORY_SEATS, set())
        # 各组互不相同（否则"三组噪声"其实是同一组）
        plans = [tuple(mech_control.noise_plan(self.vary, pool, v, 12))
                 for v in range(3)]
        self.assertEqual(len(set(plans)), 3)

    def test_write_variant_really_rewrites_the_selectors(self):
        """换完必须读回来核对 —— 初版 bug 正是"以为换了、其实没换"。"""
        pool = [0, 2, 3, 4, 5, 6, 11]
        plan = mech_control.noise_plan(self.vary, pool, 0, 12)
        with tempfile.TemporaryDirectory() as tmp:
            used = mech_control.write_variant(tmp, "v", "plot-mech", self.vary, plan)
            self.assertEqual(used, len(self.vary))
            written = jsonl(
                os.path.join(tmp, "presets", "v", "events.jsonl"))
        # 只数【选择器真的被换掉】的那些 —— 机制预设里另外几条（封印 / 接掌）本就不该被换
        origin = jsonl(
            os.path.join(ROOT, "presets", "plot-mech", "events.jsonl"))
        got = [int(r["selector"]["expr"].split(":", 1)[1])
               for r, o in zip(written, origin)
               if r.get("selector") and r["selector"] != o.get("selector")]
        self.assertEqual(got, plan)
        # 与原始选择器不同 —— 否则这次"变体"就是原样复制
        self.assertNotEqual(got, [int(r["selector"]["expr"].split(":", 1)[1])
                                  for r in self.vary])

    def test_write_variant_refuses_a_silent_no_op(self):
        """换不到就当场报错 —— 绝不静默出一张等于基准的假表。"""
        ghost = [{"frame": 1, "capability": "evict_holder",
                  "selector": {"expr": "order:0"}, "payload": {}}]
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                mech_control.write_variant(tmp, "v", "plot-mech", ghost, [0])

    def test_varied_records_is_empty_for_identical_presets(self):
        """同一个预设自己跟自己比 —— 没有"多出来的投递"，工具应当拒跑。"""
        self.assertEqual(
            mech_control.varied_records(_events("plot"), _events("plot")), [])


if __name__ == "__main__":
    unittest.main()