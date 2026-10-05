"""遗迹勘测（建议表 #2 遗迹标记 + #3 考古报告）—— 只读红线 + 档案正确性。

四条要求：
  ① 只读：挂了遗迹勘测，演算逐帧不变（与 Sampler / LiveStream 同性质）；
  ② 档案自洽：在位 + 空置 = 全程，且 `seated_at_end` 对上终局位表（含压制口径）；
  ③ 报告三段齐全（遗址总览 / 逐处遗迹 / 终局结论），逐席覆盖；
  ④ 可复现：同一组输入两次勘测，档案与报告逐字一致。
"""
from __future__ import annotations

import os
import sys
import unittest

from _support import ROOT, load, seat_name

sys.path.insert(0, os.path.join(ROOT, "tools"))
import excavation  # noqa: E402


class ExcavationIsReadOnly(unittest.TestCase):
    """红线：勘测是观察者，不是参与者 —— 挂了它，演算逐帧不变。"""

    def test_survey_does_not_change_trajectory(self):
        _ctx_a, _data_a, plain = load("plot", frames=600)
        ctx_b, data_b, _ = load("plot", frames=600)
        sv, watched = excavation.survey(ctx_b, data_b, seed=0, frames=600)

        self.assertEqual(plain.iterations, watched.iterations)
        self.assertEqual(plain.reached_frame, watched.reached_frame)
        self.assertEqual(plain.verdict, watched.verdict)
        self.assertEqual(plain.final.digest(), watched.final.digest())
        self.assertTrue(sv.archives())

    def test_observing_final_does_not_touch_state(self):
        ctx, _data, traj = load("plot", frames=600)
        sv = excavation.RuinSurvey([l.id for l in ctx.loci])
        before = traj.final.digest()
        sv.observe_final(traj).finalize(traj.reached_frame)
        self.assertEqual(traj.final.digest(), before)       # 只读：观测不碰状态


class ExcavationArchives(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx, cls.data, _ = load("plot", frames=2500)
        cls.sv, cls.traj = excavation.survey(cls.ctx, cls.data, seed=0, frames=2500)
        cls.archives = cls.sv.archives()
        cls.report = excavation.build_report(cls.ctx, cls.data, cls.traj, cls.archives)

    def test_one_archive_per_seat(self):
        self.assertEqual([a["locus_id"] for a in self.archives],
                         [l.id for l in self.ctx.loci])

    def test_tenure_and_vacancy_fill_the_whole_run(self):
        reach = self.traj.reached_frame + 1
        for a in self.archives:
            self.assertEqual(a["tenured"] + a["vacant_frames"], reach, a["locus_id"])
            self.assertGreaterEqual(a["changes"], max(0, len(a["carried"]) - 1))

    def test_seated_at_end_matches_final_register(self):
        """「有人坐」须与 `world_signature()` 同口径：被压制的位记作空。"""
        st = self.traj.final
        sup = set(getattr(st, "suppressed", ()) or ())
        for i, a in enumerate(self.archives):
            owner = getattr(st.register.slots[i], "owner", None)
            self.assertEqual(a["seated_at_end"], owner is not None and i not in sup,
                             a["locus_id"])

    def test_marks_are_objective(self):
        for a in self.archives:
            tags = excavation.marks_of(a, self.traj.reached_frame)
            if a["born"] is None:
                self.assertEqual(tags, ["never"])
                continue
            self.assertNotIn("never", tags)
            # 「终局空置」与「终局在位」互斥
            self.assertNotEqual("vacant_end" in tags, a["seated_at_end"])

    def test_report_has_three_sections(self):
        for marker in ("考古报告", "【一】遗址总览", "【二】逐处遗迹", "【三】终局结论"):
            self.assertIn(marker, self.report)

    def test_report_covers_every_seat(self):
        for a in self.archives:
            self.assertIn(seat_name(self.ctx, self.traj, a["locus_id"]), self.report)

    def test_report_is_deterministic(self):
        again = excavation.build_report(self.ctx, self.data, self.traj, self.archives)
        self.assertEqual(self.report, again)

    def test_survey_is_deterministic(self):
        a = excavation.survey(self.ctx, self.data, seed=0, frames=600)[0].archives()
        b = excavation.survey(self.ctx, self.data, seed=0, frames=600)[0].archives()
        self.assertEqual(a, b)

    def test_json_shape(self):
        marks = {a["locus_id"]: excavation.marks_of(a, self.traj.reached_frame)
                 for a in self.archives}
        blob = excavation.as_json(self.ctx, self.data, self.traj,
                                  self.archives, marks)
        self.assertEqual(blob["totals"]["seats"], len(self.ctx.loci))
        self.assertEqual(len(blob["ruins"]), len(self.ctx.loci))
        for row in blob["ruins"]:
            self.assertIn("marks", row)
            self.assertIn("seat", row)
            self.assertIsInstance(row["carried"], list)


if __name__ == "__main__":
    unittest.main()