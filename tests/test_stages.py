"""阶段装配（A 步）：变量域每一档可以装一组机制门。

盯住四件事：
  ① **缺省回退** —— 没写 `stages` 时完全不装配（与历史逐位一致）；
  ② **启动即报** —— 长度不对 / 门名没登记 / `params` 非空，一律拦下；
  ③ **装配可被看见** —— 门写进 `st.gates`，而它在 `world_signature()` 里，
     于是冻结检测与「复用等价」都看得见这次结构变化；
  ④ **装配进消融** —— 否则阶段机制对 `progress` 没有因果，就只是渲染上的说法。
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest

from _support import ROOT, state, temp_root_with_copy

from engine import ablation
from engine.conditions import evaluate
from engine.core import _assemble, initial_state, run
from engine.loader import Config, ConfigError, DataSet
from engine.operators import Annex, Compete


def _rewrite_genesis(tmp, mutate):
    path = os.path.join(tmp, "data", "genesis.json")
    with open(path, encoding="utf-8") as f:
        g = json.load(f)
    mutate(g)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(g, f, ensure_ascii=False)


class StageValidation(unittest.TestCase):
    """配置与数据的启动校验。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="amphoreus_stage_")
        temp_root_with_copy(self.tmp)
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_shipped_genesis_matches_the_decided_assembly(self):
        """仓库自带 genesis 的装配位：4 项（域长 3 + 阶段四），且三个阶段各装了什么。

        钉住的是**出厂决定**，防止它被无声改回：
          · B1：记忆继承机制由【阶段三】引入（wiki：第 176200 次循环起加入），不靠外生剧本定时开；
          · C2：各阶段性质收在自己阶段里 —— 阶段一压寿命、阶段二调随机性（并把寿命收回常态）、
                阶段三收窄随机性（wiki 阶段二结论「应适当缩小变量区间」）；
          · D1：分化机制同样归【阶段三】（biligame 第 7,091,231 次循环，正落在阶段三区间内），
                原先 7000 帧那条外生开门已删；
          · E：**各档帧预算**（`domain_dwell`）逐档写死在阶段里 —— 2,000 / 4,000 / 5,000，
                照 wiki「三阶段逐次加深」的形状，合计 11,000 落在 3.0 桥段 12,000 之前；
          · I：**「主动更替」是阶段三装配的机制**（biligame 第 19,110,218 次循环
                「将自动更替循环修改为电信号主动更替」，落在阶段三区间内）⇒ 进 `on`。
                注意：`OP_PROMOTION`（**自动**更替循环）**常开、不在门里** —— 它自始就有；
                阶段三装的是把它「改成主动」的那道改造。
        """
        data = DataSet(ROOT, preset="emergent")
        self.assertEqual(len(data.stage_profiles), 4)
        self.assertEqual(data.stage_gates(0), ())                        # 阶段一不装门
        self.assertEqual(data.stage_gates(1), ())                        # 阶段二不装门
        self.assertEqual(data.stage_gates(2), ("OP_MEMORY_INHERIT",     # 阶段三
                                              "OP_BIFURCATE",
                                              "OP_ANNEX",
                                              "OP_ACTIVE_RENEWAL"))
        self.assertEqual(data.stage_gates(3), data.stage_gates(2))       # 阶段四沿用
        self.assertEqual(data.stage_params(0), {"life_span": 175, "domain_dwell": 2000})
        self.assertEqual(data.stage_params(1),
                         {"life_span": 700, "mutation": 0.02, "domain_dwell": 4000})
        self.assertEqual(data.stage_params(2),
                         {"life_span": 700, "mutation": 0.01, "domain_dwell": 5000})
        self.assertEqual(data.stage_params(3), data.stage_params(2))

    def test_absent_stages_means_no_assembly(self):
        _rewrite_genesis(self.tmp, lambda g: g["domain"].pop("stages"))
        data = DataSet(self.tmp, preset="emergent")
        self.assertEqual(data.stage_profiles, [])
        self.assertEqual(data.stage_gates(0), ())

    def test_bad_length_is_rejected(self):
        _rewrite_genesis(self.tmp,
                         lambda g: g["domain"].update({"stages": [{"on": []}]}))
        with self.assertRaises(ConfigError) as cm:
            DataSet(self.tmp, preset="emergent")
        self.assertIn("stages 长度", str(cm.exception))

    def test_unknown_gate_is_rejected(self):
        def mutate(g):
            g["domain"]["stages"][1] = {"on": ["OP_NO_SUCH_GATE"]}
        _rewrite_genesis(self.tmp, mutate)
        with self.assertRaises(ConfigError) as cm:
            DataSet(self.tmp, preset="emergent")
        self.assertIn("OP_NO_SUCH_GATE", str(cm.exception))

    def test_unknown_param_key_is_rejected(self):
        """只允许覆盖【运行时真会读】的旋钮 —— 写别的等于静默失效，故拒绝。"""
        def mutate(g):
            g["domain"]["stages"][2] = {"on": [], "params": {"drift": 0.5}}
        _rewrite_genesis(self.tmp, mutate)
        with self.assertRaises(ConfigError) as cm:
            DataSet(self.tmp, preset="emergent")
        self.assertIn("不是阶段可覆盖的旋钮", str(cm.exception))

    def test_non_numeric_param_is_rejected(self):
        def mutate(g):
            g["domain"]["stages"][1] = {"on": [], "params": {"mutation": "big"}}
        _rewrite_genesis(self.tmp, mutate)
        with self.assertRaises(ConfigError) as cm:
            DataSet(self.tmp, preset="emergent")
        self.assertIn("应为数字", str(cm.exception))


class StageAssembly(unittest.TestCase):
    """装配本身：幂等、累积、进签名。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="amphoreus_stage_")
        temp_root_with_copy(self.tmp)
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        # 阶段 1 装记忆继承；阶段 2 再装分化（累积 ⇒ 阶段 2 应同时有两个门）
        _rewrite_genesis(self.tmp, lambda g: g["domain"].update({"stages": [
            {"on": []},
            {"on": ["OP_MEMORY_INHERIT"]},
            {"on": ["OP_BIFURCATE"]},
            {"on": []},
        ]}))
        self.data = DataSet(self.tmp, preset="emergent")
        self.ctx = Config(self.tmp)

    def _st(self, index=0, exhausted=False):
        # 状态里的 domain 就是 genesis 的 initial_variable（阶段数 = 它的长度）
        st = state(self.ctx, 64,
                   list(self.data.genesis["domain"]["initial_variable"]))
        st.domain_index = index
        st.domains_exhausted = exhausted
        return st

    def test_assembly_is_cumulative(self):
        st = self._st(index=2)
        _assemble(st, self.data)
        self.assertEqual(st.gates, {"OP_MEMORY_INHERIT", "OP_BIFURCATE"})

    def test_assembly_is_idempotent_and_reports_only_new(self):
        st = self._st(index=1)
        self.assertEqual(_assemble(st, self.data), ["OP_MEMORY_INHERIT"])
        self.assertEqual(_assemble(st, self.data), [])          # 再来一次什么都不新
        self.assertEqual(st.gates, {"OP_MEMORY_INHERIT"})

    def test_assembly_lands_in_world_signature(self):
        """装配必须可见于结构签名 —— 否则冻结检测 / 复用等价看不见它。"""
        before = self._st(index=0).world_signature()
        st = self._st(index=1)
        _assemble(st, self.data)
        self.assertNotEqual(before, st.world_signature())

    def test_exhausted_uses_the_extra_profile(self):
        """变量域穷尽之后（阶段四）用多出来的那一项。"""
        _rewrite_genesis(self.tmp, lambda g: g["domain"].update({"stages": [
            {"on": []}, {"on": []}, {"on": []}, {"on": ["OP_BIFURCATE"]},
        ]}))
        data = DataSet(self.tmp, preset="emergent")
        st = self._st(index=2, exhausted=True)
        _assemble(st, data)
        self.assertEqual(st.gates, {"OP_BIFURCATE"})

    def test_stage_params_are_cumulative(self):
        _rewrite_genesis(self.tmp, lambda g: g["domain"].update({"stages": [
            {"on": []},
            {"on": [], "params": {"mutation": 0.05}},
            {"on": [], "params": {"tau_age": 100}},
            {"on": []},
        ]}))
        data = DataSet(self.tmp, preset="emergent")
        self.assertEqual(data.stage_params(0), {})
        self.assertEqual(data.stage_params(1), {"mutation": 0.05})
        self.assertEqual(data.stage_params(2), {"mutation": 0.05, "tau_age": 100})

    def test_domain_advance_assembles_in_a_real_run(self):
        """跑起来：域推进后，该阶段的门真的被装上。"""
        ctx = Config(self.tmp)
        ctx.params["domain_dwell"] = 1
        traj = run(ctx, self.data, seed=0, max_frames=400, rules=evaluate)
        self.assertGreaterEqual(traj.final.domain_index, 1,
                                "帧预算内应当推进过至少一档变量域")
        self.assertIn("OP_MEMORY_INHERIT", traj.final.gates)


class DomainAdvanceCriterion(unittest.TestCase):
    """换档只看【帧预算】：跑满 domain_dwell 才换下一档，与探针结论无关。"""

    def _st(self, progress, n_domain=3, dwell=2):
        ctx = Config(ROOT)
        ctx.params["domain_dwell"] = dwell
        st = state(ctx, 64, list("abc"[:n_domain]))
        for l in st.loci:
            l.progress = progress
        return ctx, st

    def test_each_value_runs_its_budget(self):
        """逐档跑满预算 ⇒ 依次换档；末端那一档跑满 ⇒ 域穷尽。"""
        from engine.operators import Domain
        ctx, st = self._st(progress=0.0, dwell=2)
        for frame in range(2):                            # 第一档跑满
            Domain().apply(st, ctx, None, frame)
        self.assertEqual((st.domain_index, st.domains_exhausted), (1, False))
        for frame in range(2):                            # 第二档跑满
            Domain().apply(st, ctx, None, frame)
        self.assertEqual((st.domain_index, st.domains_exhausted), (2, False))
        for frame in range(2):                            # 末端档跑满 ⇒ 穷尽
            Domain().apply(st, ctx, None, frame)
        self.assertEqual((st.domain_index, st.domains_exhausted), (2, True))

    def test_progress_does_not_shift_the_budget(self):
        """探针提前证伪【不】提前换档 —— 这正是"阶段三只剩 1 帧"的病根所在。"""
        from engine.operators import Domain
        ctx, st = self._st(progress=1.0, dwell=5)         # 一上来就全部达标
        Domain().apply(st, ctx, None, 0)
        self.assertEqual((st.domain_index, st.domains_exhausted), (0, False))
        self.assertEqual(st.domain_dwell, 1)


class StageGatesReachAblation(unittest.TestCase):
    """④ 装配要进消融 —— 否则阶段机制对裁决零因果。"""

    def test_mini_world_carries_the_stage_gates(self):
        import numpy as np
        ctx = Config(ROOT)
        st = state(ctx, 64, ["a"])
        sub = ablation._Ctx(ctx, {"min_population": 6, "ablation_pool": 6,
                                  "life_span": 10 ** 9, "min_factor_cohort": 0,
                                  "disorder": 0.0, "ablation_frames": 1,
                                  "tau_ablation_entropy": 0.012})
        rng = np.random.default_rng(0)
        mini = ablation._mini_world(st, sub, 0, rng, ("OP_MEMORY_INHERIT",))
        self.assertEqual(mini.gates, {"OP_MEMORY_INHERIT"})
        plain = ablation._mini_world(st, sub, 0, rng, ())
        self.assertEqual(plain.gates, set())

    def test_stage_params_really_change_progress(self):
        """B2 的核心：阶段参数必须真能撬动 `progress` —— 否则它只是个装饰。"""
        ctx = Config(ROOT)
        st = state(ctx, 64, ["a"])
        st.domain_disorder = [0.0]
        st.domain_index = 0

        def progress(**over):
            s = st.clone()                      # 克隆：progress 从头算，互不污染
            ablation.solve(s, ctx, seed=0,
                           stage_overrides=(over or None))
            return tuple(round(float(l.progress), 6) for l in s.loci)

        base = progress()
        wild = progress(mutation=5.0, interact_gain=0.0, interact_repel=0.5)
        self.assertNotEqual(base, wild,
                            "阶段参数没有撬动 progress —— 那它只是个装饰")


class StageParamsReachTheWorld(unittest.TestCase):
    """C1：阶段参数不只进探针，也真的改变【世界】的演化。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="amphoreus_stage_")
        temp_root_with_copy(self.tmp)
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_view_merges_params_and_delegates_the_rest(self):
        from engine.core import StageCtx
        ctx = Config(ROOT)
        view = StageCtx(ctx)
        self.assertEqual(view.params, ctx.params)
        self.assertIsNot(view.params, ctx.params)         # 是副本：不污染基础配置
        view.rebind({"mutation": 0.5})
        self.assertEqual(view.params["mutation"], 0.5)
        self.assertEqual(ctx.params["mutation"], 0.01)    # 基础配置一字未改
        self.assertIs(view.loci, ctx.loci)                # 其余属性转发给真 Config
        self.assertEqual(view.policy("OVERFLOW"), ctx.policy("OVERFLOW"))
        view.rebind({})
        self.assertEqual(view.params, ctx.params)         # 空覆盖 ⇒ 回到基础

    def test_stage_params_change_the_world(self):
        """给阶段二装 min_population=200 ⇒ 种群被托高：世界真的不一样了。"""
        def run_with(stages):
            _rewrite_genesis(self.tmp,
                             lambda g: g["domain"].update({"stages": stages}))
            data = DataSet(self.tmp, preset="emergent")
            ctx = Config(self.tmp)
            ctx.params["domain_dwell"] = 1
            return run(ctx, data, seed=0, max_frames=120, rules=evaluate)

        empty = [{"on": []}, {"on": []}, {"on": []}, {"on": []}]
        plain = run_with(empty)
        big = run_with([{"on": []},
                        {"on": [], "params": {"min_population": 200}},
                        {"on": []}, {"on": []}])
        self.assertGreaterEqual(len(big.final.pool), 200)
        self.assertNotEqual(len(plain.final.pool), len(big.final.pool))


class AnnexProtocol(unittest.TestCase):
    """嵌合协议（D2 形态 A）：主导因子把决策写成【协议内容】，成为后续默认。

    考据见 biligame 第 1480 / 566 行；有界落法见 `engine/operators.py::Annex`。
    """

    def setUp(self):
        self.ctx = Config(ROOT)
        self.data = DataSet(ROOT, preset="emergent")
        self.st = initial_state(self.ctx, self.data, 0)

    def test_annex_writes_the_protocol_once(self):
        """门没开就不写；门开后写一次（含倍率），且此后再也不改。"""
        op = Annex()
        op.apply(self.st, self.ctx, None, 0)
        self.assertNotIn("annex.factor", self.st.overrides)      # 门没开
        self.st.gates.add(Annex.name)
        op.apply(self.st, self.ctx, None, 0)
        self.assertIsInstance(self.st.overrides["annex.factor"], int)
        self.assertAlmostEqual(self.st.overrides["annex.span_ratio"], 0.8)
        self.assertEqual(self.st.score["embedded_protocol"], 1.0)
        op.apply(self.st, self.ctx, None, 1)                     # 只嵌合一次
        self.assertEqual(self.st.score["embedded_protocol"], 1.0)

    def test_non_annex_factors_die_earlier(self):
        """协议生效后，非嵌合因子的个体更早退出演算（「从演算中剔除」）。"""
        st = self.st
        st.gates.add(Annex.name)
        st.overrides["annex.factor"] = 0
        st.overrides["annex.span_ratio"] = 0.5
        span = float(self.ctx.params["life_span"])
        idx = st.pool.index()
        # support 由 Interact 逐帧维护；这里直接撑高，免得被判成「孤立」而全体阵亡
        for k in idx:
            st.pool.support[int(k)] = 0.5 * max(1, idx.size - 1)
            st.pool.born[int(k)] = -int(span * 0.75)   # 年龄 = 0.75×寿命
        # 非嵌合者上限 0.5×（当场出局），嵌合者上限 1×（留下）
        Compete().apply(st, self.ctx, None, 0)
        alive = st.pool.index()
        self.assertGreater(int(alive.size), 0)
        self.assertEqual({int(f) for f in st.pool.factor[alive]}, {0})

    def test_without_the_protocol_nobody_is_culled(self):
        """没写协议时，同一批人一个都不该死 —— 证明上面那条差异确由协议造成。"""
        st = self.st                        # 门不开、无 overrides
        span = float(self.ctx.params["life_span"])
        idx = st.pool.index()
        for k in idx:
            st.pool.support[int(k)] = 0.5 * max(1, idx.size - 1)
            st.pool.born[int(k)] = -int(span * 0.75)
        Compete().apply(st, self.ctx, None, 0)
        self.assertEqual(int(st.pool.index().size), int(idx.size))


if __name__ == "__main__":
    unittest.main()
