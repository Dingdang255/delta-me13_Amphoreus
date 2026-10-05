"""逐火点名录（`tools/roll_call.py`）—— 个体史账本的第一个消费者。

它把「席位级的机制」讲成一张「有人死、有人活的逐火史」。三条要求：

  ① **账本自洽**：登场 = 陨落 + 仍在；死因的分类计数与墓碑逐条对得上；
  ② **外生伤亡是可归因的**：逐出 / 让位单独成表，且"由谁"有明确的呈现口径；
  ③ **承位链连得上**：每个接手者的 `from` 都必须是墓碑里那个被夺席的人。
"""
from __future__ import annotations

import os
import sys
import unittest

from _support import ROOT, load

sys.path.insert(0, os.path.join(ROOT, "tools"))
import roll_call  # noqa: E402


class RollCallData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx, cls.data, cls.traj = load("plot", frames=3000, seed=0)
        cls.blob = roll_call.collect(cls.traj, cls.ctx)

    def test_ledger_adds_up(self):
        self.assertEqual(self.blob["born"],
                         self.blob["died"] + self.blob["alive"])
        self.assertEqual(self.blob["died"],
                         sum(self.blob["causes"].values()))

    def test_cause_buckets_match_the_stones(self):
        """分类计数必须与墓碑逐条对得上 —— 不许两处口径漂。"""
        for cause, n in self.blob["causes"].items():
            rows = [r for r in self.blob["stones"] if r[3] == cause]
            self.assertEqual(len(rows), n, cause)

    def test_every_cause_has_a_label(self):
        for cause in self.blob["causes"]:
            self.assertIn(cause, roll_call.CAUSE_LABELS)

    def test_lineage_points_at_the_dethroned(self):
        dethroned = {r[1] for r in self.blob["dethroned"]}
        self.assertTrue(self.blob["lineage"])
        for heir, src in self.blob["lineage"]:
            self.assertIn(src, dethroned, f"{heir} 说它接自 {src}")
            self.assertIn(heir, self.blob["factor_of"])

    def test_external_bucket_only_holds_external_causes(self):
        self.assertTrue(all(r[3] in roll_call.EXTERNAL
                            for r in self.blob["external"]))


class Attribution(unittest.TestCase):
    def test_unattributed_external_is_marked(self):
        self.assertEqual(roll_call._by_text("evicted", None), "（外生·未记名）")

    def test_named_actor_wins(self):
        self.assertEqual(roll_call._by_text("evicted", "hacker"), "hacker")

    def test_environmental_death_has_no_attribution(self):
        self.assertEqual(roll_call._by_text("aged", None), "—")


class Report(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx, cls.data, cls.traj = load("plot", frames=3000, seed=0)
        cls.blob = roll_call.collect(cls.traj, cls.ctx)
        cls.text = roll_call.build_report(cls.ctx, cls.data, cls.traj, cls.blob)

    def test_has_three_sections(self):
        for marker in ("逐火点名录", "【一】总账", "【二】外生干预",
                       "【三】承位链"):
            self.assertIn(marker, self.text)

    def test_is_deterministic(self):
        again = roll_call.build_report(self.ctx, self.data, self.traj, self.blob)
        self.assertEqual(self.text, again)


if __name__ == "__main__":
    unittest.main()