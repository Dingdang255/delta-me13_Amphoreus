"""考据 → 实体表（F3）：`presets/*/actors.json` 必须是 `docs/外部变量.json` 的派生物。

考据写了一版、引擎真读的那张表又是另一版，是这类项目最容易烂掉的地方。
这里用生成器核对：改考据不重生成，单测就红。
"""
from __future__ import annotations

import json
import os
import sys
import unittest

from _support import ROOT

sys.path.insert(0, os.path.join(ROOT, "tools"))
import actors_from_spec  # noqa: E402


class ActorsFromSpec(unittest.TestCase):
    def test_spec_is_well_formed(self):
        spec = actors_from_spec.load_spec()
        ids = [a["id"] for a in spec["actors"]]
        self.assertEqual(len(ids), len(set(ids)), "实体 id 有重复")
        for a in spec["actors"]:
            self.assertTrue(a.get("label"), a["id"])
            self.assertIsInstance(a.get("grants"), list)

    def test_permissions_come_from_engine_vocabulary(self):
        """权限名只能是引擎的规则词汇 —— 否则 revise_protocol 永远写不进去。"""
        allowed = {"solver.direction", "promotion.mode", "suppression.release",
                   "gate.open", "locus.hand", "memory.steal"}
        spec = actors_from_spec.load_spec()
        for a in spec["actors"]:
            for g in a["grants"]:
                self.assertIn(g, allowed, f"{a['id']} 的权限 {g!r} 不在引擎词汇里")

    def test_preset_actors_match_spec(self):
        built = actors_from_spec.build(actors_from_spec.load_spec())
        for preset in ("plot",):
            path = actors_from_spec.path_of(preset)
            self.assertTrue(os.path.exists(path), path)
            with open(path, encoding="utf-8") as f:
                cur = json.load(f)
            self.assertEqual(cur, built, (
                f"{preset} 的 actors.json 与 docs/外部变量.json 不一致：跑 "
                f"python tools/actors_from_spec.py --preset {preset} --write"))


if __name__ == "__main__":
    unittest.main()
