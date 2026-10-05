"""外部变量参与者（设计稿 §八 落地）：带外编号一族的引擎语义 + 预设接线。

这几位（开拓者 / 丹恒 / 长夜月）此前是**被锚定改名的普通涌现个体**；现改为
「不从池子里长出来、却占席参与」的场外参与者：
  · 预设侧：锚定用【带外编号】（< 0，与记忆承载的 -1 同族），`external: true` 仍标着；
  · 引擎侧：新增 `bind_participant`，在预设指定的帧把场外个体直接放进席位；
  · 语义：带外占位一律**不被活体抢占 / 不被逐火驱逐 / 不计入涌现**（只看编号符号，
    不看名字 —— 命名正交，红线 5）。
"""
from __future__ import annotations

import unittest

from _support import ROOT, state

from engine.disturbance import CAPABILITIES, dispatch
from engine.loader import Config, DataSet
from engine.operators import MEMORY_OWNER, Occupy, is_external_owner


class ExternalOwnerFamily(unittest.TestCase):
    def test_flag_is_about_the_sign_not_the_name(self):
        self.assertTrue(is_external_owner(MEMORY_OWNER))     # 记忆承载
        self.assertTrue(is_external_owner(-2))              # 场外参与者
        self.assertFalse(is_external_owner(0))
        self.assertFalse(is_external_owner(None))


class BindParticipantCapability(unittest.TestCase):
    """`bind_participant` 把一个带外编号放进选中的席位，并拒收非负数。"""

    @classmethod
    def setUpClass(cls):
        cls.data = DataSet(ROOT, preset="plot")
        cls.ctx = Config(ROOT, lex_overlay=cls.data.preset.get("lexicon"))
        cls.i0 = next(i for i, l in enumerate(cls.ctx.loci) if l.order == 0)

    def _st(self):
        return state(self.ctx, 16,
                     list(self.data.genesis["domain"]["initial_variable"]))

    def test_registered_and_binds_a_negative_serial(self):
        self.assertIn("bind_participant", CAPABILITIES)
        st = self._st()
        dispatch({"capability": "bind_participant", "selector": {"expr": "order:0"},
                  "payload": {"participant": -2}}, st, self.ctx, 1)
        self.assertEqual(st.register.slots[self.i0].owner, -2)

    def test_rejects_a_pool_serial(self):
        st = self._st()
        dispatch({"capability": "bind_participant", "selector": {"expr": "order:0"},
                  "payload": {"participant": 7}}, st, self.ctx, 1)
        self.assertIsNone(st.register.slots[self.i0].owner)
        self.assertEqual(st.score.get("bind_denied"), 1.0)

    def test_external_seat_survives_the_owner_assigner(self):
        """外生占位既不被活体抢占，也不会被「查不到就清空」那条规则抹掉。"""
        st = self._st()
        st.pool.alloc()                                  # 池里有人，才走得到席位那段
        st.register.slots[self.i0].owner = -2
        Occupy().apply(st, self.ctx, None, 1)
        self.assertEqual(st.register.slots[self.i0].owner, -2)


class PresetWiring(unittest.TestCase):
    def _events(self, preset):
        return DataSet(ROOT, preset=preset).preset.get("events") or []

    def test_plot_binds_the_participants_by_external_serial(self):
        data = DataSet(ROOT, preset="plot")
        ext = {int(str(a["key"]).split(":", 1)[1])
               for a in data.anchors if a.get("external")}
        self.assertTrue({-2, -3, -1} <= ext, f"三位场外参与者应带外编号：{sorted(ext)}")
        binds = [e for e in (data.preset.get("events") or [])
                 if e.get("capability") == "bind_participant"]
        self.assertEqual({int(e["payload"]["participant"]) for e in binds}, {-2, -3})

    def test_nullify_keeps_the_seat_empty(self):
        """否定版里没有场外参与者来接 —— 那一席是被【清空】的。"""
        caps = {e.get("capability") for e in self._events("nullify")}
        self.assertNotIn("bind_participant", caps)


if __name__ == "__main__":
    unittest.main()
