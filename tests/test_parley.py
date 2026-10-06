"""交涉取火种（能力 `parley`）—— 判据、后果，以及与 `plead` 的分家。

这是 B6-L2 补的**第二条路**：`evict_holder` 是暴力（必死），`parley` 是交涉
（**谈成则自愿离席、人不死**）。四条要求：

  ① **判据是判据**：手里越空越愿意给（`slot.value ≤ tau_parley`）、神志尚清才谈得拢
     （`noise ≤ tau_noise_parley`）—— 缺一条都不成；
  ② **门槛是按实测定标的**：plot 在位者 `slot.value` 的 p25/中位/p75 = 0.3053/0.3188/0.3314，
     门槛必须落在这个区间里 —— 既不恒成、也不恒不成；
  ③ **与暴力手段的后果真的不同**：谈成 ⇒ 席位空出来但**池子不变、不死人**；
     逐出 ⇒ `death_events` +1、池子少一个；
  ④ **没有打穿「游说」那条老路**：`plead` / `barter` 仍是不动世界的尝试法子 ——
     `core._attempt()` 在永劫回归期靠这一点保持轨迹不变。这条是**回归守卫**。
"""
from __future__ import annotations

import unittest

from _support import ROOT, state

from engine.disturbance import CAPABILITIES, dispatch
from engine.loader import Config
from engine.render import Renderer
from engine.services import default as default_services

#: 实测：plot 在位者的 slot.value 分位（见设计稿 2.4）
V_P25, V_MED, V_P75 = 0.3053, 0.3188, 0.3314


def _seated(ctx, seat=0, value=0.30, noise=0.10):
    """造一个【那一位已经有人坐】的状态（只用于判据测试，不跑演算）。"""
    st = state(ctx, 64, ["a"])
    k = st.pool.alloc()
    serial = int(st.pool.serial[k])
    st.register.slots[seat].owner = serial
    st.register.slots[seat].value = float(value)
    st.noise = float(noise)
    return st, k, serial


def _rec(cap, seat=0):
    return {"frame": 1, "channel": "world", "capability": cap,
            "selector": {"expr": "order:%d" % seat}, "payload": {}}


class ParleyCriteria(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = Config(ROOT)

    def test_empty_handed_seat_is_talked_round(self):
        """手里空 ⇒ 愿意给。"""
        st, _k, _s = _seated(self.ctx, value=V_P25)
        dispatch(_rec("parley"), st, self.ctx, 1)
        self.assertEqual(st.score.get("parley_granted"), 1.0)
        self.assertIsNone(st.register.slots[0].owner)

    def test_a_median_seat_can_be_talked_round(self):
        """实测中位那一席谈得成 —— 这条钉住「门槛落在分布里」，不是恒成 / 恒不成。"""
        st, _k, _s = _seated(self.ctx, value=V_MED)
        dispatch(_rec("parley"), st, self.ctx, 1)
        self.assertEqual(st.score.get("parley_granted"), 1.0)

    def test_a_full_handed_seat_refuses(self):
        """手里满 ⇒ 不肯给：席位一动不动。"""
        st, _k, serial = _seated(self.ctx, value=V_P75 + 0.05)
        dispatch(_rec("parley"), st, self.ctx, 1)
        self.assertEqual(st.score.get("parley_refused"), 1.0)
        self.assertEqual(st.register.slots[0].owner, serial)
        self.assertNotIn("parley_granted", st.score)

    def test_black_tide_blocks_the_parley(self):
        """黑潮压过谈判门 ⇒ 手里再空也谈不拢（「泰坦已丧失理智」）。"""
        st, _k, serial = _seated(self.ctx, value=V_P25, noise=99.0)
        dispatch(_rec("parley"), st, self.ctx, 1)
        self.assertEqual(st.score.get("parley_refused"), 1.0)
        self.assertEqual(st.register.slots[0].owner, serial)

    def test_empty_seat_is_left_alone(self):
        """空席上无所谓交涉 —— 既不记谈成也不记谈崩。"""
        st, _k, _s = _seated(self.ctx, value=V_P25)
        st.register.slots[0].owner = None
        dispatch(_rec("parley"), st, self.ctx, 1)
        self.assertNotIn("parley_granted", st.score)
        self.assertNotIn("parley_refused", st.score)

    def test_defaults_sit_inside_the_measured_distribution(self):
        """默认门槛必须落在实测的 p25 – p75 之间（既不恒成、也不恒不成）。"""
        tau = float(self.ctx.params["tau_parley"])
        self.assertGreater(tau, V_P25)
        self.assertLess(tau, V_P75)
        # 谈判门要在 plot 的黑潮之上（否则整个世界的和平手段一律失效）
        self.assertGreater(float(self.ctx.params["tau_noise_parley"]), 0.7083)


class ParleyVersusEviction(unittest.TestCase):
    """两条路的后果必须真的不同 —— 这是「伤亡账可核对」的前提。"""

    @classmethod
    def setUpClass(cls):
        cls.ctx = Config(ROOT)

    def test_parley_grants_without_killing(self):
        st, k, _serial = _seated(self.ctx, value=V_P25)
        alive = int(st.pool.alive.sum())
        dispatch(_rec("parley"), st, self.ctx, 1)
        self.assertIsNone(st.register.slots[0].owner)      # 席位空出来了
        self.assertTrue(bool(st.pool.alive[k]))            # 但那个人还活着
        self.assertEqual(int(st.pool.alive.sum()), alive)  # 池子没少人
        self.assertEqual(int(st.death_events), 0)

    def test_eviction_kills_the_incumbent(self):
        st, k, _serial = _seated(self.ctx, value=V_P25)
        alive = int(st.pool.alive.sum())
        dispatch(_rec("evict_holder"), st, self.ctx, 1)
        self.assertIsNone(st.register.slots[0].owner)
        self.assertFalse(bool(st.pool.alive[k]))           # 这个人没了
        self.assertEqual(int(st.pool.alive.sum()), alive - 1)
        self.assertEqual(int(st.death_events), 1)


class PleadStaysInert(unittest.TestCase):
    """回归守卫：`plead` / `barter` 必须仍然**不动世界一个比特**。

    `core._attempt()` 在永劫回归期把「游说」当作试探的第一种法子，而它试算后与参考
    结构的比对结果决定要不要留痕。**若这两个能力偷偷改了世界，整条招牌轨道的留痕
    判定就全变** —— 那正是本能力另起 `parley` 这个名字的原因。
    """

    @classmethod
    def setUpClass(cls):
        cls.ctx = Config(ROOT)

    def _assert_inert(self, cap):
        st, _k, serial = _seated(self.ctx)
        before = st.world_signature()
        dispatch(_rec(cap), st, self.ctx, 1)
        self.assertEqual(st.world_signature(), before, f"{cap} 动了世界")
        self.assertEqual(st.register.slots[0].owner, serial)

    def test_plead_is_inert(self):
        self._assert_inert("plead")

    def test_barter_is_inert(self):
        self._assert_inert("barter")


class EmberLedger(unittest.TestCase):
    """火种账本：暴力夺取记一笔 `embers_taken`；和平归还记 `embers_returned`。

    **这是两种手段唯一的分别** —— 而它真的参与因果：`Promotion` 拿 `embers_taken`
    抬高再创世门槛（「集齐火种才能再创世」⇒「火种被夺走，终点被推远」）。
    实测（`plot-mech`：6 逐出 + 1 交涉 vs 全暴力 7 逐出）⇒ 换代 **58 / 56**、
    迭代 **47,487 / 43,167** ⇒ **和平逐火与血战逐火走向不同的世界**。
    """

    @classmethod
    def setUpClass(cls):
        cls.ctx = Config(ROOT)

    def test_eviction_records_a_taken_ember(self):
        st, _k, _s = _seated(self.ctx, value=V_P25)
        dispatch(_rec("evict_holder"), st, self.ctx, 7)
        self.assertEqual(st.score.get("embers_taken"), 1.0)
        self.assertEqual(st.score.get("evicted"), 1.0)

    def test_parley_records_a_returned_ember(self):
        st, _k, _s = _seated(self.ctx, value=V_P25)
        dispatch(_rec("parley"), st, self.ctx, 7)
        self.assertEqual(st.score.get("embers_returned"), 1.0)
        self.assertNotIn("embers_taken", st.score)

    def test_a_refused_parley_records_nothing(self):
        """谈崩了不算归还，也不算夺取 —— 席位一动不动。"""
        st, _k, serial = _seated(self.ctx, value=V_P75 + 0.05)
        dispatch(_rec("parley"), st, self.ctx, 7)
        self.assertNotIn("embers_returned", st.score)
        self.assertNotIn("embers_taken", st.score)
        self.assertEqual(st.register.slots[0].owner, serial)

    def test_an_empty_seat_takes_no_ember(self):
        """空席上无所谓夺取 —— 账本不该记这一笔。"""
        st, _k, _s = _seated(self.ctx, value=V_P25)
        st.register.slots[0].owner = None
        dispatch(_rec("evict_holder"), st, self.ctx, 7)
        self.assertNotIn("embers_taken", st.score)


class ConfigIsNotMutated(unittest.TestCase):
    """★ 回归守卫：`State` 不许持有 `cfg.loci`。

    本账本一度改过 `locus.capacity`（想让"位被破坏"参与动力学，实测无效已撤），
    那时才发现 [`State.__init__`](../../engine/state.py) 里 `self.loci = loci` 是
    **共享引用** —— 于是同一个 `Config` 上的第二次 run 会带着被上一次改烂的位表开始。
    现在虽已不削 capacity，但「State 不持有调用方对象」这条契约仍须守住。
    """

    def _run_twice(self):
        import json
        import os
        import tempfile

        from _support import ROOT, temp_root_with_copy

        from engine.conditions import evaluate
        from engine.core import run
        from engine.loader import Config, DataSet

        with tempfile.TemporaryDirectory() as tmp:
            root = temp_root_with_copy(tmp)
            d = os.path.join(root, "presets", "t")
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "preset.json"), "w", encoding="utf-8") as f:
                json.dump({"name": "t", "seed": 0}, f)
            with open(os.path.join(d, "events.jsonl"), "w", encoding="utf-8") as f:
                f.write(json.dumps({"frame": 300, "channel": "world",
                                    "capability": "evict_holder",
                                    "selector": {"expr": "order:3"},
                                    "payload": {}}, ensure_ascii=False) + "\n")
            ctx = Config(root)
            data = DataSet(root, preset="t")
            before = [float(l.capacity) for l in ctx.loci]
            first = run(ctx, data, seed=0, max_frames=400, rules=evaluate,
                        runtime=default_services())
            after = [float(l.capacity) for l in ctx.loci]
            second = run(ctx, data, seed=0, max_frames=400, rules=evaluate,
                         runtime=default_services())
            return first, second, before, after

    def test_config_loci_survive_the_run(self):
        _a, _b, before, after = self._run_twice()
        self.assertEqual(before, after, "cfg.loci 被演算改掉了")

    def test_repeated_runs_agree(self):
        """同一份 Config 连跑两次必须逐位一致 —— 跨 run 污染的最终判据。"""
        first, second, _before, _after = self._run_twice()
        self.assertEqual(first.final.digest(), second.final.digest())


class ParleyRegistry(unittest.TestCase):
    def test_capability_is_registered(self):
        self.assertIn("parley", CAPABILITIES)

    def test_thresholds_are_stage_tunable(self):
        """旋钮必须进白名单 —— 否则写了也没人读（那正是这类项目最容易烂掉的地方）。"""
        from engine.operators import STAGE_TUNABLE
        self.assertIn("tau_parley", STAGE_TUNABLE)
        self.assertIn("tau_noise_parley", STAGE_TUNABLE)

    def test_it_has_a_rendering_name(self):
        """渲染层查得到中文名 —— 编年史里不许出现裸的 `parley`。"""
        R = Renderer(Config(ROOT))
        self.assertEqual(R.capability("parley"), "交涉归还")
        self.assertNotEqual(R.capability("parley"), "parley")


if __name__ == "__main__":
    unittest.main()