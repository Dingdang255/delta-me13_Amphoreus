"""敏感度（C5）：结论要随【动力学】变，而不是把参数直译成帧号。

这个引擎最危险的退化形态是变成一台「参数 → 帧号翻译机」：裁决看起来是演算出来的，
其实只是照着配置里的数值在某个固定帧号上给出某个固定枚举。本文件用两件可核对的事
把这条退化堵住：

  ① 消融求解器真的在跑【嵌套演算】—— 同一批位，只改「世界失序度」这一处输入，
     progress 必须跟着变（否则它就是查表，不是演算）；
  ② 引擎的裁决由【消融结果】驱动 —— 同一个世界、同一份外生剧本，只改「消融判熵的
     阈值」这一处动力学，结论就会改判，而不是照旧在原来的帧号上给原来的答案。
"""
from __future__ import annotations

import os
import sys
import unittest

from _support import ROOT, load, state

from engine import ablation
from engine.core import run
from engine.loader import Config, DataSet

sys.path.insert(0, os.path.join(ROOT, "tools"))
import sensitivity  # noqa: E402


class AblationSensitivity(unittest.TestCase):
    """① 消融对「世界失序度」敏感：progress 是【连续】量，且随 disorder 变。"""

    def _progress(self, disorder):
        return tuple(float(l.progress) for l in self._loci(disorder))

    def _loci(self, disorder):
        ctx = Config(ROOT)
        st = state(ctx, 64, ["a"])
        st.domain_disorder = [float(disorder)]
        st.domain_index = 0
        ablation.solve(st, ctx, seed=0)
        return st.loci

    def test_progress_is_continuous(self):
        """progress 是连续量（⑥-B）—— 不再是 {0, 1} 两档。"""
        vals = set(self._progress(1.0))
        self.assertGreater(len(vals), 2, "progress 退回了二值，连续读数丢失")

    def test_progress_responds_to_disorder(self):
        """只改失序度、其余一切不变 —— progress 必须变化。

        若整条扫描线给出同一个结果，说明 progress 与动力学脱钩（查表），
        那台「翻译机」就又回来了。
        """
        seen = {self._progress(d) for d in (0.0, 0.5, 1.0, 5.0)}
        self.assertGreater(len(seen), 1, "progress 对 disorder 完全不敏感")
        # 失序度足够大时，每一位都被独立驱动失序 ⇒ 全部越过达标线。
        self.assertTrue(all(v >= 1.0 for v in self._progress(5.0)))

    def test_average_progress_grows_with_disorder(self):
        """失序度越大 ⇒ 平均 progress 越高（连续读数真的在量「程度」）。"""
        low = [float(l.progress) for l in self._loci(0.0)]
        high = [float(l.progress) for l in self._loci(5.0)]
        self.assertLess(sum(low) / len(low), sum(high) / len(high))

    def test_tau_falsify_is_now_a_real_knob(self):
        """⑥-B 的核心：τ 不再是空转旋钮 —— 换个 τ，达标席位数就该变。

        二值时代 progress ∈ {0,1}，任何 τ ∈ (0,1] 结果相同；现在 progress 连续，
        τ 越大达标越少。这条测试就是「B 确实兑现了」的证据。
        """
        ctx = Config(ROOT)
        st = state(ctx, 64, ["a"])
        st.domain_disorder = [1.0]
        st.domain_index = 0
        ablation.solve(st, ctx, seed=0)
        taus = (0.25, 1.0, 1.5, 1e9)
        hits = [sum(1 for l in st.loci if l.progress >= t) for t in taus]
        self.assertEqual(hits, sorted(hits, reverse=True), "τ 变大而达标数反而变多")
        self.assertGreater(len(set(hits)), 1, "τ 仍是空转旋钮")


class RefutedWorldNeverFalsifies(unittest.TestCase):
    """`refuted` 世界的**定义性判据**：探针在任何一档上都不达标。

    「证伪」只能由一个**初始变量域不同**的世界演示（`all_falsified` 是世界无关的量，
    见遗留议题 §1.4 / 教程 §四）。这条守卫钉住的正是那个"不同" —— 若有人把
    `presets/refuted/genesis.json` 改回默认（机制门 / disorder / 寿命），它就会重新
    变成 `proved` / `destruction`。满预算回归只在 `selfcheck --full` 里跑（47s），
    这里用秒级的探针直接验它的前提。
    """

    def test_probe_never_passes_in_any_domain(self):
        from engine.core import _stage_index
        from engine import verdicts

        ctx, data, _ = load("refuted", frames=600, seed=0)
        st = state(ctx, 64, list(data.genesis["domain"]["initial_variable"]))
        st.domain_disorder = [float(x) for x in data.genesis["domain"]["disorder"]]
        for di in range(len(st.domain_disorder)):
            st.domain_index = di
            st.domains_exhausted = False
            si = _stage_index(st, data)
            ablation.solve(st, ctx, seed=0, stage_gates=data.stage_gates(si),
                           stage_overrides=data.stage_params(si))
            self.assertFalse(
                verdicts._falsified(st, ctx),
                f"域 {di} 上 `all_falsified` 成立了 —— `refuted` 世界的前提被破坏")


class VerdictDrivenByDynamics(unittest.TestCase):
    """② 裁决由消融结果驱动：改一处动力学阈值，结论随之改判。"""

    def _world(self, **param_patch):
        data = DataSet(ROOT, preset="emergent")
        ctx = Config(ROOT, lex_overlay=data.preset.get("lexicon"))
        ctx.params.update(param_patch)
        # 帧预算要跨过第一档的 domain_dwell：证真是【换档之后】才发生的
        # （阶段一那套参数跑不出全称证伪，换到阶段二的新参数才越过 τ）。
        # ⚠ R3 两路探针之后，证真从 2,000 帧推到了 **4,000 帧**（路 B【剔除】口径
        # 比路 A 严），故预算要留足 —— 这也是那条改动最直接的可见后果。
        frames = int(ctx.params["domain_dwell"]) + 3000
        return ctx, data, run(ctx, data, seed=0, max_frames=frames)

    def test_baseline_is_proved(self):
        _ctx, _data, traj = self._world()
        self.assertEqual(traj.verdict, "proved")

    def test_raising_entropy_threshold_flips_verdict(self):
        """把「消融判熵的阈值」抬到天上 ⇒ 没有一个位能达标 ⇒ 命题无从证真。

        世界、种子、剧本、帧预算全都没变，只动了这一处动力学 —— 结论必须跟着变。
        这正是「裁决不是帧号翻译」的直接证据。
        """
        _ctx, _data, traj = self._world(tau_ablation_entropy=1e9)
        self.assertNotEqual(traj.verdict, "proved")
        self.assertEqual(traj.verdict, "undecided")


class TwoPathProbes(unittest.TestCase):
    """R3 · 多路独立探针：路 A【独留】与路 B【剔除】必须提供**独立**信息。

    这是 R3 成立的**唯一前提** —— 第二路若不是独立的，加它就只是把同一个数乘个常数，
    "两路一致才判"会退化成"只看路 A"。

    ⚠ 曾经试过另一条路（保留全体但**切断耦合**）：实测 `progress2 / progress` 恒定在
    3.05–3.40（跨度仅 1.11×）—— **共线**，且两路都远在阈值之上 ⇒ 判据零增益。
    原因可解释：迷你世界里的席间差异**只来自该位的耦合行**，切断耦合就把这个差异
    抹掉了，剩下的只是采样噪声。

    ⚠ 第二十七批（消融探针重构）重新标定：探针取 K=32 次均值后，`progress2 / progress`
    的**比值跨度**从 1.3×+ 掉到 1.13–1.16×（emergent@2,000 / plot@8,000 实测）。
    原因是原先那 1.3× 里有一半是**单次抽样的噪声**；去噪后，那个"跨度"不再可信，
    但两路的**排序仍然完全独立**（12 席里同位的 0 个）。故本类的守卫改为：
      · 比值不是常数（> 1.05，防"同一个数乘常数"）；
      · **序关系**必须显著不同（≤ 半数位次相同）—— 这才是"独立信息"的本质判据。
    """

    @classmethod
    def setUpClass(cls):
        cls.ctx, cls.data, cls.traj = load("emergent", frames=2500, seed=0)
        cls.loci = cls.traj.final.loci

    def test_both_paths_are_measured(self):
        self.assertTrue(any(float(l.progress) > 0 for l in self.loci), "路 A 没跑")
        self.assertTrue(any(float(l.progress2) > 0 for l in self.loci), "路 B 没跑")

    def test_two_paths_are_not_collinear(self):
        """两路不许是同一个数的常数倍 —— 否则第二路没有独立信息。"""
        a = [float(l.progress) for l in self.loci]
        b = [float(l.progress2) for l in self.loci]
        ratios = [y / x for x, y in zip(a, b) if x > 0]
        self.assertTrue(ratios)
        spread = max(ratios) / min(ratios)
        self.assertGreater(spread, 1.05,
                           f"两路共线（比值跨度仅 {spread:.3f}×），第二路无效")

    def test_two_paths_rank_differently(self):
        """★ 独立信息的**本质**判据：两路的排序必须显著不同。

        同一个读数换个量纲 ⇒ 排序完全一致；这里要求**至多一半位次相同**。
        （第二十七批去噪后实测 0/12 —— 两路对「哪一席最勉强」的看法完全不同。）
        """
        a = [float(l.progress) for l in self.loci]
        b = [float(l.progress2) for l in self.loci]
        order_a = sorted(range(len(a)), key=lambda i: a[i])
        order_b = sorted(range(len(b)), key=lambda i: b[i])
        same = sum(1 for i in range(len(a)) if order_a[i] == order_b[i])
        self.assertLessEqual(same, len(a) // 2,
                             f"两路排序过于一致（同位 {same}/{len(a)}）—— 第二路近乎冗余")

    def test_paths_do_not_enter_the_fingerprint(self):
        """两路都只是读数 —— 不进 digest，故加它们不改轨迹（指纹门禁另证）。"""
        _ctx, _data, again = load("emergent", frames=2500, seed=0)
        self.assertEqual(self.traj.final.digest(), again.final.digest())


class SensitivityScanTool(unittest.TestCase):
    """③ 扫描产物（建议表 #8）：参数 × 种子的矩阵真的把参数【用上】了。

    最危险的失败形态不是报错，而是**静默空转**：参数名写错 / 引擎根本不读它，
    于是整张热力图全同色 —— 看着像「结论很稳」，其实是「什么都没扫」。
    故这里盯两件事：白名单挡住没人读的键；换取值结果必须真的变。
    """

    PRESET = "emergent"
    FRAMES = 60          # 够跑到第一档的常规演化：低 τ 会当场判，高 τ 判不出来

    def _scan(self, params, seeds=(0,), frames=None):
        return sensitivity.scan(self.PRESET, list(seeds), params,
                                frames=self.FRAMES if frames is None else frames,
                                iter_cap=60000, jobs=1)

    def test_unknown_param_is_rejected(self):
        """没人读的键必须当场报错，否则整张图会是一张白图。"""
        with self.assertRaises(ValueError):
            sensitivity.check_param("drift")          # 已知在 config 里没人读
        with self.assertRaises(ValueError):
            sensitivity.parse_params(["nope=1,2"])

    def test_tunable_names_are_the_runtime_read_knobs(self):
        from engine.operators import STAGE_TUNABLE
        self.assertEqual(sensitivity.tunable_names(), tuple(STAGE_TUNABLE))
        self.assertIn("tau_falsify", sensitivity.tunable_names())

    def test_matrix_shape_and_order(self):
        cells = self._scan([("tau_falsify", [0.5, 1.5])], seeds=(0, 1))
        self.assertEqual(len(cells), 4)
        rows = sensitivity.rows_of(cells, "tau_falsify", [0, 1])
        self.assertEqual([r["value"] for r in rows], [0.5, 1.5])
        for row in rows:
            self.assertEqual([c["seed"] for c in row["cells"]], [0, 1])

    def test_changing_the_value_changes_the_outcome(self):
        """扫描必须真的把参数用上 —— 两个取值给出不同裁决才算「扫到了」。"""
        cells = self._scan([("tau_falsify", [0.5, 1.5])])
        got = {c["value"]: c["verdict"] for c in cells}
        self.assertEqual(got[0.5], "proved")
        self.assertEqual(got[1.5], "undecided")

    def test_truncated_cells_are_flagged_and_excluded(self):
        """没跑完的世界其裁决是兜底的，不能混进统计。"""
        cells = sensitivity.scan(self.PRESET, [0], [("tau_falsify", [1.0])],
                                 frames=self.FRAMES, iter_cap=1, jobs=1)
        self.assertTrue(cells[0]["truncated"])
        row = sensitivity.rows_of(cells, "tau_falsify", [0])[0]
        self.assertEqual(row["solid"], 0)
        self.assertEqual(row["counts"], {})
        self.assertIsNone(row["frames"])
        self.assertIn("~", sensitivity.render_text(
            cells, [("tau_falsify", [1.0])], [0],
            {"preset": self.PRESET, "frames": self.FRAMES, "iter_cap": 1}))

    def test_scan_is_deterministic(self):
        params = [("tau_falsify", [0.5, 1.5])]
        a = self._scan(params, seeds=(0, 1))
        b = self._scan(params, seeds=(0, 1))
        self.assertEqual(a, b)

    def test_conflicting_verdicts_are_called_out(self):
        cells = self._scan([("tau_falsify", [0.5, 1.5])])
        text = sensitivity.render_text(cells, [("tau_falsify", [0.5, 1.5])], [0],
                                       {"preset": self.PRESET, "frames": self.FRAMES})
        self.assertIn("改判", text)

    def test_html_is_self_contained_and_carries_every_cell(self):
        cells = self._scan([("tau_falsify", [0.5, 1.5])], seeds=(0, 1))
        html = sensitivity.render_html(cells, [("tau_falsify", [0.5, 1.5])], [0, 1],
                                       {"preset": self.PRESET, "frames": self.FRAMES})
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)
        self.assertNotIn("</script><script>", html)
        self.assertEqual(html.count("<td"), 2 + 4)      # 2 个取值标签 + 4 个格子
        self.assertIn("热力", html)
        for c in cells:
            self.assertIn(c["label"], html)

    def test_parse_params_accepts_int_and_float(self):
        self.assertEqual(sensitivity.parse_params(["promotion_dwell=10,20"]),
                         [("promotion_dwell", [10, 20])])
        self.assertEqual(sensitivity.parse_params(["mutation=0.01,0.02"]),
                         [("mutation", [0.01, 0.02])])
        self.assertEqual(sensitivity.resolve_seeds("3:3"), [3, 4, 5])
        self.assertEqual(sensitivity.resolve_seeds("2,4"), [2, 4])


if __name__ == "__main__":
    unittest.main()
