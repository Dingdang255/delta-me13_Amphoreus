"""黑潮爆发探测（建议表 #5）—— 只读红线 + 判据数学 + 报告形态。

四条要求：
  ① 只读：挂了黑潮勘测，演算逐帧不变（`digest` 逐位相同）；
  ② 区域取自结构：`couplings > 0` 的连通分量，12 位正好切成 4 簇 × 3 区；
  ③ 判据是【真判据】：合成序列喂进去，该命中的命中、该挡的挡住（含「簇内不足半数」这条）；
  ④ 报告与 JSON 自洽。
"""
from __future__ import annotations

import os
import sys
import unittest

from _support import ROOT, load

from engine.render import renderer_for

sys.path.insert(0, os.path.join(ROOT, "tools"))
import blacktide  # noqa: E402

CLUSTERS = [[0, 1, 2], [3, 4, 5], [6, 7, 8], [9, 10, 11]]


def _norm(vals):
    total = sum(vals)
    return tuple(v / total for v in vals)


def _survey(series):
    sv = blacktide.TideSurvey()
    sv.series = list(series)
    return sv


def _series(base_shares, post_shares, n=200, at=128, ent=(1.0, 0.9)):
    """前 `at` 帧用 base_shares，之后用 post_shares；熵同步从 ent[0] 掉到 ent[1]。"""
    out = []
    for f in range(n):
        out.append((f, base_shares if f < at else post_shares,
                    ent[0] if f < at else ent[1], 0.0))
    return out


BASE = _norm([0.35, 0.10, 0.10] + [0.05] * 9)
COHERENT = _norm([0.02, 0.02, 0.02] + [0.10444] * 9)
INCOHERENT = _norm([0.15, 0.10, 0.10] + [0.05 + 0.2 / 9] * 9)


class TideIsReadOnly(unittest.TestCase):
    """红线：勘测是观察者 —— 挂了它，演算必须逐帧不变。"""

    def test_survey_does_not_change_trajectory(self):
        _ctx, _data, plain = load("tide", frames=300, seed=0)
        ctx, data, _ = load("tide", frames=300, seed=0)
        sv, watched = blacktide.survey_run(ctx, data, seed=0, frames=300)
        self.assertEqual(plain.final.digest(), watched.final.digest())
        self.assertEqual(plain.verdict, watched.verdict)
        self.assertEqual(plain.reached_frame, watched.reached_frame)
        self.assertTrue(sv.series)

    def test_survey_returns_true_and_never_prunes(self):
        sv = blacktide.TideSurvey()
        _ctx, _data, traj = load("tide", frames=60, seed=0, watch=sv)
        self.assertNotEqual(traj.stop_reason, "PRUNED")
        self.assertFalse(traj.truncated)

    def test_decimation_keeps_series_bounded(self):
        """抽稀：点数触顶就隔点丢弃、步长翻倍 —— 内存封顶，形状还在。"""
        sv = blacktide.TideSurvey(cap=8)
        for f in range(64):
            sv(0, *_stub())
        self.assertLessEqual(len(sv.series), 8)
        self.assertGreater(sv.stride, 1)


def _stub():
    """给 `TideSurvey.__call__` 造一个最小的状态替身（只用到 loci / entropy / noise）。"""
    class _L:
        load = 1.0

    class _St:
        loci = [_L() for _ in range(12)]
        entropy = 1.0
        noise = 0.0
    return (_St(), None)


class TideClusters(unittest.TestCase):
    def test_real_config_splits_into_four_threes(self):
        ctx, _data, _ = load("tide", frames=30, seed=0)
        clusters = blacktide.clusters_of(ctx)
        self.assertEqual(len(clusters), 4)
        self.assertTrue(all(len(g) == 3 for g in clusters))
        flat = sorted(i for g in clusters for i in g)
        self.assertEqual(flat, list(range(len(ctx.loci))))

    def test_clusters_are_deterministic(self):
        ctx, _data, _ = load("tide", frames=30, seed=0)
        self.assertEqual(blacktide.clusters_of(ctx), blacktide.clusters_of(ctx))


class TideCriteria(unittest.TestCase):
    """判据数学：合成序列，不跑引擎。"""

    def test_flat_series_yields_nothing(self):
        sv = _survey(_series(BASE, BASE))
        self.assertEqual(blacktide.detect(sv, CLUSTERS), [])

    def test_coherent_cluster_collapse_is_detected(self):
        sv = _survey(_series(BASE, COHERENT))
        hits = blacktide.detect(sv, CLUSTERS)
        self.assertTrue(hits)
        self.assertEqual({h["cluster"] for h in hits}, {(0, 1, 2)})
        self.assertTrue(all(h["coherent"] for h in hits))
        segs = blacktide.merge(hits, gap=64)
        self.assertEqual(len(segs), 1)
        self.assertEqual(segs[0]["cluster"], (0, 1, 2))
        self.assertEqual(segs[0]["start"], 128)
        self.assertGreater(segs[0]["drop"], 0.15)

    def test_single_member_fall_is_rejected(self):
        """簇里只跌一个区 —— 那不是「黑潮吞掉整块区域」，必须挡住。

        且**放松跌幅阈值也救不回来**：一致性是独立的第二道闸，不是跌幅的附属。
        """
        sv = _survey(_series(BASE, INCOHERENT))
        self.assertEqual(blacktide.detect(sv, CLUSTERS), [])
        self.assertEqual(blacktide.detect(sv, CLUSTERS, drop_min=0.001), [])

    def test_rise_is_complementary_to_drop(self):
        """簇外升幅 ≈ 跌幅（份额守恒）—— 故它是读数，不是额外筛子。"""
        sv = _survey(_series(BASE, COHERENT))
        hit = blacktide.detect(sv, CLUSTERS)[0]
        self.assertAlmostEqual(hit["rise"], hit["drop"], places=6)

    def test_entropy_filter_blocks_rising_entropy(self):
        """全局熵在涨 ⇒ 世界没有变集中 ⇒ 不算爆发。"""
        sv = _survey(_series(BASE, COHERENT, ent=(0.9, 1.0)))
        self.assertEqual(blacktide.detect(sv, CLUSTERS), [])

    def test_threshold_is_a_real_knob(self):
        """跌幅阈值真的在筛：抬到实际跌幅之上就没有命中了。"""
        sv = _survey(_series(BASE, COHERENT))
        self.assertTrue(blacktide.detect(sv, CLUSTERS, drop_min=0.15))
        self.assertEqual(blacktide.detect(sv, CLUSTERS, drop_min=0.9), [])

    def test_merge_separates_different_clusters(self):
        hits = [{"frame": 10, "cluster": (0, 1, 2), "drop": 0.2, "rise": 0.2,
                 "entropy_drop": 0.1},
                {"frame": 12, "cluster": (3, 4, 5), "drop": 0.2, "rise": 0.2,
                 "entropy_drop": 0.1},
                {"frame": 14, "cluster": (0, 1, 2), "drop": 0.3, "rise": 0.3,
                 "entropy_drop": 0.1}]
        segs = blacktide.merge(hits, gap=64)
        self.assertEqual(len(segs), 3)        # 簇不同不并段
        self.assertEqual(segs[2]["drop"], 0.3)

    def test_sparse_sampling_is_excluded_not_guessed(self):
        """复用期采样帧距可达数千帧 ⇒ 基线落在窗口外的点必须**跳过**，不是算个假跌幅。

        真实世界里那段（42,000 – 33,594,383）是沿参考轨道复用的，采样帧距 4,096。
        滑窗只有 64 帧，基线与当前点隔了三个数量级 —— 那样算出来的"跌幅"是跨大段
        跳越的结果，不可比。跳过并【计数】，把"测不准"与"没有爆发"分开。
        """
        dense = [(f, BASE, 1.0, 0.0) for f in range(0, 200)]
        # 第二段：帧距 4,096（远超 window×4），且占比已换成另一套 —— 若硬算，
        # 跨段那一点会给出一个巨大的假跌幅。
        sparse = [(200_000 + 4096 * k, COHERENT, 0.9, 0.0) for k in range(5)]
        sv = _survey(dense + sparse)
        self.assertEqual(blacktide.detect(sv, CLUSTERS), [])
        self.assertGreater(blacktide.sparse_points(sv.series, 64), 0)

    def test_sparse_points_counts_only_the_sparse_ones(self):
        """密集采样段不该被误记成"稀疏"。"""
        sv = _survey(_series(BASE, BASE))          # 帧距 1，全部密集
        self.assertEqual(blacktide.sparse_points(sv.series, 64), 0)

    def test_sparse_count_is_reported(self):
        ctx, data, _ = load("tide", frames=400, seed=0)
        sv, traj = blacktide.survey_run(ctx, data, seed=0, frames=400)
        clusters = blacktide.clusters_of(ctx)
        th = {"window": 64, "drop_min": 0.15, "rise_min": 0.05,
              "entropy_drop_min": 0.0}
        text = blacktide.build_report(ctx, data, traj, [], clusters, th, None,
                                      sparse=1234)
        self.assertIn("1,234", text)
        self.assertIn("测不准", text)

    def test_closest_miss_explains_why(self):
        sv = _survey(_series(BASE, INCOHERENT))
        miss = blacktide._window_miss(sv, CLUSTERS, 64, 0.15, 0.05, 0.0)
        self.assertIsNotNone(miss)
        self.assertIn("簇内不足半数在跌", miss["reasons"])


class TideReport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ctx, data, _ = load("tide", frames=800, seed=0)
        sv, traj = blacktide.survey_run(ctx, data, seed=0, frames=800)
        cls.ctx, cls.data, cls.traj, cls.sv = ctx, data, traj, sv
        cls.clusters = blacktide.clusters_of(ctx)
        cls.thresholds = {"window": 64, "drop_min": 0.15, "rise_min": 0.05,
                          "entropy_drop_min": 0.0}
        cls.hits = blacktide.detect(sv, cls.clusters, window=64, drop_min=0.15)
        cls.segs = blacktide.merge(cls.hits, gap=64)
        cls.miss = (None if cls.segs else
                    blacktide._window_miss(sv, cls.clusters, 64, 0.15, 0.05, 0.0))
        cls.report = blacktide.build_report(ctx, data, traj, cls.segs,
                                            cls.clusters, cls.thresholds, cls.miss)

    def test_has_three_sections(self):
        for marker in ("黑潮爆发探测", "【一】探测口径", "【二】爆发总览"):
            self.assertIn(marker, self.report)

    def test_lists_every_cluster(self):
        """每一簇的每一个区都要在报告里点到名（取词走 Renderer，与报告同一条路径）。"""
        R = renderer_for(self.ctx, self.traj)
        for g in self.clusters:
            for i in g:
                name = R.seat(self.traj.namer, self.traj.reached_frame,
                              self.ctx.loci[i].id)
                self.assertIn(name, self.report)

    def test_coarse_contrast_is_shown(self):
        self.assertIn("粗判对照", self.report)
        self.assertIn("OVERFLOW", self.report)

    def test_deterministic(self):
        again = blacktide.build_report(self.ctx, self.data, self.traj, self.segs,
                                       self.clusters, self.thresholds, self.miss)
        self.assertEqual(self.report, again)

    def test_json_shape(self):
        blob = blacktide.as_json(self.ctx, self.data, self.traj, self.segs,
                                 self.clusters, self.thresholds, self.miss)
        self.assertEqual(len(blob["clusters"]), len(self.clusters))
        self.assertIn("bursts", blob)
        for b in blob["bursts"]:
            self.assertEqual(len(b["cluster"]), len(b["seats"]))
            self.assertIn("drop", b)


if __name__ == "__main__":
    unittest.main()