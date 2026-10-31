"""origin 世界：13 席 / meta / 真实 origin 状态 / 回望锚点固定点。

这些测试只跑很短的一段，且把 `ablation_period` 推到极大 —— 探针在别处已有覆盖，
这里要验的是「第十三席是不是真的动力学」。
"""
from __future__ import annotations

import json
import os
import unittest

import numpy as np

from _support import ROOT

from apps.conditions import evaluate
from apps.origin_loop import Planner, _missing_of, load_nodes
from apps.services import default as default_services
from apps.verdicts import inner_conclusion
from kernel.api import load
from kernel.disturbance import dispatch
from kernel.loader import Config, DataSet
from kernel.operators import Drift, Occupy, Origin, MEMORY_OWNER, Paths
from kernel.state import State

ORIGIN_ROOT = os.path.join(ROOT, "worlds", "origin")
DOMAIN = ["inorganic", "organic", "human"]


def _ctx(preset="origin"):
    data = DataSet(ORIGIN_ROOT, preset=preset)
    ctx = Config(ORIGIN_ROOT, lex_overlay=data.preset.get("lexicon"))
    data.apply_params(ctx)                       # 分支预设的参数覆盖
    ctx.params["ablation_period"] = 10 ** 9      # 测试不跑消融探针
    return ctx, data


def _state(ctx, cap=64):
    return State(ctx.loci, int(ctx.params["dim"]),
                 int(ctx.params["observables"]), cap, list(DOMAIN))


def _norm(v):
    v = np.asarray(v, dtype=np.float32)
    return (v / float(v.sum())).astype(np.float32)


def _seat(st, i, vec, serial=None):
    slot = st.register.slots[i]
    slot.owner = int(serial) if serial is not None else -1
    slot.vector = _norm(vec)
    slot.value = float(slot.vector[i])
    return slot


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.ctx, self.data = _ctx()

    def test_thirteen_seats(self):
        self.assertEqual(int(self.ctx.params["dim"]), 13)
        self.assertEqual(len(self.ctx.loci), 13)
        self.assertTrue(self.ctx.loci[-1].meta)
        self.assertFalse(any(l.meta for l in self.ctx.loci[:-1]))
        self.assertEqual(len(self.ctx.params["capability_names"]), 13)
        self.assertEqual(self.ctx.mapping.shape, (13, self.ctx.params["observables"]))
        self.assertEqual(len(self.ctx.phonology["machine_stems"]), 13)
        self.assertIn("L12", self.ctx.phonology["title_calibration"])
        self.assertIn("L12", self.ctx.lexicon["regions"])

    def test_preset_data(self):
        self.assertTrue(self.data.assertions)
        self.assertTrue(load_nodes(ORIGIN_ROOT, "origin"))
        self.assertGreaterEqual(len(load_nodes(ORIGIN_ROOT, "origin")), 3)

    def test_canonical_still_twelve(self):
        with open(os.path.join(ROOT, "config", "params.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["dim"], 12)
        with open(os.path.join(ROOT, "config", "loci.json"), encoding="utf-8") as f:
            self.assertFalse(any(l.get("meta") for l in json.load(f)["loci"]))


class MetaLocusTest(unittest.TestCase):
    def setUp(self):
        self.ctx, _ = _ctx()

    def test_complete_ignores_meta(self):
        st = _state(self.ctx, cap=16)
        for i in range(12):
            _seat(st, i, [0.05] * 12 + [0.0])
        self.assertEqual(st.register.vacant(), [])
        self.assertEqual(st.register.vacant(include_meta=True), [12])
        self.assertTrue(st.register.complete())

    def test_meta_vacant_alone_is_not_vacant(self):
        st = _state(self.ctx, cap=16)
        for i in range(12):
            _seat(st, i, [0.05] * 12 + [0.0])
        self.assertNotIn(12, st.register.vacant())


class OriginStateTest(unittest.TestCase):
    def setUp(self):
        self.ctx, _ = _ctx()
        self.st = _state(self.ctx, cap=16)
        for i in range(12):
            _seat(self.st, i, [0.05] * 13)
        _seat(self.st, 12, [0.02] * 12 + [0.6])
        self.st.origin.ever = True
        self.st.origin.filled = True
        self.st.origin.energy = 3.0
        self.st.origin.selfhood = 0.4

    def test_signature_only_structural(self):
        before = self.st.world_signature()
        self.st.origin.energy = 9.0
        self.st.origin.selfhood = 0.9
        self.assertEqual(self.st.world_signature(), before)
        self.st.origin.filled = False
        self.assertNotEqual(self.st.world_signature(), before)

    def test_clone_and_digest(self):
        clone = self.st.clone()
        self.assertEqual(clone.digest(), self.st.digest())
        self.assertTrue(clone.origin.ever)
        self.assertAlmostEqual(clone.origin.energy, 3.0)

    def test_copy_world_from_rolls_origin(self):
        other = self.st.clone()
        other.origin.closure = 1
        other.origin.repaid = 2
        self.st.copy_world_from(other)
        self.assertEqual(self.st.origin.closure, 1)
        self.assertEqual(self.st.origin.repaid, 2)


class OriginOperatorTest(unittest.TestCase):
    def setUp(self):
        self.ctx, _ = _ctx()
        self.st = _state(self.ctx, cap=16)
        self.i = self.st.pool.alloc()
        self.st.pool.factor[self.i] = 12
        self.st.pool.born[self.i] = 0
        self.st.pool.vec[self.i] = _norm([0.02] * 12 + [0.5])
        _seat(self.st, 12, self.st.pool.vec[self.i],
              serial=int(self.st.pool.serial[self.i]))
        self.st.origin.awake = True          # 这些用例验的是苏醒后的动力学
        self.st.origin.form = 1

    def test_dormant_until_woken(self):
        st = _state(self.ctx, cap=8)
        i = st.pool.alloc()
        st.pool.factor[i] = 12
        st.pool.born[i] = 0
        st.pool.vec[i] = _norm([0.02] * 12 + [0.5])
        _seat(st, 12, st.pool.vec[i], serial=int(st.pool.serial[i]))
        for f in range(5):
            Origin().apply(st, self.ctx, np.random.default_rng(f), f)
        self.assertFalse(st.origin.awake)
        self.assertFalse(st.origin.ever)
        self.assertFalse(st.origin.filled)
        self.assertEqual(st.origin.form, 0)

    def test_external_resonance_wakes_dormant_origin(self):
        st = _state(self.ctx, cap=8)
        i = st.pool.alloc()
        st.pool.factor[i] = 12
        st.pool.born[i] = 0
        st.pool.vec[i] = _norm([0.02] * 12 + [0.5])
        _seat(st, 12, st.pool.vec[i], serial=int(st.pool.serial[i]))
        ext = _norm([0.02] * 12 + [0.6])
        _seat(st, 0, ext, serial=-2)
        self.assertFalse(st.origin.awake)
        Origin().apply(st, self.ctx, np.random.default_rng(0), 0)
        self.assertTrue(st.origin.awake)
        self.assertEqual(st.origin.form, 1)
        self.assertGreaterEqual(st.origin.resonance,
                                self.ctx.params["origin_resonance_threshold"])
        self.assertEqual(st.origin.resonance_host, -2)
        self.assertGreater(st.score.get("origin_resonance_wake", 0.0), 0.0)

    def test_auto_wake_frame(self):
        st = _state(self.ctx, cap=8)
        i = st.pool.alloc()
        st.pool.factor[i] = 12
        st.pool.born[i] = 0
        st.pool.vec[i] = _norm([0.02] * 12 + [0.5])
        _seat(st, 12, st.pool.vec[i], serial=int(st.pool.serial[i]))
        auto = int(self.ctx.params["origin_auto_wake_frame"])
        Origin().apply(st, self.ctx, np.random.default_rng(0), auto - 1)
        self.assertFalse(st.origin.awake)
        Origin().apply(st, self.ctx, np.random.default_rng(0), auto)
        self.assertTrue(st.origin.awake)
        self.assertEqual(st.origin.form, 1)

    def test_forms_and_accumulates(self):
        op = Origin()
        for f in range(5):
            op.apply(self.st, self.ctx, np.random.default_rng(f), f)
        self.assertTrue(self.st.origin.ever)
        self.assertTrue(self.st.origin.filled)
        self.assertGreater(self.st.origin.selfhood, self.ctx.params["tau_origin"])
        self.assertGreater(self.st.origin.energy, 0.0)

    def test_dissolves_when_selfhood_low(self):
        self.st.origin.ever = True
        self.st.origin.filled = True
        self.st.register.slots[12].vector = _norm([1.0] * 12 + [0.0001])
        dwell = int(self.ctx.params["origin_dissolve_dwell"])
        for f in range(dwell + 1):
            Origin().apply(self.st, self.ctx, np.random.default_rng(f), f)
        self.assertIsNone(self.st.register.slots[12].owner)

    def test_creation_fills_a_empty_seat(self):
        self.st.origin.ever = True
        self.st.origin.filled = True
        self.st.origin.form = 2
        self.st.origin.energy = 50.0
        # 一个真正的空席 + 一个不在席上的候选体
        j = self.st.pool.alloc()
        self.st.pool.factor[j] = 3
        self.st.pool.born[j] = 0
        self.st.pool.vec[j] = _norm([0.05] * 13)
        Origin().apply(self.st, self.ctx, np.random.default_rng(0), 0)
        self.assertIsNotNone(self.st.register.slots[0].owner)
        self.assertGreater(self.st.score.get("origin_create", 0.0), 0.0)

    def test_factor_memory_enables_companion(self):
        # 一个真实的在位者，供忆灵依附
        h = self.st.pool.alloc()
        self.st.pool.factor[h] = 0
        self.st.pool.born[h] = 0
        self.st.pool.vec[h] = _norm([0.1] * 13)
        _seat(self.st, 0, self.st.pool.vec[h],
              serial=int(self.st.pool.serial[h]))
        host = int(self.st.pool.serial[h])
        # 先成形
        Origin().apply(self.st, self.ctx, np.random.default_rng(0), 0)
        self.assertTrue(self.st.origin.ever)
        self.assertEqual(self.st.origin.form, 1)
        self.st.origin.energy = 10.0
        self.st.origin.age = int(self.ctx.params["origin_companion_age"]) - 1
        dispatch({"capability": "origin_anchor",
                  "payload": {"action": "seed_memory", "mode": "factor_basis",
                              "cost": 0.5}},
                 self.st, self.ctx, 10)
        self.assertEqual(self.st.origin.factor_rows, 12)
        self.assertAlmostEqual(self.st.origin.factor_rows / 12.0, 1.0)
        Origin().apply(self.st, self.ctx, np.random.default_rng(1), 11)
        self.assertEqual(self.st.origin.form, 2)
        self.assertGreater(self.st.score.get("origin_companion", 0.0), 0.0)
        self.assertGreaterEqual(self.st.origin.companion_serial, 0)
        self.assertGreaterEqual(
            self.st.pool.index_of_serial(self.st.origin.companion_serial), 0)
        self.assertGreater(self.st.score.get("origin_companion_spawn", 0.0), 0.0)
        self.assertEqual(self.st.origin.companion_host, host)
        self.assertGreater(self.st.score.get("origin_attach", 0.0), 0.0)

    # ---- 忆灵自己的成长阶段 -------------------------------------------------
    def _with_companion(self):
        """原初凝成忆灵并依附到外部变量（-2）的最小真实场景。"""
        st = _state(self.ctx, cap=8)
        i = st.pool.alloc()
        st.pool.factor[i] = 12
        st.pool.born[i] = 0
        st.pool.vec[i] = _norm([0.02] * 12 + [0.5])
        _seat(st, 12, st.pool.vec[i], serial=int(st.pool.serial[i]))
        _seat(st, 0, _norm([0.02] * 12 + [0.6]), serial=-2)
        st.origin.awake = True
        st.origin.form = 2
        st.origin.ever = True
        st.origin.filled = True
        st.origin.energy = 50.0
        Origin().apply(st, self.ctx, np.random.default_rng(0), 0)
        return st

    @staticmethod
    def _seed_savior(st, ctx, mid, frame):
        dispatch({"capability": "origin_anchor",
                  "payload": {"action": "seed_memory", "mode": "savior",
                              "memory": {"id": mid, "label": mid,
                                         "effect": "fitness", "magnitude": 0.1},
                              "cost": 0.5}},
                 st, ctx, frame)

    def test_companion_grows_through_stages(self):
        st = self._with_companion()
        self.assertEqual(st.origin.companion_stage, 1)
        self.assertGreaterEqual(st.origin.companion_serial, 0)
        # 第一段记忆真正转印 ⇒ 下一帧 carry 记为 1，够到「同行」的年龄门槛就长一级
        self._seed_savior(st, self.ctx, "m1", 10)
        Origin().apply(st, self.ctx, np.random.default_rng(1), 11)
        self.assertTrue(st.origin.memory_fragments[0].transferred)
        Origin().apply(st, self.ctx, np.random.default_rng(1), 12)
        self.assertEqual(st.origin.companion_carry, 1)
        st.origin.companion_age = int(
            self.ctx.params["origin_companion_stage2_age"])
        Origin().apply(st, self.ctx, np.random.default_rng(2), 13)
        self.assertEqual(st.origin.companion_stage, 2)
        self.assertIn("emitted_origin_companion_grow", st.score)
        # 第二段记忆 ⇒ carry 2，够到「承忆」的年龄门槛
        self._seed_savior(st, self.ctx, "m2", 20)
        Origin().apply(st, self.ctx, np.random.default_rng(3), 21)
        Origin().apply(st, self.ctx, np.random.default_rng(3), 22)
        self.assertEqual(st.origin.companion_carry, 2)
        st.origin.companion_age = int(
            self.ctx.params["origin_companion_stage3_age"])
        Origin().apply(st, self.ctx, np.random.default_rng(4), 23)
        self.assertEqual(st.origin.companion_stage, 3)
        self.assertGreater(st.score.get("origin_companion_grow", 0.0), 0.0)

    def test_companion_keeps_memory_seat_when_origin_is_broke(self):
        # 忆灵还没长到「同行」：原初没能量就守不住这一席
        st = self._with_companion()
        st.memory_seats.add(3)
        st.origin.energy = 0.0
        Origin().apply(st, self.ctx, np.random.default_rng(1), 1)
        self.assertIsNone(st.register.slots[3].owner)
        # 「同行」之后，忆灵自己替原初守住这一席，不耗原初能量
        st.origin.companion_stage = 2
        Origin().apply(st, self.ctx, np.random.default_rng(2), 2)
        self.assertEqual(st.register.slots[3].owner, MEMORY_OWNER)
        self.assertGreater(st.score.get("origin_companion_rebind", 0.0), 0.0)
        self.assertIn("emitted_origin_companion_rebind", st.score)
        self.assertNotIn("emitted_origin_memory_rebound", st.score)

    def test_companion_rebonds_to_a_new_host_at_stage_three(self):
        st = self._with_companion()
        self._seed_savior(st, self.ctx, "m1", 10)
        Origin().apply(st, self.ctx, np.random.default_rng(1), 11)
        # 另备两个真实在位者，供忆灵在宿主离席后继续往前走
        hosts = []
        for seat, factor in ((1, 1), (2, 2)):
            j = st.pool.alloc()
            st.pool.factor[j] = factor
            st.pool.born[j] = 0
            st.pool.vec[j] = _norm([0.1] * 13)
            _seat(st, seat, st.pool.vec[j],
                  serial=int(st.pool.serial[j]))
            hosts.append(int(st.pool.serial[j]))
        st.register.slots[0].owner = None            # 原宿主离席
        # 「同行」：换宿主，但还不会把记忆完整再印一次
        st.origin.companion_stage = 2
        Origin().apply(st, self.ctx, np.random.default_rng(2), 12)
        first = int(st.origin.companion_host)
        self.assertIn(first, hosts)
        self.assertEqual(st.score.get("origin_companion_rebond", 0.0), 0.0)
        # 「承忆」：宿主真的死了，忆灵换到另一位并把随身那段记忆完整再印一次
        st.origin.companion_stage = 3
        dead = st.pool.index_of_serial(first)
        if dead >= 0:
            st.pool.kill(dead)
        for slot in st.register.slots:
            if slot.owner is not None and int(slot.owner) == first:
                slot.owner = None
        Origin().apply(st, self.ctx, np.random.default_rng(3), 13)
        self.assertNotEqual(int(st.origin.companion_host), first)
        self.assertGreaterEqual(st.origin.companion_bond, 3)
        self.assertGreater(st.score.get("origin_companion_rebond", 0.0), 0.0)
        self.assertIn("emitted_origin_companion_rebond", st.score)

    def test_companion_becomes_eminence_and_holds_the_seat(self):
        st = self._with_companion()
        self._seed_savior(st, self.ctx, "m1", 10)
        self._seed_savior(st, self.ctx, "m2", 10)
        Origin().apply(st, self.ctx, np.random.default_rng(1), 11)
        Origin().apply(st, self.ctx, np.random.default_rng(1), 12)
        self.assertEqual(st.origin.companion_carry, 2)
        self.assertTrue(st.origin.savior_transferred)
        st.origin.companion_age = int(
            self.ctx.params["origin_companion_stage4_age"])
        Origin().apply(st, self.ctx, np.random.default_rng(2), 13)
        self.assertEqual(st.origin.companion_stage, 4)
        # 「忆者」自己占记忆承载席：原初没能量也照守
        st.memory_seats.add(3)
        st.origin.energy = 0.0
        Origin().apply(st, self.ctx, np.random.default_rng(3), 14)
        self.assertEqual(st.register.slots[3].owner,
                         int(st.origin.companion_serial))
        self.assertGreater(st.score.get("origin_companion_seat", 0.0), 0.0)
        self.assertIn("emitted_origin_companion_seat", st.score)

    def test_suppression_spares_eminence_held_seat(self):
        st = self._with_companion()
        comp = int(st.origin.companion_serial)
        k = st.pool.index_of_serial(comp)
        st.memory_seats.add(1)
        st.register.slots[1].owner = comp
        st.register.slots[1].vector = st.pool.vec[k].copy()
        st.suppressed.add(1)
        Occupy().apply(st, self.ctx, np.random.default_rng(0), 1)
        self.assertEqual(st.register.slots[1].owner, comp)
        self.assertIn("emitted_origin_memory_seal_resisted", st.score)

    def test_gaze_lifts_selfhood_for_a_window(self):
        Origin().apply(self.st, self.ctx, np.random.default_rng(0), 0)
        base = float(self.st.origin.selfhood)
        self.assertGreater(base, 0.0)
        self.st.actors["external_x"] = {"label": "", "grants": (), "state": {}}
        dispatch({"capability": "gaze",
                  "selector": None,
                  "payload": {"actor": "external_x",
                              "effect": {"origin": True, "duration": 10}}},
                 self.st, self.ctx, 5)
        self.assertEqual(self.st.origin.gaze_until, 15)
        self.assertIn("emitted_origin_gazed", self.st.score)
        Origin().apply(self.st, self.ctx, np.random.default_rng(1), 6)
        boosted = float(self.st.origin.selfhood)
        self.assertGreater(boosted, base)
        # 目光移开之后，读数回到原本的那一份
        Origin().apply(self.st, self.ctx, np.random.default_rng(2), 20)
        self.assertLess(float(self.st.origin.selfhood), boosted)

    def test_black_tide_takes_the_seat_and_memory_reclaims_it(self):
        st = self._with_companion()
        st.memory_seats.add(1)
        st.register.slots[1].owner = MEMORY_OWNER
        st.register.slots[1].vector = _norm([0.05] * 13)
        dispatch({"capability": "evict_holder",
                  "selector": {"expr": "order:1"}, "payload": {}},
                 st, self.ctx, 5)
        self.assertIsNone(st.register.slots[1].owner)
        self.assertIn("emitted_seat_seized", st.score)
        Origin().apply(st, self.ctx, np.random.default_rng(1), 6)
        self.assertEqual(st.register.slots[1].owner, MEMORY_OWNER)
        self.assertIn("emitted_origin_seat_reclaimed", st.score)

    def test_savior_memory_capture_and_transfer(self):
        st = _state(self.ctx, cap=8)
        i = st.pool.alloc()
        st.pool.factor[i] = 12
        st.pool.born[i] = 0
        st.pool.vec[i] = _norm([0.02] * 12 + [0.5])
        _seat(st, 12, st.pool.vec[i], serial=int(st.pool.serial[i]))
        ext = _norm([0.02] * 12 + [0.6])
        _seat(st, 0, ext, serial=-2)
        st.origin.awake = True
        st.origin.form = 2
        st.origin.ever = True
        st.origin.filled = True
        st.origin.energy = 50.0
        Origin().apply(st, self.ctx, np.random.default_rng(0), 0)
        self.assertGreaterEqual(st.origin.companion_serial, 0)
        current = st.register.slots[0].vector.copy()   # 忆灵已经印过一次
        before_value = float(st.register.slots[0].value)
        dispatch({"capability": "origin_anchor",
                  "payload": {"action": "seed_memory", "mode": "savior",
                              "memory": {"id": "savior", "label": "救世主记忆",
                                         "effect": "fitness", "magnitude": 0.5},
                              "cost": 0.5}},
                 st, self.ctx, 10)
        self.assertTrue(st.origin.savior_active)
        self.assertIsNotNone(st.origin.savior_vector)
        np.testing.assert_allclose(st.origin.savior_vector, current,
                                   rtol=1e-5, atol=1e-6)
        self.assertEqual(len(st.origin.memory_fragments), 1)
        frag = st.origin.memory_fragments[0]
        self.assertEqual(frag.label, "救世主记忆")
        self.assertEqual(frag.effect, "fitness")
        self.assertAlmostEqual(frag.magnitude, 0.5)
        Origin().apply(st, self.ctx, np.random.default_rng(1), 11)
        self.assertTrue(st.origin.savior_transferred)
        self.assertTrue(frag.transferred)
        self.assertGreater(st.score.get("origin_savior_transfer", 0.0), 0.0)
        self.assertGreater(st.score.get("origin_memory_transfer", 0.0), 0.0)
        self.assertGreater(float(st.register.slots[0].value), before_value)

    def _prepared_with_fragment(self, effect, magnitude=0.3,
                                sustain=False, rate=0.0, phases=None):
        st = _state(self.ctx, cap=8)
        i = st.pool.alloc()
        st.pool.factor[i] = 12
        st.pool.born[i] = 0
        st.pool.vec[i] = _norm([0.02] * 12 + [0.5])
        _seat(st, 12, st.pool.vec[i], serial=int(st.pool.serial[i]))
        _seat(st, 0, _norm([0.02] * 12 + [0.6]), serial=-2)
        st.origin.awake = True
        st.origin.form = 2
        st.origin.ever = True
        st.origin.filled = True
        st.origin.energy = 50.0
        Origin().apply(st, self.ctx, np.random.default_rng(0), 0)
        dispatch({"capability": "origin_anchor",
                  "payload": {"action": "seed_memory", "mode": "savior",
                              "memory": {"id": "m_" + effect, "label": effect,
                                         "effect": effect, "magnitude": magnitude,
                                         "sustain": sustain, "rate": rate,
                                         "phases": phases},
                              "cost": 0.5}},
                 st, self.ctx, 10)
        return st

    def test_memory_effect_selfhood_lifts_origin(self):
        st = self._prepared_with_fragment("selfhood", 0.2)
        before = float(st.register.slots[12].vector[12]) / float(
            st.register.slots[12].vector.sum())
        Origin().apply(st, self.ctx, np.random.default_rng(1), 11)
        after = float(st.register.slots[12].vector[12]) / float(
            st.register.slots[12].vector.sum())
        self.assertGreater(after, before)

    def test_memory_effect_coupling_and_mutation_are_read_by_drift(self):
        for effect, attr in (("coupling", "memory_coupling_gain"),
                             ("mutation", "memory_mutation_damp")):
            st = self._prepared_with_fragment(effect, 0.3)
            plain = st.clone()
            Origin().apply(st, self.ctx, np.random.default_rng(1), 11)
            self.assertAlmostEqual(getattr(st.origin, attr), 0.3)
            self.assertGreater(getattr(st.origin,
                                       attr.replace("_gain", "_until")
                                       .replace("_damp", "_until")), 11)
            Drift().apply(st, self.ctx, np.random.default_rng(7), 12)
            Drift().apply(plain, self.ctx, np.random.default_rng(7), 12)
            self.assertFalse(np.allclose(st.pool.vec[0], plain.pool.vec[0]))

    def test_sustained_memory_field_accumulates(self):
        st = self._prepared_with_fragment("fitness", 0.1, sustain=True, rate=0.1)
        frag = st.origin.memory_fragments[0]
        before = float(st.register.slots[0].value)
        Origin().apply(st, self.ctx, np.random.default_rng(1), 11)
        v1 = float(st.register.slots[0].value)
        Origin().apply(st, self.ctx, np.random.default_rng(2), 12)
        v2 = float(st.register.slots[0].value)
        self.assertGreater(v1, before)
        self.assertGreater(v2, v1)
        self.assertGreaterEqual(frag.ticks, 1)
        self.assertGreater(st.score.get("origin_memory_tick", 0.0), 0.0)

    def test_memory_phases_advance(self):
        phases = [
            {"label": "一", "effect": "fitness", "magnitude": 0.1,
             "duration": 2, "sustain": False},
            {"label": "二", "effect": "selfhood", "magnitude": 0.1,
             "duration": 0, "sustain": False},
        ]
        st = self._prepared_with_fragment("fitness", 0.1, phases=phases)
        frag = st.origin.memory_fragments[0]
        self.assertEqual(len(frag.phases), 2)
        Origin().apply(st, self.ctx, np.random.default_rng(1), 11)
        self.assertEqual(frag.phase_index, 0)
        Origin().apply(st, self.ctx, np.random.default_rng(2), 13)
        self.assertEqual(frag.phase_index, 1)
        self.assertGreaterEqual(st.score.get("origin_memory_phase", 0.0), 1.0)
        self.assertEqual(frag.phases[frag.phase_index]["label"], "二")

    def test_memory_effect_memory_seat_marks_host(self):
        st = self._prepared_with_fragment("memory_seat", 0.0)
        Origin().apply(st, self.ctx, np.random.default_rng(1), 11)
        self.assertIn(0, st.memory_seats)

    def test_trailblaze_breaks_stagnation(self):
        self.st.origin.ever = True
        self.st.origin.filled = True
        self.st.origin.energy = 50.0
        dwell = int(self.ctx.params["origin_trailblaze_dwell"])
        before_solver = self.st.solver
        before_gates = set(self.st.gates)
        # 把「结构签名」钉成上一帧的样子，并让停滞计数只差最后一帧。
        self.st.domains_exhausted = True
        self.st.origin.last_sig = self.st.world_signature()
        self.st.origin.stagnant_run = dwell - 1
        Origin().apply(self.st, self.ctx, np.random.default_rng(0), 0)
        self.assertTrue(self.st.solver != before_solver
                        or set(self.st.gates) != before_gates)
        self.assertGreater(self.st.score.get("origin_trailblaze", 0.0), 0.0)

    def test_love_window_is_real_for_drift(self):
        a = self.st.clone()
        b = self.st.clone()
        a.origin.love_until = 0
        b.origin.love_until = 10
        Drift().apply(a, self.ctx, np.random.default_rng(7), 3)
        Drift().apply(b, self.ctx, np.random.default_rng(7), 3)
        self.assertFalse(np.allclose(a.pool.vec[self.i], b.pool.vec[self.i]))


class OriginAnchorTest(unittest.TestCase):
    def setUp(self):
        self.ctx, _ = _ctx()
        self.st = _state(self.ctx, cap=16)
        i = self.st.pool.alloc()
        self.st.pool.factor[i] = 12
        self.st.pool.born[i] = 0
        self.st.pool.vec[i] = _norm([0.02] * 12 + [0.5])
        _seat(self.st, 12, self.st.pool.vec[i],
              serial=int(self.st.pool.serial[i]))
        self.st.origin.awake = True
        self.st.origin.form = 1
        self.st.origin.ever = True
        self.st.origin.filled = True
        self.st.origin.energy = 10.0

    def _fire(self, payload, frame=10):
        dispatch({"capability": "origin_anchor", "payload": payload},
                 self.st, self.ctx, frame)

    def test_bind_memory_fills_and_releases(self):
        self.st.suppressed.add(3)
        self._fire({"action": "bind_memory", "seat": "L03", "cost": 0.5})
        self.assertEqual(self.st.register.slots[3].owner, MEMORY_OWNER)
        self.assertNotIn(3, self.st.suppressed)
        self.assertEqual(self.st.origin.borrowed, 1)
        self.assertEqual(self.st.origin.repaid, 1)

    def test_bind_participant_can_read_actor_table(self):
        vec = _norm([0.02] * 12 + [0.6])
        self.st.actors["external_x"] = {"label": "", "grants": (), "state": {},
                                        "vector": vec.tolist(), "attrs": {}}
        dispatch({"capability": "bind_participant",
                  "selector": {"expr": "order:0"},
                  "payload": {"participant": -2, "actor": "external_x"}},
                 self.st, self.ctx, 1)
        self.assertEqual(self.st.register.slots[0].owner, -2)
        np.testing.assert_allclose(self.st.register.slots[0].vector, vec,
                                   rtol=1e-6, atol=1e-6)

    def test_bind_participant_can_carry_attributes(self):
        vec = _norm([0.02] * 12 + [0.6])
        dispatch({"capability": "bind_participant",
                  "selector": {"expr": "order:0"},
                  "payload": {"participant": -2, "vector": vec.tolist()}},
                 self.st, self.ctx, 1)
        self.assertEqual(self.st.register.slots[0].owner, -2)
        np.testing.assert_allclose(self.st.register.slots[0].vector, vec,
                                   rtol=1e-6, atol=1e-6)

    def test_bind_uses_its_own_row_and_resists_seal(self):
        self._fire({"action": "seed_memory", "mode": "factor_basis", "cost": 0.5}, 5)
        row5 = self.st.memory_bank[5].copy()
        self._fire({"action": "bind_memory", "seat": "L05", "cost": 0.5}, 6)
        np.testing.assert_array_equal(self.st.register.slots[5].vector, row5)
        self.assertIn(5, self.st.memory_seats)
        # 记忆承载席抵抗外部封印：Occupy 不会把它清空。
        self.st.suppressed.add(5)
        Occupy().apply(self.st, self.ctx, np.random.default_rng(0), 7)
        self.assertEqual(self.st.register.slots[5].owner, MEMORY_OWNER)

    def test_seed_memory_and_open_gate(self):
        self._fire({"action": "seed_memory", "seat": "L05", "cost": 0.5})
        self.assertGreater(self.st.memory_bank.shape[0], 0)
        self._fire({"action": "open_gate", "gate": "OP_BIFURCATE", "cost": 0.5})
        self.assertIn("OP_BIFURCATE", self.st.gates)

    def test_refused_before_origin_forms(self):
        st = _state(self.ctx, cap=8)
        dispatch({"capability": "origin_anchor",
                  "payload": {"action": "bind_memory", "seat": "L01", "cost": 0.5}},
                 st, self.ctx, 5)
        self.assertEqual(st.origin.borrowed, 1)
        self.assertEqual(st.origin.repaid, 0)
        self.assertIsNone(st.register.slots[1].owner)


class UnreachableTest(unittest.TestCase):
    def setUp(self):
        self.ctx, self.data = _ctx()
        self.st = _state(self.ctx, cap=8)

    def test_node_before_origin_is_unreachable(self):
        node = {"frame": 5, "seat": "L00", "missing": "vacant",
                "repair": "bind_memory"}
        snap = {"filled": (False,) * 13, "memory_rows": 0,
                "gates": frozenset(), "events": frozenset(),
                "selfhood": 0.0, "solver": "OP_SOLVE_ENTROPY"}
        miss, why = _missing_of(node, snap, 100, self.st, 0.05)
        self.assertTrue(miss)
        self.assertEqual(why, "unreachable")

    def test_build_prepends_wake_origin(self):
        planner = Planner(self.ctx, self.data, 0, frames=100)
        node = {"id": "N", "frame": 5, "seat": "L00", "missing": "vacant",
                "repair": "bind_memory", "cost": 0.5}
        recs = planner._build([{"node": node, "unreachable": True}])
        self.assertEqual([r["payload"]["action"] for r in recs],
                         ["wake_origin", "bind_memory"])

    def test_wake_lifts_an_occupied_but_unformed_seat(self):
        i = self.st.pool.alloc()
        self.st.pool.factor[i] = 12
        self.st.pool.born[i] = 0
        self.st.pool.vec[i] = _norm([0.07] * 13)
        _seat(self.st, 12, self.st.pool.vec[i],
              serial=int(self.st.pool.serial[i]))
        self.assertFalse(self.st.origin.ever)
        dispatch({"capability": "origin_anchor",
                  "payload": {"action": "wake_origin", "cost": 0.6}},
                 self.st, self.ctx, 5)
        self.assertTrue(self.st.origin.ever)
        self.assertTrue(self.st.origin.filled)
        self.assertGreaterEqual(self.st.origin.selfhood,
                                self.ctx.params["tau_origin"])
        self.assertEqual(self.st.origin.repaid, 1)


class FourStatesTest(unittest.TestCase):
    def setUp(self):
        self.ctx, _ = _ctx()

    def _state_with(self, **kw):
        st = _state(self.ctx, cap=8)
        st.origin.final = True
        for k, v in kw.items():
            setattr(st.origin, k, v)
        return st

    def test_closed(self):
        st = self._state_with(ever=True, closure=1)
        self.assertEqual(inner_conclusion(st, self.ctx, False), "origin_closed")

    def test_unstable(self):
        st = self._state_with(ever=True, closure=0, unstable=True)
        self.assertEqual(inner_conclusion(st, self.ctx, False), "origin_unstable")

    def test_open(self):
        st = self._state_with(ever=True, closure=0, unstable=False)
        self.assertEqual(inner_conclusion(st, self.ctx, False), "origin_open")

    def test_absent(self):
        st = self._state_with(ever=False, closure=0, unstable=False)
        self.assertEqual(inner_conclusion(st, self.ctx, False), "origin_absent")

    def test_not_settled_never_fires(self):
        st = _state(self.ctx, cap=8)
        st.origin.ever = True
        st.origin.closure = 1
        self.assertIsNone(inner_conclusion(st, self.ctx, False))


class ReplayTest(unittest.TestCase):
    """回望驱动：扫描 → 锚点 → 重演 → 固定点。"""

    def test_fixed_point_closes(self):
        ctx, data = _ctx()
        planner = Planner(ctx, data, 0, frames=2600)
        anchors = planner.plan()
        # 外部变量在 150 帧共鸣唤醒原初 ⇒ 早期节点都可达，不再需要 wake_origin 锚点。
        # 节点表扩充后（亡者之墓 / 记忆守席 / 记忆补回等），真正需要「补一手」的节点变多；
        # 这里只钉住「至少覆盖早期关键节点」，具体条数由节点表决定，不在测试里写死。
        self.assertGreaterEqual(len(anchors), 5)
        self.assertEqual(anchors[0]["payload"]["action"], "seed_memory")
        planner.begin_final()
        sess = load({"config": ctx, "data": data, "seed": 0,
                     "runtime": default_services(), "rules": evaluate,
                     "watch": planner.watch, "inbox": anchors})
        traj = sess.step(2600)
        summary = planner.finalize(traj)
        self.assertEqual(summary["state"], "origin_closed")
        self.assertEqual(summary["missing"], 0)
        self.assertEqual(summary["borrowed"], summary["repaid"])
        self.assertGreaterEqual(summary["repaid"], 4)
        self.assertGreaterEqual(summary["create"], 1)
        self.assertEqual(summary["form"], 2)
        self.assertEqual(summary["factor_rows"], 12)
        self.assertAlmostEqual(summary["coverage"], 1.0)
        self.assertGreaterEqual(summary["companion_spawn"], 1)
        self.assertGreaterEqual(summary["attach"], 1)
        self.assertGreaterEqual(summary["memory_seats"], 1)
        self.assertEqual(summary["resonance_host"], -2)
        self.assertGreaterEqual(summary["resonance_wake"], 1)
        self.assertEqual(summary["companion_host"], -2)
        self.assertTrue(summary["savior_active"])
        self.assertGreaterEqual(summary["savior_transfer"], 1)
        self.assertGreaterEqual(summary["memory_fragment"], 1)
        self.assertGreaterEqual(summary["memory_transfer"], 1)
        self.assertTrue(any(f.get("transferred")
                            for f in summary.get("memory_fragments", [])))
        self.assertEqual(traj.verdict, "origin_closed")
        self.assertEqual(traj.conclusion["id"], "C_ORIGIN_CLOSED")

    def test_plan_ignores_nodes_beyond_horizon(self):
        ctx, data = _ctx()
        planner = Planner(ctx, data, 0, frames=2600)
        self.assertTrue(planner.nodes)
        self.assertTrue(all(int(n.get("frame", 0)) < 2600
                            for n in planner.nodes))

    def test_same_seed_reproduces_anchors(self):
        ctx, data = _ctx()
        a = Planner(ctx, data, 0, frames=2200).plan()
        ctx2, data2 = _ctx()
        b = Planner(ctx2, data2, 0, frames=2200).plan()
        self.assertEqual([(x["frame"], x["payload"]["action"]) for x in a],
                         [(x["frame"], x["payload"]["action"]) for x in b])

    def test_absent_when_origin_never_forms(self):
        ctx, data = _ctx()
        # 让外部变量的共鸣也够不着：200 帧内原初始终沉睡，第一遍从未成形。
        ctx.params["origin_resonance_threshold"] = 2.0
        planner = Planner(ctx, data, 0, frames=200)
        self.assertEqual(planner.plan(), [])
        planner.begin_final()
        sess = load({"config": ctx, "data": data, "seed": 0,
                     "runtime": default_services(), "rules": evaluate,
                     "watch": planner.watch})
        traj = sess.step(200)
        summary = planner.finalize(traj)
        self.assertEqual(summary["state"], "origin_absent")
        self.assertEqual(traj.verdict, "origin_absent")


class BranchPresetsTest(unittest.TestCase):
    """失败分支与「开拓」演示预设必须真的走到对应四态。"""

    @staticmethod
    def _replay(preset, frames):
        ctx, data = _ctx(preset)
        planner = Planner(ctx, data, 0, frames=frames)
        anchors = planner.plan()
        planner.begin_final()
        sess = load({"config": ctx, "data": data, "seed": 0,
                     "runtime": default_services(), "rules": evaluate,
                     "watch": planner.watch, "inbox": anchors})
        traj = sess.step(frames)
        return anchors, traj, planner.finalize(traj)

    def test_absent_branch(self):
        anchors, traj, summary = self._replay("origin-absent", 2000)
        self.assertEqual(anchors, [])
        self.assertEqual(summary["state"], "origin_absent")
        self.assertFalse(summary["ever"])
        self.assertEqual(traj.verdict, "origin_absent")

    def test_open_branch(self):
        anchors, traj, summary = self._replay("origin-open", 2000)
        self.assertEqual(summary["state"], "origin_open")
        self.assertEqual(summary["missing"], 0)
        self.assertLess(summary["repaid"], summary["borrowed"])
        self.assertEqual(traj.verdict, "origin_open")

    def test_unstable_branch(self):
        anchors, traj, summary = self._replay("origin-unstable", 2000)
        self.assertEqual(len(anchors), 1)
        self.assertEqual(summary["state"], "origin_unstable")
        self.assertEqual(summary["missing"], 1)
        self.assertEqual(traj.verdict, "origin_unstable")

    def test_trailblaze_branch(self):
        ctx, data = _ctx("origin-stall")
        from kernel.core import run
        traj = run(ctx, data, seed=0, max_frames=12000,
                   rules=evaluate, runtime=default_services())
        self.assertGreater(int(traj.final.score.get("origin_trailblaze", 0.0)), 0)
        self.assertTrue(traj.final.origin.awake)
        self.assertTrue(traj.final.origin.ever)


class EternalRecurrenceTest(unittest.TestCase):
    """永劫回归：帧钟真的走到 3300 万量级，但只真算数万帧（其余沿参考轨道复用）。"""

    def test_preset_declares_the_narrative_scale(self):
        ctx, _data = _ctx("origin-eternal")
        # 跑到收束（最后一轮 3.7 的协议覆写）就停，不再往后空转 5000 帧 ——
        # 否则编年史会继续冒出「新的黄金裔涌现」，与「故事已经收束」矛盾。
        self.assertGreaterEqual(int(ctx.params.get("frames", 0)), 33590000)
        path = os.path.join(ORIGIN_ROOT, "presets", "origin-eternal",
                            "events.jsonl")
        with open(path, encoding="utf-8") as f:
            events = [json.loads(line) for line in f if line.strip()]
        frames = {int(e.get("frame", 0)) for e in events}
        self.assertIn(12000, frames)          # 封回长眠、结构冻结
        self.assertIn(33594336, frames)       # 外部变量结束循环
        self.assertIn(33594527, frames)       # 协议覆写：收束点
        self.assertLessEqual(max(frames), int(ctx.params["frames"]))

    def test_loop_reuses_the_reference_track(self):
        ctx, data = _ctx("origin-eternal")
        planner = Planner(ctx, data, 0, frames=16000)
        anchors = [
            {"frame": 300, "channel": "origin", "capability": "origin_anchor",
             "selector": None, "payload": {"action": "seed_memory",
                                           "mode": "factor_basis", "cost": 0.5,
                                           "node": "N2", "order": 1}},
            {"frame": 700, "channel": "origin", "capability": "origin_anchor",
             "selector": None, "payload": {"action": "bind_memory",
                                           "cost": 0.5, "node": "N1",
                                           "order": 1}},
        ]
        traj, _scanner = planner._run_pass(anchors)
        self.assertTrue(traj.deadlock)
        self.assertGreater(traj.skipped_frames, 0)
        self.assertEqual(traj.reached_frame, 15999)
        self.assertLess(traj.iterations, 16000)


class PathTest(unittest.TestCase):
    """权柄层 · 命途：走上、聚拢、代价、背离、可回滚。"""

    def setUp(self):
        self.ctx, _ = _ctx()
        self.st = _state(self.ctx, cap=8)
        self.k = self.st.pool.alloc()
        self.st.pool.factor[self.k] = 2
        self.st.pool.born[self.k] = 0
        v = np.zeros(13, dtype=np.float32)
        v[0], v[2], v[4], v[5] = 0.1, 0.5, 0.2, 0.2
        self.st.pool.vec[self.k] = v
        self.st.pool.support[self.k] = 5.0

    def test_join_bias_and_price(self):
        serial = int(self.st.pool.serial[self.k])
        before_support = float(self.st.pool.support[self.k])
        before_off = float(self.st.pool.vec[self.k][0])
        Paths().apply(self.st, self.ctx, np.random.default_rng(0), 16)
        self.assertIn(serial, self.st.paths)
        self.assertEqual(self.st.paths[serial]["id"], "trailblaze")
        self.assertGreater(self.st.score.get("path_joined", 0.0), 0.0)
        self.assertIn("emitted_path_joined", self.st.score)
        # 行路代价 + 朝轴聚拢（轴外的分量被压小）
        self.assertLess(float(self.st.pool.support[self.k]), before_support)
        self.assertLess(float(self.st.pool.vec[self.k][0]), before_off)

    def test_defection_after_dwell(self):
        serial = int(self.st.pool.serial[self.k])
        self.st.paths[serial] = {"id": "trailblaze", "affinity": 0.9,
                                 "joined": 0, "low": 0}
        v = np.zeros(13, dtype=np.float32)
        v[0] = 1.0                      # 完全离开这条轴
        self.st.pool.vec[self.k] = v
        dwell = int(self.ctx.paths["defect_dwell"])
        for n in range(dwell):
            Paths().apply(self.st, self.ctx, np.random.default_rng(n),
                          16 * (n + 1))
        self.assertNotIn(serial, self.st.paths)
        self.assertGreater(self.st.score.get("path_defected", 0.0), 0.0)
        self.assertIn("emitted_path_defected", self.st.score)

    def test_disabled_paths_do_nothing(self):
        ctx, _ = _ctx()
        ctx.paths = None
        st = _state(ctx, cap=8)
        k = st.pool.alloc()
        st.pool.vec[k] = _norm([0.1] * 13)
        Paths().apply(st, ctx, np.random.default_rng(0), 16)
        self.assertEqual(st.paths, {})
        self.assertEqual(st.score.get("path_joined", 0.0), 0.0)

    def test_path_state_rolls_back_with_the_world(self):
        before = self.st.digest()
        Paths().apply(self.st, self.ctx, np.random.default_rng(0), 16)
        self.assertNotEqual(self.st.digest(), before)
        clone = self.st.clone()
        self.assertEqual(clone.digest(), self.st.digest())
        self.assertEqual(dict(clone.paths), dict(self.st.paths))

    def _member_state(self, grant=False):
        ctx, _ = _ctx()
        st = _state(ctx, cap=8)
        k = st.pool.alloc()
        st.pool.factor[k] = 2
        st.pool.born[k] = 0
        v = np.zeros(13, dtype=np.float32)
        v[0], v[2], v[4], v[5] = 0.1, 0.5, 0.2, 0.2
        st.pool.vec[k] = v
        st.pool.support[k] = 5.0
        if grant:
            st.grants[int(st.pool.serial[k])] = {
                "path": "trailblaze", "by": "external_x", "frame": 0}
        return ctx, st, k

    def test_emanator_walks_a_tighter_path(self):
        ctx_a, a, ka = self._member_state(grant=False)
        ctx_b, b, kb = self._member_state(grant=True)
        Paths().apply(a, ctx_a, np.random.default_rng(0), 16)
        Paths().apply(b, ctx_b, np.random.default_rng(0), 16)
        # 令使聚拢得更狠、代价付得更少
        self.assertLess(float(b.pool.vec[kb][0]), float(a.pool.vec[ka][0]))
        self.assertGreater(float(b.pool.support[kb]), float(a.pool.support[ka]))

    def test_defection_revokes_the_grant(self):
        serial = int(self.st.pool.serial[self.k])
        self.st.paths[serial] = {"id": "trailblaze", "affinity": 0.9,
                                 "joined": 0, "low": 0}
        self.st.grants[serial] = {"path": "trailblaze", "by": "external_x",
                                  "frame": 0}
        v = np.zeros(13, dtype=np.float32)
        v[0] = 1.0
        self.st.pool.vec[self.k] = v
        for n in range(int(self.ctx.paths["defect_dwell"])):
            Paths().apply(self.st, self.ctx, np.random.default_rng(n),
                          16 * (n + 1))
        self.assertNotIn(serial, self.st.grants)
        self.assertGreater(self.st.score.get("path_revoked", 0.0), 0.0)
        self.assertIn("emitted_path_revoked", self.st.score)


class EmanatorTest(unittest.TestCase):
    """权柄层 · 星神与令使：授权、授予、收回。"""

    def setUp(self):
        self.ctx, _ = _ctx()
        self.st = _state(self.ctx, cap=8)
        self.st.actors["external_x"] = {"label": "", "grants": (), "state": {}}

    def _gaze(self, effect, frame=5):
        dispatch({"capability": "gaze", "selector": None,
                  "payload": {"actor": "external_x", "effect": effect}},
                 self.st, self.ctx, frame)

    def test_gaze_grants_emanator_with_authority(self):
        self._gaze({"authority": ["memory"],
                    "grant": {"serial": -2, "path": "memory"}})
        self.assertIn(-2, self.st.grants)
        self.assertEqual(self.st.grants[-2]["path"], "memory")
        self.assertIn("memory", self.st.authorities["external_x"])
        self.assertIn("emitted_emanator_granted", self.st.score)

    def test_grant_denied_without_authority(self):
        self._gaze({"grant": {"serial": -2, "path": "memory"}})
        self.assertNotIn(-2, self.st.grants)
        self.assertGreater(self.st.score.get("grant_denied", 0.0), 0.0)

    def test_revoke_penalizes_holder(self):
        k = self.st.pool.alloc()
        serial = int(self.st.pool.serial[k])
        self.st.pool.support[k] = 5.0
        self.st.grants[serial] = {"path": "memory", "by": "external_x",
                                  "frame": 0}
        self._gaze({"revoke": serial, "penalty": 2.0})
        self.assertNotIn(serial, self.st.grants)
        self.assertAlmostEqual(float(self.st.pool.support[k]), 3.0)
        self.assertIn("emitted_path_revoked", self.st.score)


class ReportLineTest(unittest.TestCase):
    def test_recurrence_line_uses_real_skipped_frames(self):
        from apps.origin import render_state
        text = "\n".join(render_state(
            {"state": "origin_closed", "reached_frame": 33599999,
             "frames_simulated": 27916, "frames_skipped": 33580197,
             "recurrence_target": 33550336}, {}))
        self.assertIn("永劫回归约 33,580,197 轮", text)
        self.assertIn("按 1 帧 = 1 轮计", text)
        self.assertIn("原著 33,550,336", text)


class DecisionTest(unittest.TestCase):
    """来古士的话只改 certainty；真正的决定由 OP_DECIDE 自己下。"""

    def setUp(self):
        from kernel.operators import Decide
        self.ctx, _ = _ctx()
        self.st = _state(self.ctx, cap=8)
        self.Decide = Decide
        _seat(self.st, 0, [0.1] * 12 + [0.05], serial=7)

    def _name_and_hint(self, hint=True):
        dispatch({"capability": "name_factor", "selector": {"expr": "order:0"},
                  "payload": {"role": "甲"}}, self.st, self.ctx, 10)
        if hint:
            dispatch({"capability": "hint",
                      "payload": {"certainty": 0.6, "roles": ["甲"]}},
                     self.st, self.ctx, 11)

    def test_hint_then_decision_creates_the_loophole(self):
        self._name_and_hint()
        self.assertGreaterEqual(
            self.st.factor_ledger["甲"]["certainty"], 0.5)
        self.Decide().apply(self.st, self.ctx, None, 11999)
        self.assertNotIn(1, self.st.suppressed)       # 还没到决定时刻
        self.Decide().apply(self.st, self.ctx, None, 12000)
        self.assertIn(1, self.st.suppressed)          # 因子自己压住岁月席
        self.assertEqual(self.st.factor_intent.get("甲"), "prevent_recreation")
        self.assertGreater(self.st.score.get("factor_decided", 0.0), 0.0)

    def test_without_hint_no_decision(self):
        self._name_and_hint(hint=False)
        self.Decide().apply(self.st, self.ctx, None, 12000)
        self.assertNotIn(1, self.st.suppressed)
        self.assertNotIn("甲", self.st.factor_intent)

    def test_entry_lock_blocks_bind_until_unlocked(self):
        dispatch({"capability": "entry", "payload": {"locked": True}},
                 self.st, self.ctx, 10)
        dispatch({"capability": "bind_participant",
                  "selector": {"expr": "order:0"},
                  "payload": {"participant": -2}}, self.st, self.ctx, 11)
        self.assertNotEqual(self.st.register.slots[0].owner, -2)
        self.assertGreater(self.st.score.get("entry_denied", 0.0), 0.0)
        dispatch({"capability": "entry", "payload": {"locked": False}},
                 self.st, self.ctx, 12)
        dispatch({"capability": "bind_participant",
                  "selector": {"expr": "order:0"},
                  "payload": {"participant": -2}}, self.st, self.ctx, 13)
        self.assertEqual(self.st.register.slots[0].owner, -2)


class RollbackTest(unittest.TestCase):
    """真实回退：checkpoint 存世界，gaze.rollback 把世界退回，账本不回退。"""

    def test_checkpoint_then_rollback_restores_world_only(self):
        ctx, _ = _ctx()
        st = _state(ctx, cap=8)
        st.actors["fuli"] = {"label": "", "grants": (), "state": {}}
        st.noise = 1.0
        st.score["keep"] = 7.0
        dispatch({"capability": "checkpoint", "payload": {"to": 12}},
                 st, ctx, 12)
        self.assertIsNotNone(st.rewind_state)
        self.assertEqual(st.rewind_frame, 12)
        st.noise = 9.0
        st.score["extra"] = 1.0
        _, fired = dispatch({"capability": "gaze",
                             "payload": {"actor": "fuli",
                                         "effect": {"rollback": True}}},
                            st, ctx, 20)
        self.assertTrue(fired)
        self.assertTrue(st.rewind_to)
        st.copy_world_from(st.rewind_state)
        self.assertEqual(float(st.noise), 1.0)
        # 账本不回退：回退前写下的读数仍在。
        self.assertEqual(st.score.get("keep"), 7.0)
        self.assertEqual(st.score.get("extra"), 1.0)

    def test_rollback_without_checkpoint_is_refused(self):
        ctx, _ = _ctx()
        st = _state(ctx, cap=8)
        st.actors["fuli"] = {"label": "", "grants": (), "state": {}}
        dispatch({"capability": "gaze",
                  "payload": {"actor": "fuli", "effect": {"rollback": True}}},
                 st, ctx, 20)
        self.assertFalse(st.rewind_to)
        self.assertGreater(st.score.get("rollback_refused", 0.0), 0.0)


class OriginPanelTest(unittest.TestCase):
    """看板的原初小节：双曲线 / 记忆泳道 / 忆灵生命线 / 锚点借还刻度。"""

    def _summary(self):
        return {
            "state": "origin_closed", "ever": True, "selfhood": 0.42,
            "energy": 3.5, "borrowed": 5, "repaid": 5, "missing": 0,
            "companion_spawn": 2, "companion_stage": 3,
            "companion_carry": 2, "companion_alive": True,
            "memory_fragments": [{
                "id": "m1", "label": "救世主记忆", "effect": "selfhood",
                "transferred": True, "start_frame": 1200, "phase_index": 1,
                "phases": [
                    {"label": "初读", "effect": "selfhood", "duration": 600},
                    {"label": "同行", "effect": "coupling", "duration": 0}],
            }],
            "anchor_frames": [
                {"frame": 300, "action": "wake_origin", "node": "N2",
                 "cost": 2.0, "keep": False},
                {"frame": 700, "action": "bind_memory", "node": "N1",
                 "cost": 1.0, "keep": True}],
        }

    def test_panel_draws_curves_lanes_and_anchors(self):
        from apps.viz import origin_panel
        series = [(100, 0.1, 1.0, 0, 1, 0, False),
                  (900, 0.3, 2.0, 0, 2, 1, True),
                  (3000, 0.42, 3.5, 1, 3, 2, True)]
        text = origin_panel(self._summary(), series, 3000)
        self.assertIn("原初（第十三席）", text)
        self.assertIn("自我度 / 能量", text)
        self.assertIn("记忆阶段泳道", text)
        self.assertIn("救世主记忆", text)
        self.assertIn("忆灵生命线", text)
        self.assertIn("凝", text)
        self.assertIn("承忆（3/4）", text)
        self.assertIn("锚点借还刻度", text)
        self.assertIn("唤醒·N2", text)
        self.assertIn("借出 5 手 · 还上 5 笔", text)

    def test_panel_is_absent_without_origin(self):
        from apps.viz import origin_panel
        self.assertEqual(origin_panel({}, [], 100), "")
        self.assertEqual(origin_panel(None, [], 100), "")

    def test_sampler_collects_origin_readings_only_when_formed(self):
        from apps.viz import Sampler
        ctx, _ = _ctx()
        st = _state(ctx, cap=8)
        smp = Sampler(total=1000, cap=10)
        smp(1, st, None)
        self.assertEqual(smp.origin, [])
        st.origin.ever = True
        st.origin.selfhood = 0.25
        st.origin.energy = 2.0
        smp(5, st, None)
        self.assertTrue(smp.origin)
        self.assertAlmostEqual(float(smp.origin[-1][1]), 0.25, places=5)
        self.assertAlmostEqual(float(smp.origin[-1][2]), 2.0, places=5)


class L12CardTest(unittest.TestCase):
    """看板要有【第十三席】自己的一张卡：席位归属 + 忆灵成长。"""

    def test_l12_seat_card_reports_growth(self):
        from apps.namer import Namer
        from apps.viz import summary_cards

        ctx, _ = _ctx()
        st = _state(ctx, cap=8)
        i = st.pool.alloc()
        st.pool.factor[i] = 12
        _seat(st, 12, [0.02] * 12 + [0.6], serial=int(st.pool.serial[i]))

        class _Traj:
            records = []
            spans = ()
            personas = []
            final = st
            namer = Namer(ctx, {})
            origin = {"form": 2, "selfhood": 0.3, "factor_rows": 12,
                      "borrowed": 5, "repaid": 5, "missing": 0,
                      "memory_seats": 1, "companion_serial": 7,
                      "companion_host": 3, "companion_stage": 3,
                      "companion_age": 900, "companion_carry": 2,
                      "path_members": 34, "emanators": 1}
            conclusion = {"template": "", "id": ""}
            verdict = "origin_closed"
            stop_reason = "ORIGIN_CLOSED"
            reached_frame = 100
            iterations = 1
            skipped_frames = 0

        cards = summary_cards(ctx, _Traj())
        seat = dict((k, v) for k, v, _m in cards)
        self.assertIn("第十三席", seat)
        self.assertIn("L12", seat["第十三席"])
        self.assertIn("承忆（3/4）", seat["第十三席"])
        self.assertIn("携 2 段记忆", seat["第十三席"])
        self.assertIn("命途行者 34", seat["第十三席"])
        self.assertIn("令使 1", seat["第十三席"])


class CheckpointTest(unittest.TestCase):
    def test_truncated_replay_matches_full(self):
        ctx, data = _ctx()
        spec = {"config": ctx, "data": data, "seed": 0,
                "runtime": default_services(), "rules": evaluate,
                "trace": False}
        full = load(spec)
        full.step(240)
        want = full.state.digest()

        part = load(spec)
        part.step(120)
        snap = part.snapshot()
        part.step(120)
        part.restore(snap)
        part.step(120)
        self.assertEqual(part.state.digest(), want)


if __name__ == "__main__":
    unittest.main()
