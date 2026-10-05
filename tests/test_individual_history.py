"""个体史（墓碑 + 出生 + 承位链）—— 让「谁死了、因何、被谁」可查。

在此之前，引擎只把个体当**统计样本**：`kill()` 之后槽位立刻可被 `alloc()` 复用并覆盖，
于是"谁死了、因何、被谁"在下一个补种之后就查不到了；而"谁从谁手里接的位"从未记录。

四条要求：
  ① **死者必有墓碑**，死因取自注册的那几个通用词；
  ② **墓碑与账本不许漂**：各死因的条数必须与 `score` 里的计数逐一对上；
  ③ **克隆体从零开始**：个体史是**主轨道**的记录 —— 试算世界的历史不许漏进主账本
     （`snapshot()` 每帧都要克隆，这也是它不能被克隆的原因）；
  ④ **承位链真的连得上**：接手者的 `from_serial` 必须是墓碑里那个被夺席的人。
"""
from __future__ import annotations

import unittest
from collections import Counter

from _support import ROOT, load, state

from engine.disturbance import dispatch
from engine.loader import Config
from engine.state import DEATH_CAUSES

#: 死因的封闭集合（都是通用词，不含任何专名）—— 与引擎同一份来源。
CAUSES = set(DEATH_CAUSES)


class Tombstones(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx, cls.data, cls.traj = load("plot", frames=3000, seed=0)

    def test_every_death_leaves_a_stone(self):
        stones = self.traj.final.tombstones
        self.assertTrue(stones, "3000 帧一个墓碑都没有，说明埋点没接上")
        for row in stones:
            self.assertEqual(len(row), 5)
            frame, serial, factor, cause, by = row
            self.assertIsInstance(frame, int)
            self.assertIsInstance(serial, int)
            self.assertIsInstance(factor, int)
            self.assertIn(cause, CAUSES, f"未注册的死因 {cause!r}")

    def test_causes_match_the_score_ledger(self):
        """墓碑的条数必须与账本对得上 —— 两处口径不许漂。"""
        st = self.traj.final
        n = Counter(row[3] for row in st.tombstones)
        self.assertEqual(n["aged"], int(st.score.get("deaths_natural", 0)))
        self.assertEqual(n["dethroned"], int(st.score.get("deaths_slain", 0)))
        competitive = n["isolated"] + n["homogenized"]
        self.assertEqual(competitive, int(st.score.get("deaths_competitive", 0)))

    def test_every_stone_has_a_birth_record(self):
        """死人必有出生记录 —— 否则"生平"缺了开头。"""
        st = self.traj.final
        for _f, serial, _fa, _c, _b in st.tombstones:
            self.assertIn(serial, st.chronicle)

    def test_stone_and_chronicle_agree(self):
        st = self.traj.final
        for f, serial, _fa, cause, by in st.tombstones:
            rec = st.chronicle[serial]
            self.assertEqual(rec["died"], f)
            self.assertEqual(rec["cause"], cause)
            self.assertEqual(rec["by"], by)

    def test_a_slain_holder_was_on_a_seat(self):
        """被夺席的人必然坐过席 —— 否则 `_pilgrimage` 埋错了点。"""
        st = self.traj.final
        # 被夺席者死前是某一席的在位者；这里只核"确实有这一死因且字段齐全"
        slain = [r for r in st.tombstones if r[3] == "dethroned"]
        self.assertTrue(slain)
        for _f, serial, _fa, _c, _b in slain:
            self.assertIn("born", st.chronicle[serial])


class CloneStartsEmpty(unittest.TestCase):
    """个体史是【主轨道】的账本 —— 试算世界（克隆体）从零开始。"""

    @classmethod
    def setUpClass(cls):
        cls.ctx, cls.data, cls.traj = load("plot", frames=600, seed=0)

    def test_clone_gets_no_history(self):
        st = self.traj.final
        self.assertTrue(st.tombstones or st.chronicle)     # 主轨道上确实有
        c = st.clone()
        self.assertEqual(c.tombstones, [])
        self.assertEqual(c.chronicle, {})

    def test_snapshot_is_a_clone(self):
        st = self.traj.final
        self.assertEqual(st.snapshot().tombstones, [])


class Inheritance(unittest.TestCase):
    """承位链：引擎里唯一真实的「传承关系」来自 `_pilgrimage` 的夺席。"""

    @classmethod
    def setUpClass(cls):
        cls.ctx, cls.data, cls.traj = load("plot", frames=3000, seed=0)

    def test_heirs_point_back_at_the_dethroned(self):
        st = self.traj.final
        heirs = [(s, r) for s, r in st.chronicle.items()
                 if r["from_serial"] is not None]
        self.assertTrue(heirs, "没有任何承位链 —— `_pilgrimage` 该留下才对")
        dethroned = {s for _f, s, _fa, c, _b in st.tombstones if c == "dethroned"}
        for serial, rec in heirs:
            self.assertIn(rec["from_serial"], dethroned,
                          f"{serial} 说它接自 {rec['from_serial']}，但那人不在被夺席之列")

    def test_births_are_recorded_for_the_living_too(self):
        """活着的人也该有出生记录 —— 有 chronicle 条目、died 为空。"""
        st = self.traj.final
        alive_records = [r for r in st.chronicle.values() if r["died"] is None]
        self.assertTrue(alive_records)


class ExternalKillsAreAttributed(unittest.TestCase):
    """外生逐出 / 接掌也要留墓碑，而且记下【由谁】—— 这是"元凶"可归因的前提。"""

    def setUp(self):
        self.ctx = Config(ROOT)

    def _seated(self, seat=0):
        st = state(self.ctx, 64, ["a"])
        k = st.pool.alloc()
        st.pool.factor[k] = 0
        st.born(0, k)
        st.register.slots[seat].owner = int(st.pool.serial[k])
        return st, k

    def test_eviction_records_cause_and_actor(self):
        st, _k = self._seated()
        dispatch({"frame": 7, "channel": "world", "capability": "evict_holder",
                  "selector": {"expr": "order:0"},
                  "payload": {"actor": "hacker"}}, st, self.ctx, 7)
        frame, serial, factor, cause, by = st.tombstones[-1]
        self.assertEqual(cause, "evicted")
        self.assertEqual(by, "hacker")
        self.assertEqual(frame, 7)
        self.assertEqual(st.chronicle[serial]["cause"], "evicted")
        self.assertEqual(st.chronicle[serial]["factor"], 0)

    def test_bind_participant_records_displacement(self):
        st, _k = self._seated()
        dispatch({"frame": 9, "channel": "world", "capability": "bind_participant",
                  "selector": {"expr": "order:0"},
                  "payload": {"participant": -2, "actor": "observer_04"}},
                 st, self.ctx, 9)
        self.assertEqual(st.tombstones[-1][3], "displaced")
        self.assertEqual(st.tombstones[-1][4], "observer_04")

    def test_environmental_death_has_no_actor(self):
        """环境性的死（寿终 / 被孤立）不归因到谁头上 —— `by` 必须是 None。"""
        _ctx, _data, traj = load("plot", frames=600, seed=0)
        env = [r for r in traj.final.tombstones if r[3] in ("aged", "isolated",
                                                            "homogenized")]
        self.assertTrue(env)
        self.assertTrue(all(r[4] is None for r in env))


if __name__ == "__main__":
    unittest.main()