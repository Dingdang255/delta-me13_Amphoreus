"""轮内配额：涌现 / 接掌在一轮之内有上限，轮末再创世时结算清零。

这条把「涌现不是每帧自动刷新」钉成回归：
  · 一轮内涌现人数 ≤ round_emergence_quota；
  · 一轮内 OCCUPY 的接掌次数 ≤ round_succession_quota；
  · PROMOTION 真正 +1 轮时两个计数清零；
  · 同一 seed 两次跑逐位一致（配额只读现成状态、不掷骰子）；
  · 配额为 0 时这一轮不再涌现（3.0 之后「只剩既定十二人」靠的就是它）。
"""
from __future__ import annotations

import unittest

import kernel.emergence as emergence_mod
import kernel.operators as operators

from _support import ROOT, load

from apps.conditions import evaluate
from apps.services import default as default_services
from kernel.core import run
from kernel.loader import Config, DataSet

FRAMES = 900


class _Spy:
    """记录每个轮次里涌现 / 接掌各自用掉多少 —— 只读，不改变任何行为。"""

    def __init__(self):
        self.emerged = {}
        self.successions = {}
        self.resets = []
        self._orig = {}

    def __enter__(self):
        orig_scan = emergence_mod.EmergenceRegistrar.scan
        orig_occ = operators.Occupy.apply
        orig_prom = operators.Promotion.apply

        def scan(self_, st, frame):
            out = orig_scan(self_, st, frame)
            if out:
                self.emerged[int(st.round)] = self.emerged.get(int(st.round), 0) + len(out)
            return out

        def occupy(self_, st, ctx, rng, frame):
            r = orig_occ(self_, st, ctx, rng, frame)
            rnd = int(st.round)
            self.successions[rnd] = max(self.successions.get(rnd, 0),
                                        int(st.round_successions))
            return r

        def promotion(self_, st, ctx, rng, frame):
            before = int(st.round)
            r = orig_prom(self_, st, ctx, rng, frame)
            if int(st.round) != before:
                self.resets.append((int(st.round),
                                    int(st.round_emergence),
                                    int(st.round_successions)))
            return r

        self._orig = (orig_scan, orig_occ, orig_prom)
        emergence_mod.EmergenceRegistrar.scan = scan
        operators.Occupy.apply = occupy
        operators.Promotion.apply = promotion
        return self

    def __exit__(self, *exc):
        (emergence_mod.EmergenceRegistrar.scan,
         operators.Occupy.apply,
         operators.Promotion.apply) = self._orig
        return False


class RoundQuota(unittest.TestCase):
    def test_emergence_and_succession_stay_within_quota(self):
        with _Spy() as spy:
            ctx, _data, traj = load("plot", frames=FRAMES)
        e_quota = int(ctx.params["round_emergence_quota"])
        s_quota = int(ctx.params["round_succession_quota"])

        self.assertTrue(spy.emerged, "这段时间里应当至少发生一次涌现")
        for rnd, n in spy.emerged.items():
            self.assertLessEqual(n, e_quota,
                                 f"第 {rnd} 轮涌现 {n} 人，超过配额 {e_quota}")
        for rnd, n in spy.successions.items():
            self.assertLessEqual(n, s_quota,
                                 f"第 {rnd} 轮接掌 {n} 次，超过配额 {s_quota}")
        self.assertEqual(max(spy.emerged.values()), e_quota,
                         "配额应当真的被用满，否则这条测试没有覆盖上限")

    def test_promotion_clears_round_counters(self):
        with _Spy() as spy:
            _ctx, _data, traj = load("plot", frames=FRAMES)
        self.assertGreaterEqual(traj.final.promotions, 1, "窗口内该至少换代一次")
        self.assertTrue(spy.resets, "没有观察到任何一次轮末结算")
        for rnd, emerged, successions in spy.resets:
            self.assertEqual((emerged, successions), (0, 0),
                             f"第 {rnd} 轮开始后计数没有清零：{emerged}/{successions}")

    def test_same_seed_is_reproducible(self):
        _c1, _d1, a = load("plot", frames=FRAMES)
        _c2, _d2, b = load("plot", frames=FRAMES)
        self.assertEqual(a.final.digest(), b.final.digest())
        self.assertEqual(a.reached_frame, b.reached_frame)
        self.assertEqual(len(a.personas), len(b.personas))

    def test_zero_quota_halts_emergence(self):
        data = DataSet(ROOT, preset="plot")
        ctx = Config(ROOT, lex_overlay=data.preset.get("lexicon"))
        ctx.params["round_emergence_quota"] = 0
        traj = run(ctx, data, seed=0, max_frames=FRAMES, rules=evaluate,
                   runtime=default_services())
        self.assertEqual(len(traj.personas), 0,
                         "涌现配额为 0 时该轮不该再登记任何角色")
        self.assertGreaterEqual(traj.final.promotions, 1,
                                "接掌配额仍为正，席位动力学不该被一起按死")


if __name__ == "__main__":
    unittest.main()
