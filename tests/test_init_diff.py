"""初始变量集（--init-set）的契约测试。

覆盖五件事：
  · 同 seed 同初始变量 ⇒ 逐帧签名 / 事件 / 末帧读数完全一致；
  · A/B 的首个分叉帧可复现（跑两次相同），且 3000 帧内出现定性差异
    （裁决 / 事件集合 / 承位结果至少一项）；
  · seed 属于初始变量集：init 里的 seed 生效，`--init-set` 与 `--seed` 同用报错；
  · 缺文件时给出带「可用集合」的清晰错误；
  · 解析优先级：presets/<当前预设>/init-X.json 先于 presets/scepter/init-X.json。

    python -m unittest discover -s tests -p "test_init_diff.py" -q
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import types
import unittest

from _support import ROOT

sys.path.insert(0, os.path.join(ROOT, "tools"))

import init_diff  # noqa: E402
import run as runner  # noqa: E402


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


class InitDiffContract(unittest.TestCase):
    FRAMES = 30
    DIVERGENCE_FRAMES = 3000

    def test_same_seed_same_init_is_identical(self):
        a1 = init_diff.run_init("A", seed=0, frames=self.FRAMES)
        a2 = init_diff.run_init("A", seed=0, frames=self.FRAMES)
        self.assertEqual(a1["signatures"], a2["signatures"])
        self.assertEqual(a1["events"], a2["events"])
        self.assertEqual(a1["final"], a2["final"])
        self.assertEqual(a1["seed"], a2["seed"])

    def test_first_divergence_is_reproducible(self):
        c1 = init_diff.compare(
            init_diff.run_init("A", seed=0, frames=self.FRAMES),
            init_diff.run_init("B", seed=0, frames=self.FRAMES))
        c2 = init_diff.compare(
            init_diff.run_init("A", seed=0, frames=self.FRAMES),
            init_diff.run_init("B", seed=0, frames=self.FRAMES))
        self.assertIsNotNone(c1["first_divergence_frame"])
        self.assertEqual(c1["first_divergence_frame"],
                         c2["first_divergence_frame"])
        # 六项初始变量在 A/B 下都真的不同
        self.assertEqual(len(c1["dimension_diff"]["changed"]), 6)

    def test_init_seed_wins_over_preset_and_cli_is_rejected(self):
        path, doc = runner.resolve_init_set(ROOT, "emergent", "A")
        fake = types.SimpleNamespace(preset={"seed": 7}, genesis={"seed": 9})
        self.assertEqual(runner.init_set_seed(path, doc), 0)
        # init 里的 seed 优先于 preset.seed / genesis.seed
        self.assertEqual(runner.resolve_seed(None, doc, fake, path), 0)
        # 同时给 CLI seed ⇒ 报错（seed 已属于初始变量集）
        with self.assertRaises(runner.InitSetError):
            runner.resolve_seed(3, doc, fake, path)
        # 没给 init 时保持旧优先级：CLI → preset → genesis
        self.assertEqual(runner.resolve_seed(5, None, fake), 5)
        self.assertEqual(runner.resolve_seed(None, None, fake), 7)
        no_seed = {"knobs": {"resource_abundance": 1.0}}
        self.assertEqual(runner.resolve_seed(None, no_seed, fake), 7)

    def test_ab_is_qualitatively_different_at_3000_frames(self):
        a = init_diff.run_init("A", frames=self.DIVERGENCE_FRAMES)
        b = init_diff.run_init("B", frames=self.DIVERGENCE_FRAMES)
        self.assertEqual(a["seed"], b["seed"], "A/B 必须同一个抽样键")
        changed = init_diff.compare(a, b)
        final = changed["final_diff"]["changed"]
        event_kinds_a = set(a["events"])
        event_kinds_b = set(b["events"])
        verdict_or_events = ("verdict" in final
                             or event_kinds_a != event_kinds_b)
        promotions = final.get("promotions")
        self.assertTrue(
            verdict_or_events or promotions is not None,
            "3000 帧内 A/B 没有定性差异（裁决 / 事件集合 / 承位结果）")

    def test_missing_set_names_what_is_available(self):
        with self.assertRaises(runner.InitSetError) as caught:
            runner.resolve_init_set(ROOT, "emergent", "NO_SUCH_SET")
        message = str(caught.exception)
        self.assertIn("找不到初始变量集", message)
        self.assertIn("可用", message)
        self.assertIn("A", message)
        self.assertIn("B", message)

    def test_preset_dir_wins_over_shared_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            for folder in ("plot", "scepter"):
                os.makedirs(os.path.join(tmp, "presets", folder))
                path = os.path.join(tmp, "presets", folder, "init-Z.json")
                with open(path, "w", encoding="utf-8") as f:
                    json.dump({"label": folder, "knobs": {}}, f)
            chosen, doc = runner.resolve_init_set(tmp, "plot", "Z")
            self.assertEqual(doc["label"], "plot")
            self.assertEqual(chosen, os.path.join(tmp, "presets", "plot",
                                                  "init-Z.json"))
            # 当前预设目录没有时，回落到共享目录
            fallback, doc2 = runner.resolve_init_set(tmp, "emergent", "Z")
            self.assertEqual(doc2["label"], "scepter")
            self.assertEqual(fallback, os.path.join(tmp, "presets", "scepter",
                                                   "init-Z.json"))

    def test_init_set_never_touches_config_files(self):
        watched = [os.path.join(ROOT, "config", name)
                   for name in ("params.json", "loci.json", "generation.json")]
        before = {p: _sha(p) for p in watched}
        init_diff.run_init("B", seed=0, frames=5)
        after = {p: _sha(p) for p in watched}
        self.assertEqual(before, after, "初始变量集写回了 config/ 原文件")


if __name__ == "__main__":
    unittest.main()
