"""结论层：判据表（C4）与「耗尽」维度（C3）。

三件事要盯住：
  ① 判据表必须与原来的三段判据【等价】—— 既有世界的结论一字不变；
  ② 新增的 annihilation 维度必须【真的可达】，否则就是死代码；
  ③ 新增维度不得污染既有世界 —— 不开溢出的世界，吞没计数必须恒为 0。
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest

from _support import ROOT, load, state, temp_root_with_copy

from engine.loader import Config, ConfigError


class VerdictRuleTable(unittest.TestCase):
    """判据表是数据：每条都得在 conclusions.json 里查得到文案。"""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, "config", "params.json"), encoding="utf-8") as f:
            cls.params = json.load(f)
        with open(os.path.join(ROOT, "config", "conclusions.json"),
                  encoding="utf-8") as f:
            cls.conclusions = json.load(f)

    def test_every_rule_has_conclusion_text(self):
        ids = [r["id"] for r in self.params["verdict_rules"]]
        self.assertTrue(ids)
        for rid in ids:
            self.assertIn(rid, self.conclusions)
            self.assertTrue(self.conclusions[rid]["id"])
            self.assertTrue(self.conclusions[rid]["template"])

    def test_base_verdicts_still_present(self):
        for key in ("proved", "refuted", "undecided"):
            self.assertIn(key, self.conclusions)

    def test_only_known_when_clauses(self):
        for rule in self.params["verdict_rules"]:
            self.assertIn(rule["when"], ("all_falsified", "stalled_and_exhausted"))

    def test_display_names_come_from_config(self):
        """报告的裁决短名与停因长句都必须取自配置 —— 加维度不必改报告层。"""
        from engine.render import Renderer
        from _support import load as _load

        ctx, _data, _traj = _load("emergent", frames=200)
        R = Renderer(ctx)
        for rid in [r["id"] for r in self.params["verdict_rules"]]:
            self.assertEqual(R.verdict_label(rid),
                             self.conclusions[rid]["label"])
        self.assertEqual(R.stop_label("ANNIHILATION"),
                         self.conclusions["annihilation"]["stop_label"])
        # 非裁决类的停因走词表
        self.assertTrue(R.stop_label("BUDGET"))
        self.assertEqual(R.verdict_label("no_such_verdict"), "no_such_verdict")

    def test_rule_table_reproduces_base_behaviour(self):
        """等价性：判据表要能重现原来那段三段判据的结论。

        ⑤ 之后求值在 `engine/verdicts.py`（情形 + 附加条件都是注册表），
        这里直接对它求值，不再依赖 core 里的私有函数。
        """
        from engine.verdicts import evaluate, inner_conclusion

        ctx = Config(ROOT)
        tau = float(ctx.params["tau_falsify"])

        def world(solver, falsified, stalled, exhausted, destr, path_b=None):
            st = state(ctx, 8, ["a", "b"])
            b = falsified if path_b is None else path_b
            for l in st.loci:
                l.progress = tau if falsified else 0.0
                l.progress2 = tau if b else 0.0
            st.solver = solver
            st.domains_exhausted = exhausted
            st.destruction_events = destr
            return st

        E, D = "OP_SOLVE_ENTROPY", "OP_SOLVE_DESTRUCTION"
        self.assertEqual(inner_conclusion(world(E, True, False, True, 0), ctx, False),
                         "proved")
        self.assertEqual(inner_conclusion(world(D, True, False, True, 0), ctx, False),
                         "destruction")
        self.assertEqual(inner_conclusion(world(E, False, True, True, 0), ctx, True),
                         "refuted")
        self.assertIsNone(inner_conclusion(world(E, False, False, False, 0), ctx, False))
        # 耗尽维度：全位证伪 + 吞没达标 ⇒ 走 annihilation（而不是 proved）
        self.assertEqual(inner_conclusion(world(E, True, False, True, 999), ctx, False),
                         "annihilation")
        # 但吞没没达标时不许抢先
        self.assertEqual(inner_conclusion(world(E, True, False, True, 1), ctx, False),
                         "proved")
        # ---- R3：两路探针**一致**才算证伪（单一路径达标不够）----
        self.assertIsNone(
            inner_conclusion(world(E, True, False, True, 0, path_b=False), ctx, False),
            "只有路 A【独留】达标、路 B【剔除】不达标时，判据不该成立")
        self.assertIsNone(
            inner_conclusion(world(E, False, False, True, 0, path_b=True), ctx, False),
            "只有路 B 达标、路 A 不达标时，判据同样不该成立")
        # evaluate 一次遍历同时给出 (结论, 是否升格)
        self.assertEqual(evaluate(world(D, True, False, True, 0), ctx, False),
                         ("destruction", True))
        self.assertEqual(evaluate(world(E, True, False, True, 999), ctx, False),
                         ("annihilation", True))
        self.assertEqual(evaluate(world(E, True, False, True, 0), ctx, False),
                         ("proved", False))
        self.assertEqual(evaluate(world(E, False, True, True, 0), ctx, True),
                         ("refuted", False))
        # 外生改写优先于一切内层判定
        over = world(E, False, False, False, 0)
        over.conclusion_override = "overwritten"
        self.assertEqual(evaluate(over, ctx, False), ("overwritten", False))


class AnnihilationDimension(unittest.TestCase):
    """C3：新增维度必须可达，且不得污染既有世界。"""

    @classmethod
    def setUpClass(cls):
        # ⚠ 38,000 帧：R3 两路探针之后，tide 到达 annihilation 的帧从 20,000 推到了
        # 37,000（路 B【剔除】口径比路 A 严 —— 这正是「提升区分度」的代价）。
        # 该测试的价值就在于「真的有一个世界能走到 annihilation」，故必须跑满。
        cls.ctx, _data, cls.traj = load("tide", frames=38000)

    def test_tide_is_the_reachable_world(self):
        self.assertEqual(self.traj.verdict, "annihilation")
        self.assertEqual(self.traj.conclusion["id"], "C_CONSUMED_BY_ANNIHILATION")
        self.assertTrue(self.traj.ascended)
        self.assertGreater(self.traj.final.destruction_events, 0)

    def test_tide_overflows(self):
        self.assertGreaterEqual(self.traj.final.noise,
                                float(self.ctx.params["tau_noise_annihilation"]))

    def test_normal_worlds_never_annihilate(self):
        """既有世界逐帧不变的证据：它们的吞没计数必须恒为 0。"""
        for preset in ("emergent", "plot", "nullify"):
            with self.subTest(preset=preset):
                _ctx, _data, traj = load(preset, frames=6000)
                self.assertEqual(traj.final.destruction_events, 0)
                self.assertLess(traj.final.noise,
                                float(_ctx.params["tau_noise_annihilation"]))


class CompetitiveElimination(unittest.TestCase):
    """淘汰门槛的两种口径，各自都要【真的能触发】。

    这条测试是「不许留死代码」的凭据：孤立口径与同化口径各造一个最小世界，
    证明它们真的会杀人。既有世界里两个口径都不成立，所以轨迹不变。
    """

    def _world(self, supports, age=100):
        import numpy as np

        ctx = Config(ROOT)
        dim = int(ctx.params["dim"])
        st = state(ctx, 16, ["a", "b"])
        frame = 5000
        for i in range(len(supports)):
            k = st.pool.alloc()
            v = np.zeros(dim, dtype=np.float32)
            v[i % dim] = 1.0                  # 各自独占一维 ⇒ 彼此正交
            st.pool.vec[k] = v
            st.pool.born[k] = frame - age
        st.pool.support[:] = 0.0
        idx = st.pool.index()
        for pos, k in enumerate(idx):
            st.pool.support[int(k)] = float(supports[pos])
        return ctx, st, frame, idx

    def test_isolated_individual_is_killed(self):
        """常态口径：平均相似度低于 tau_support 且已过 tau_age 者被淘汰。"""
        from engine.operators import Compete

        # 4 个个体，3 个彼此相似（support 3.0 ⇒ 平均 1.0），1 个谁也不像（0.0）
        ctx, st, frame, idx = self._world([3.0, 3.0, 3.0, 0.0])
        Compete().apply(st, ctx, None, frame)
        self.assertEqual(st.destruction_events, 1)
        self.assertFalse(bool(st.pool.alive[int(idx[3])]))     # 被孤立者死
        for k in idx[:3]:
            self.assertTrue(bool(st.pool.alive[int(k)]))       # 其余活着

    def test_young_isolated_individual_survives(self):
        """孤立但还年轻 —— 不该死（tau_age 是这道门的另一半）。"""
        from engine.operators import Compete

        ctx, st, frame, idx = self._world([3.0, 3.0, 3.0, 0.0], age=10)
        Compete().apply(st, ctx, None, frame)
        self.assertEqual(st.destruction_events, 0)
        self.assertTrue(bool(st.pool.alive[int(idx[3])]))

    def test_homogenized_individuals_are_swallowed_when_overflowing(self):
        """溢出口径：世界涨满后，改为吞没【被同化得最深】的那些（不看年龄）。"""
        from engine.operators import Compete

        ctx, st, frame, idx = self._world([3.0, 3.0, 3.0, 0.0], age=10)
        st.noise = float(ctx.params["tau_noise_annihilation"])
        Compete().apply(st, ctx, None, frame)
        self.assertEqual(st.destruction_events, 3)             # 三个高相似者被吞没
        self.assertTrue(bool(st.pool.alive[int(idx[3])]))       # 唯一不同者留下

    def test_no_elimination_without_overflow_or_isolation(self):
        """既有世界的情形：既没越线也没孤立 ⇒ 一个都不杀。"""
        from engine.operators import Compete

        ctx, st, frame, _idx = self._world([3.0, 3.0, 3.0, 3.0])
        Compete().apply(st, ctx, None, frame)
        self.assertEqual(st.destruction_events, 0)


class RuleTableValidation(unittest.TestCase):
    """启动校验要拦下「判据表指向一条没有文案的结论」。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="amphoreus_verdict_")
        temp_root_with_copy(self.tmp)
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_rule_without_template_is_rejected(self):
        path = os.path.join(self.tmp, "config", "params.json")
        with open(path, encoding="utf-8") as f:
            p = json.load(f)
        p["verdict_rules"].append({"id": "no_such_conclusion",
                                   "when": "all_falsified"})
        with open(path, "w", encoding="utf-8") as f:
            json.dump(p, f, ensure_ascii=False)
        with self.assertRaises(ConfigError) as cm:
            Config(self.tmp)
        self.assertIn("no_such_conclusion", str(cm.exception))

    def test_unknown_when_is_rejected(self):
        path = os.path.join(self.tmp, "config", "params.json")
        with open(path, encoding="utf-8") as f:
            p = json.load(f)
        p["verdict_rules"][0]["when"] = "because_i_say_so"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(p, f, ensure_ascii=False)
        with self.assertRaises(ConfigError) as cm:
            Config(self.tmp)
        self.assertIn("because_i_say_so", str(cm.exception))

    def test_counter_without_min_is_rejected(self):
        path = os.path.join(self.tmp, "config", "params.json")
        with open(path, encoding="utf-8") as f:
            p = json.load(f)
        p["verdict_rules"].append({"id": "annihilation", "when": "all_falsified",
                                   "require": [{"counter": "destruction_events"}]})
        with open(path, "w", encoding="utf-8") as f:
            json.dump(p, f, ensure_ascii=False)
        with self.assertRaises(ConfigError) as cm:
            Config(self.tmp)
        self.assertIn("min", str(cm.exception))

    def test_unknown_counter_is_rejected(self):
        """counter 写错过去会被 getattr(..., 0) 静默当成 0 —— 现在启动就报。"""
        path = os.path.join(self.tmp, "config", "params.json")
        with open(path, encoding="utf-8") as f:
            p = json.load(f)
        p["verdict_rules"].append({"id": "annihilation", "when": "all_falsified",
                                   "require": [{"counter": "destrucion_events",
                                                "min": 1}]})
        with open(path, "w", encoding="utf-8") as f:
            json.dump(p, f, ensure_ascii=False)
        with self.assertRaises(ConfigError) as cm:
            Config(self.tmp)
        self.assertIn("destrucion_events", str(cm.exception))

    def test_unknown_solver_is_rejected(self):
        """⑤ 的前置：演算方向名进注册表 —— 写错过去只是判据恒不成立，现在启动就报。"""
        path = os.path.join(self.tmp, "config", "params.json")
        with open(path, encoding="utf-8") as f:
            p = json.load(f)
        p["verdict_rules"][0]["require"] = [{"solver": "OP_NOPE"}]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(p, f, ensure_ascii=False)
        with self.assertRaises(ConfigError) as cm:
            Config(self.tmp)
        self.assertIn("OP_NOPE", str(cm.exception))

    def test_genesis_unknown_solver_is_rejected(self):
        path = os.path.join(self.tmp, "presets", "_default", "genesis.json")
        with open(path, encoding="utf-8") as f:
            g = json.load(f)
        g.setdefault("runtime", {})["solver"] = "OP_NOPE"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(g, f, ensure_ascii=False)
        from engine.loader import DataSet
        with self.assertRaises(ConfigError) as cm:
            DataSet(self.tmp, preset="emergent")
        self.assertIn("OP_NOPE", str(cm.exception))

    def test_condition_must_have_exactly_one_known_key(self):
        """require 每项恰好含一个已知条件键 —— 零个 / 两个都拦。"""
        path = os.path.join(self.tmp, "config", "params.json")
        with open(path, encoding="utf-8") as f:
            p = json.load(f)
        p["verdict_rules"].append({"id": "annihilation", "when": "all_falsified",
                                   "require": [{"min": 1}]})
        with open(path, "w", encoding="utf-8") as f:
            json.dump(p, f, ensure_ascii=False)
        with self.assertRaises(ConfigError) as cm:
            Config(self.tmp)
        self.assertIn("已知条件键", str(cm.exception))

        path = os.path.join(self.tmp, "config", "params.json")
        with open(path, encoding="utf-8") as f:
            p = json.load(f)
        p["verdict_rules"][-1]["require"] = [
            {"solver": "OP_SOLVE_ENTROPY", "counter": "promotions", "min": 1}]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(p, f, ensure_ascii=False)
        with self.assertRaises(ConfigError) as cm:
            Config(self.tmp)
        self.assertIn("已知条件键", str(cm.exception))

    def test_rule_conclusion_without_label_is_rejected(self):
        """报告层不再写死裁决短名 ⇒ 判据表用到的结论必须自带 label。"""
        path = os.path.join(self.tmp, "config", "conclusions.json")
        with open(path, encoding="utf-8") as f:
            c = json.load(f)
        c["annihilation"].pop("label")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(c, f, ensure_ascii=False)
        with self.assertRaises(ConfigError) as cm:
            Config(self.tmp)
        self.assertIn("label", str(cm.exception))

    def test_unknown_assertion_name_is_rejected(self):
        """断言名写错过去只静默记一条 FAIL —— 现在启动就报。"""
        os.makedirs(os.path.join(self.tmp, "presets", "t"), exist_ok=True)
        with open(os.path.join(self.tmp, "presets", "t", "preset.json"),
                  "w", encoding="utf-8") as f:
            json.dump({"name": "t"}, f)
        with open(os.path.join(self.tmp, "presets", "t", "assertions.jsonl"),
                  "w", encoding="utf-8") as f:
            f.write(json.dumps({"assert": "eternal_return_ever", "expect": True}) + "\n")
        from engine.loader import DataSet
        with self.assertRaises(ConfigError) as cm:
            DataSet(self.tmp, preset="t")
        self.assertIn("eternal_return_ever", str(cm.exception))


class VerdictExplainability(unittest.TestCase):
    """报告的「裁决依据」块：摊开各席 progress、达标率与裕度。纯只读渲染。

    `progress` 是连续量（消融熵 / 消融阈值）：≥ τ 即被证伪，越接近 τ 越勉强。
    措辞上它是【经验裁决】（测量），不是形式证明 —— 首行须点明这一点。
    """

    def test_note_lists_gap_seats(self):
        from run import _progress_note

        ctx, _data, traj = load("emergent", frames=200)
        tau = float(ctx.params["tau_falsify"])
        for i, l in enumerate(traj.final.loci):
            l.progress = tau + 0.5 if i % 2 == 0 else 0.05 * i    # 只证伪一半
        lines = _progress_note(traj.namer, ctx, traj)
        text = "\n".join(lines)
        total = len(traj.final.loci)
        gap = sum(1 for i in range(total) if i % 2 == 1)
        self.assertIn("经验裁决", text)          # 正名：这是测量而非形式证明
        self.assertIn(f"达标 {total - gap}/{total}", text)
        self.assertIn("尚未证伪", text)

    def test_note_when_all_falsified(self):
        from run import _progress_note

        ctx, _data, traj = load("emergent", frames=200)
        tau = float(ctx.params["tau_falsify"])
        for i, l in enumerate(traj.final.loci):
            l.progress = tau + 0.01 * i                      # 全部达标，但程度不同
        lines = _progress_note(traj.namer, ctx, traj)
        text = "\n".join(lines)
        self.assertNotIn("尚未证伪", text)
        # 全达标时点出「最勉强」的那一席 —— progress 最小的第 0 席（= τ ⇒ 裕度 1.00×τ）
        self.assertIn("最勉强", text)
        self.assertIn("裕度 1.00×τ", text)


if __name__ == "__main__":
    unittest.main()
