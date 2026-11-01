"""名字链路：内核的 EMERGENCE 载荷【没有】名字，渲染层必须在登记前用 Namer 补出来。

    python -m unittest tests.test_naming

内核只发 `{serial, rank, fingerprint, locus?}`（见 `kernel/emergence.py::describe`）；
名字由 `apps/namer.py` 按「指纹 → 编号 → 涌现次序 → 音位层现生成」补。若 `Cast.see`
直接把载荷里的空缺当「无名」，编年史就会退回 `无名者#N` —— 这里把这条链路钉住。
"""
from __future__ import annotations

import unittest

from tests._support import load

FRAMES = 300


class NamingChainTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import run
        from apps.render import renderer_for

        cls.run_module = run
        cls.ctx, cls.data, cls.traj = load("plot", frames=FRAMES)
        cls.R = renderer_for(cls.ctx, cls.traj)
        cls.namer = cls.traj.namer

    def _payload(self, persona):
        """复刻内核真正抛出的 EMERGENCE 载荷 —— 刻意不含 hanzi / latin。"""
        payload = {"serial": int(persona.serial), "rank": int(persona.rank),
                   "fingerprint": persona.fingerprint.hex()}
        if persona.locus_order is not None:
            payload["locus"] = self.ctx.loci[persona.locus_order].id
            payload["locus_order"] = int(persona.locus_order)
        return payload

    def _cast(self):
        return self.run_module.Cast(self.R, self.namer)

    def test_see_resolves_nameless_payload(self):
        """`Cast.see` 喂无名字载荷也要认得出人 —— 且与命名器给出的名字一致。"""
        cast = self._cast()
        self.assertTrue(self.traj.personas)
        for persona in self.traj.personas:
            payload = self._payload(persona)
            self.assertNotIn("hanzi", payload)
            self.assertNotIn("latin", payload)
            cast.see(payload)
            self.assertEqual(cast.resolve(persona.serial),
                             self.namer.persona_name(persona)[1])

    def test_name_is_stable_across_events(self):
        """同一个人在涌现 / 接掌 / 重复登记里拿到的都是同一个名字。"""
        cast = self._cast()
        for persona in self.traj.personas:
            cast.see(self._payload(persona))
        first, second = self.traj.personas[0], self.traj.personas[1]
        # 重复登记不换名
        cast.see(self._payload(first))
        self.assertEqual(cast.resolve(first.serial),
                         self.namer.persona_name(first)[1])
        # 另一条事件（接掌）里也写的是同一个名字，不是「无名者#N」
        text = self.run_module.chronicle_line(
            self.R, self.namer, "SUCCESSION",
            {"locus": self.ctx.loci[0].id,
             "from": int(first.serial), "to": int(second.serial)},
            cast, lv=3, frame=0)
        self.assertIsNotNone(text)
        self.assertIn(self.namer.persona_name(second)[1], text)
        self.assertNotIn("无名者", text)

    def test_anchored_serial_keeps_preset_name(self):
        """锚定层点过名的编号仍然解析成预设给的名字（先于音位层现生成）。"""
        pinned = next(a for a in self.data.anchors
                      if str(a.get("key")) == "serial:26246")
        cast = self._cast()
        self.assertEqual(cast.resolve(26246), pinned["hanzi"])
        persona = next((p for p in self.traj.personas
                        if int(p.serial) == 26246), None)
        if persona is not None:                # 若这一世他涌现过，登记也照锚定名
            cast.see(self._payload(persona))
            self.assertEqual(cast.resolve(26246), pinned["hanzi"])

    def test_succession_between_two_unknowns_is_dropped(self):
        """两端都真解析不出名字 ⇒ 不产生「无名者#N 接掌 …」的接掌行。"""
        cast = self._cast()
        base = max(int(p.serial) for p in self.traj.personas) + 1000
        text = self.run_module.chronicle_line(
            self.R, self.namer, "SUCCESSION",
            {"locus": self.ctx.loci[0].id, "from": base, "to": base + 1},
            cast, lv=3, frame=0)
        self.assertIsNone(text)

    def test_chronicle_has_no_nameless_rows(self):
        """跑满 300 帧：编年史里一行「无名者」都不该有（每个个体都有生成名）。"""
        rows = self.run_module.chronicle_rows(self.ctx, self.traj)
        self.assertTrue(rows)
        bad = [text for _frame, text, _badge, _rid in rows if "无名者" in text]
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
