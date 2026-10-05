"""配置与数据的启动校验（D1）。

两条要求：① 仓库自带的配置与 [PRESETS] 里的预设必须全部通过；
② 改坏一个文件时必须【启动即报】，并且报出的是「哪一处对不上」而不是一处 KeyError。
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest

from _support import ROOT, temp_root_with_copy

from engine.loader import Config, ConfigError, DataSet

PRESETS = ("emergent", "plot", "plot-mech", "nullify", "destruction", "tide", "refuted")


class ValidConfiguration(unittest.TestCase):
    def test_all_presets_load(self):
        for preset in PRESETS:
            with self.subTest(preset=preset):
                data = DataSet(ROOT, preset=preset)
                ctx = Config(ROOT, lex_overlay=data.preset.get("lexicon"))
                self.assertEqual(len(ctx.loci), ctx.params["dim"])

    def test_config_carries_its_keys(self):
        ctx = Config(ROOT)
        for key in ("params", "loci", "seeding", "pipeline", "mapping",
                    "conclusions", "phonology", "lexicon", "calendar"):
            self.assertTrue(hasattr(ctx, key), key)


class BrokenConfiguration(unittest.TestCase):
    """在临时副本上改坏文件 —— 仓库里的真文件一个字节都不动。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="amphoreus_cfg_")
        temp_root_with_copy(self.tmp)
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _rewrite(self, rel, mutate):
        path = os.path.join(self.tmp, rel)
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        mutate(obj)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)

    def test_dim_mismatch_is_reported(self):
        self._rewrite("config/params.json", lambda o: o.update({"dim": 9}))
        with self.assertRaises(ConfigError) as cm:
            Config(self.tmp)
        msg = str(cm.exception)
        self.assertIn("位表长度", msg)          # 说清是哪一处
        self.assertIn("9", msg)

    def test_bad_operator_name_is_reported(self):
        self._rewrite("config/operators.json",
                      lambda o: o.update({"pipeline": ["OP_DRIFT", "OP_NOPE"]}))
        with self.assertRaises(ConfigError) as cm:
            Config(self.tmp)
        self.assertIn("OP_NOPE", str(cm.exception))

    def test_calendar_month_missing_from_lexicon_is_reported(self):
        def mutate(o):
            o["month_keys"] = ["MONTH_NOT_IN_LEXICON"] + o["month_keys"][1:]
        self._rewrite("config/calendar.json", mutate)
        with self.assertRaises(ConfigError) as cm:
            Config(self.tmp)
        self.assertIn("MONTH_NOT_IN_LEXICON", str(cm.exception))

    def test_verbosity_out_of_range_is_reported(self):
        self._rewrite("config/params.json",
                      lambda o: o["verbosity"].update({"deadlock": 9}))
        with self.assertRaises(ConfigError) as cm:
            Config(self.tmp)
        self.assertIn("verbosity.deadlock", str(cm.exception))

    def test_unknown_disturbance_capability_is_reported(self):
        os.makedirs(os.path.join(self.tmp, "presets", "t"), exist_ok=True)
        with open(os.path.join(self.tmp, "presets", "t", "preset.json"),
                  "w", encoding="utf-8") as f:
            json.dump({"name": "t"}, f)
        with open(os.path.join(self.tmp, "presets", "t", "disturbances.jsonl"),
                  "w", encoding="utf-8") as f:
            f.write(json.dumps({"frame": 10, "capability": "not_a_capability"}) + "\n")
        with self.assertRaises(ConfigError) as cm:
            DataSet(self.tmp, preset="t")
        self.assertIn("not_a_capability", str(cm.exception))

    def test_bad_selector_is_reported(self):
        os.makedirs(os.path.join(self.tmp, "presets", "t"), exist_ok=True)
        with open(os.path.join(self.tmp, "presets", "t", "preset.json"),
                  "w", encoding="utf-8") as f:
            json.dump({"name": "t"}, f)
        with open(os.path.join(self.tmp, "presets", "t", "disturbances.jsonl"),
                  "w", encoding="utf-8") as f:
            f.write(json.dumps({"frame": 10, "capability": "suppress_slot",
                                "selector": {"expr": "order:not_a_number"}}) + "\n")
        with self.assertRaises(ConfigError) as cm:
            DataSet(self.tmp, preset="t")
        self.assertIn("order:not_a_number", str(cm.exception))

    def test_unknown_solver_in_disturbance_is_reported(self):
        """payload / active_if 里的方向名写错 → 启动即报（过去是静默失效）。"""
        os.makedirs(os.path.join(self.tmp, "presets", "t"), exist_ok=True)
        with open(os.path.join(self.tmp, "presets", "t", "preset.json"),
                  "w", encoding="utf-8") as f:
            json.dump({"name": "t"}, f)
        with open(os.path.join(self.tmp, "presets", "t", "disturbances.jsonl"),
                  "w", encoding="utf-8") as f:
            f.write(json.dumps({"frame": 10, "capability": "overwrite_operator",
                                "payload": {"to": "OP_BAD_ONE"}}) + "\n")
            f.write(json.dumps({"frame": 20, "capability": "suppress_slot",
                                "active_if": {"field": "solver",
                                              "equals": "OP_BAD_TWO"}}) + "\n")
        with self.assertRaises(ConfigError) as cm:
            DataSet(self.tmp, preset="t")
        msg = str(cm.exception)
        self.assertIn("OP_BAD_ONE", msg)          # payload.to
        self.assertIn("OP_BAD_TWO", msg)          # active_if.equals

    def test_needs_snapshot_follows_replay_policy(self):
        """帧初快照只在存在 REPLAY_SAME_FRAME 策略时才需要。

        仓库配置里没有任何重放策略 ⇒ 不作快照（省下每帧一次全状态深拷贝）；
        一旦某条策略改用它，needs_snapshot 必须立刻翻真，行为回到原样。
        """
        self.assertFalse(Config(ROOT).needs_snapshot)
        self._rewrite("config/policies.json",
                      lambda o: o.update({"EXTRA": {"strategy": "REPLAY_SAME_FRAME"}}))
        self.assertTrue(Config(self.tmp).needs_snapshot)

    def test_all_problems_reported_at_once(self):
        """一次报清：两处坏掉就一次列出两条，而不是改一处跑一次。"""
        def mutate(o):
            o.update({"dim": 9})
            o["verbosity"].update({"deadlock": 9})
        self._rewrite("config/params.json", mutate)
        with self.assertRaises(ConfigError) as cm:
            Config(self.tmp)
        msg = str(cm.exception)
        self.assertIn("位表长度", msg)
        self.assertIn("verbosity.deadlock", msg)


if __name__ == "__main__":
    unittest.main()
