"""权杖世界根：50 帧可跑通、七层字段齐全、只读开关不动指纹、面板复用 `.bar`。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest

from _support import ROOT

from apps import scepter
from apps.conditions import evaluate
from apps.namer import Namer
from apps.services import default as default_services
from kernel.api import load
from kernel.loader import Config, DataSet

SCEPTER_ROOT = os.path.join(ROOT, "worlds", "scepter")
ORIGIN_ROOT = os.path.join(ROOT, "worlds", "origin")
LAYERS = ("kernel_layer", "authority_layer", "seed_slots", "regen_count",
          "entropy", "memory_store", "external_injection")


def _run(root, preset, frames, seed=0):
    data = DataSet(root, preset=preset)
    ctx = Config(root, lex_overlay=data.preset.get("lexicon"))
    data.apply_params(ctx)
    namer = Namer(ctx, data.anchors)
    sess = load({"config": ctx, "data": data, "seed": seed, "namer": namer,
                 "rules": evaluate, "runtime": default_services()})
    return ctx, data, sess.step(frames)


def _spec(root, preset):
    with open(os.path.join(root, "presets", preset, "preset.json"),
              encoding="utf-8") as f:
        meta = json.load(f)
    return scepter.load_spec(root, preset=meta)


def _subprocess(args, cwd=ROOT):
    return subprocess.run([sys.executable, "run.py"] + list(args), cwd=cwd,
                          capture_output=True, text=True, encoding="utf-8")


def _payload(stdout):
    """run.py 先打印报告、最后打印 indent=2 的 JSON：从最后一处行首 `{` 读起。"""
    text = stdout.strip()
    start = text.rfind("\n{")
    start = start + 1 if start >= 0 else text.find("{")
    if start < 0:
        raise AssertionError("stdout 里没有 JSON")
    return json.loads(text[start:])


class ScepterWorldTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.html_path = os.path.join(cls.tmp.name, "scepter.html")
        done = _subprocess(["--root", "worlds/scepter", "--preset", "scepter",
                            "--frames", "50", "--scepter", "--panels",
                            "--export", cls.html_path])
        if done.returncode != 0:
            raise AssertionError(done.stderr or done.stdout)
        cls.report = done.stdout
        with open(cls.html_path, encoding="utf-8") as f:
            cls.html = f.read()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_world_builds_and_runs_fifty_frames(self):
        _ctx, _data, traj = _run(SCEPTER_ROOT, "scepter", 50)
        self.assertEqual(int(traj.iterations), 50)
        self.assertIsNotNone(traj.final)
        self.assertGreaterEqual(int(traj.reached_frame), 40)

    def test_summary_has_all_seven_layers(self):
        _ctx, _data, traj = _run(SCEPTER_ROOT, "scepter", 50)
        data = scepter.summary(traj, spec=_spec(SCEPTER_ROOT, "scepter"))
        self.assertEqual(tuple(layer["key"] for layer in data["layers"]), LAYERS)
        for layer in data["layers"]:
            for key in ("value", "unit", "source", "confidence"):
                self.assertIn(key, layer)
            self.assertTrue(str(layer["source"]).strip())
            if layer["value"] is None:
                self.assertTrue(str(layer.get("unavailable_reason") or "").strip())

    def test_report_section_has_seven_layer_lines(self):
        self.assertIn("【九】", self.report)
        spec = _spec(SCEPTER_ROOT, "scepter")
        labels = [spec["layers"][key]["label"] for key in LAYERS]
        section = self.report.split("【九】", 1)[1]
        for label in labels:
            self.assertIn(label, section)
        # 17 个锚点与上限都写在报告里，而不是代码常量。
        self.assertIn("17 个锚点", section)
        self.assertIn("33550336", section)

    def test_panel_uses_existing_bar_component(self):
        self.assertIn("权杖", self.html)
        start = self.html.find("<h2>权杖</h2>")
        self.assertGreaterEqual(start, 0)
        block = self.html[start:start + 2400]
        self.assertIn('class="bar"', block)
        self.assertIn('<i style="width:', block)

    def test_origin_toggle_keeps_fingerprint(self):
        _c1, _d1, plain = _run(ORIGIN_ROOT, "origin", 120)
        _c2, _d2, watched = _run(ORIGIN_ROOT, "origin", 120)
        before = plain.final.digest()
        scepter.summary(plain, spec=_spec(ORIGIN_ROOT, "origin"))
        self.assertEqual(plain.final.digest(), before)
        self.assertEqual(plain.final.digest(), watched.final.digest())

    def test_origin_cli_toggle_keeps_json_payload(self):
        base = ["--root", "worlds/origin", "--preset", "origin",
                "--frames", "120", "--no-terminal", "--json"]
        off = _subprocess(base)
        on = _subprocess(base + ["--scepter"])
        # 断言失败时 run.py 以 1 退出；这里只验 JSON 载荷（它仍会打印）。
        self.assertIn(off.returncode, (0, 1), off.stderr)
        self.assertIn(on.returncode, (0, 1), on.stderr)
        self.assertNotIn("权杖状态", off.stdout)
        self.assertIn("权杖状态", on.stdout)
        self.assertEqual(_payload(off.stdout), _payload(on.stdout))


if __name__ == "__main__":
    unittest.main()
