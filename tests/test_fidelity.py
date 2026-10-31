"""Contract tests for the fidelity gate and the narrative panels (P7).

    python -m unittest tests.test_fidelity

The gate must be read-only, its pass/fail must follow the thresholds in
``config/fidelity.json``, and the report must stay byte-identical when the
fidelity section is not enabled.
"""
from __future__ import annotations

import hashlib
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tests._support import load  # noqa: E402  （挂 sys.path + 钉 BLAS 线程）

from apps import agents, canon, dialogue, fidelity, render, scenes, trends  # noqa: E402
from apps import viz  # noqa: E402


def _digest_tree(*paths):
    """sha256 of every file under the given paths, keyed by relative path."""
    out = {}
    for root in paths:
        for base, _dirs, names in os.walk(root):
            for name in sorted(names):
                path = os.path.join(base, name)
                rel = os.path.relpath(path, ROOT)
                with open(path, "rb") as f:
                    out[rel] = hashlib.sha256(f.read()).hexdigest()
    return out


class FidelityGateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = fidelity.evaluate()

    def test_spec_shape(self):
        spec = fidelity.load_spec()
        self.assertEqual(len(spec["dimensions"]), 8)
        self.assertAlmostEqual(sum(d["weight"] for d in spec["dimensions"].values()), 1.0)
        self.assertTrue(0.0 < spec["threshold"] < 1.0)

    def test_every_dimension_reports_four_metrics(self):
        for name, row in self.report["dimensions"].items():
            self.assertEqual(set(row["metrics"]),
                             {"coverage", "traceability", "verbatim", "consistency"}, name)
            self.assertGreater(row["entries"], 0, name)
            self.assertTrue(0.0 <= row["score"] <= 1.0, name)

    def test_pass_follows_thresholds(self):
        spec = fidelity.load_spec()
        rows = self.report["dimensions"]
        expected = (self.report["weighted_score"] >= spec["threshold"]
                    and all(row["score"] >= spec["dimension_floor"] for row in rows.values()))
        self.assertEqual(self.report["pass"], expected)
        self.assertEqual(bool(self.report["failures"]), not expected)

    def test_gaps_are_counted_not_removed(self):
        rows = self.report["dimensions"]
        d3 = {p["id"]: p for p in rows["D3_plot"]["penalties"]}["chapter_unknown"]
        self.assertEqual(d3["count"], 1)
        self.assertEqual(d3["denominator"], 8)
        self.assertGreater(d3["amount"], 0.0)

        d8 = {p["id"]: p for p in rows["D8_characters"]["penalties"]}["scenario_unknown"]
        self.assertEqual(d8["count"], 6)
        self.assertEqual(rows["D8_characters"]["counts"]["scenario"], 81)

        d7 = {p["id"]: p for p in rows["D7_community"]["penalties"]}["channel_missing"]
        self.assertEqual(d7["count"], 7)          # 7/14 渠道有结果；登录墙也算缺口
        self.assertEqual(d7["denominator"], 14)
        self.assertEqual(rows["D7_community"]["counts"]["fragment"], 27)

    def test_gate_is_read_only_and_deterministic(self):
        before = _digest_tree(os.path.join(ROOT, "lore", "canon"),
                              os.path.join(ROOT, "config"))
        first = fidelity.evaluate()
        second = fidelity.evaluate()
        after = _digest_tree(os.path.join(ROOT, "lore", "canon"),
                             os.path.join(ROOT, "config"))
        self.assertEqual(before, after)
        self.assertEqual(first, second)

    def test_threshold_is_the_only_knob(self):
        spec = fidelity.load_spec()
        strict = dict(spec, threshold=1.01)
        strict = fidelity.evaluate(spec=strict)
        self.assertFalse(strict["pass"])
        self.assertTrue(strict["failures"])


class ReportDefaultOffTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx, cls.data, cls.traj = load("plot", frames=60, seed=0)

    def _report(self, narrative=None):
        import run
        return run.report(self.ctx, self.data, self.traj, [], explore=True,
                          narrative=narrative)

    def test_flag_defaults_to_off(self):
        import run
        self.assertFalse(run._narrative_flag(None, {}, "fidelity"))
        self.assertTrue(run._narrative_flag(None, {"fidelity": True}, "fidelity"))
        self.assertFalse(run._narrative_flag(False, {"fidelity": True}, "fidelity"))

    def test_default_report_never_touches_fidelity(self):
        with mock.patch.object(fidelity, "evaluate", side_effect=AssertionError("called")):
            text = self._report()
        self.assertNotIn("保真自检", text)
        self.assertEqual(text, self._report(narrative=[]))

    def test_section_is_appended_when_enabled(self):
        text = self._report(narrative=[("【九】保真自检",
                                        fidelity.render(fidelity.evaluate()))])
        self.assertIn("保真自检", text)
        self.assertIn("加权保真分", text)


class NarrativePanelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = canon.CanonBundle.load()
        cls.spec = trends.load_spec()

    def test_two_channels_are_rendered_side_by_side(self):
        view = {"cycle_count": 100000, "embers_taken": 40, "memory_rows": 10,
                "entropy": 0.4, "noise": 0.2}
        rows = [row for row in trends.evaluate_all(self.spec, view)
                if row["trend"] == "TREND-003"]
        self.assertEqual({row["channel"] for row in rows}, {"delay", "tendency"})
        lines = render.trend_pressure_lines(rows)
        self.assertEqual(len(lines), 2)
        self.assertIn("delay", lines[0] + lines[1])
        self.assertIn("tendency", lines[0] + lines[1])

    def test_scene_panel_keeps_gaps_visible(self):
        item = scenes.narrate(scenes.load(self.bundle)[0])
        lines = render.scene_panel_lines(item)
        self.assertTrue(lines)
        self.assertTrue(any("缺口" in line or "逐字" in line for line in lines))

    def test_dialogue_reader_never_picks_a_branch(self):
        result = dialogue.read_scene(self.bundle, "SCN-001")
        self.assertTrue(result["lines"])
        if result["pending"]:
            self.assertIsNone(result.get("choice"))
            self.assertFalse(result["finished"])
        for row in result["lines"]:
            self.assertTrue(row["text"])
            self.assertTrue(row["source"])

    def test_terminal_reader_uses_the_same_channel(self):
        from apps.terminal import TerminalFeed
        seen = []
        result = dialogue.read_scene(self.bundle, "SCN-001")
        feed = TerminalFeed([], write=seen.append)
        feed.play_dialogue(result)
        self.assertTrue(seen)
        self.assertTrue(all(line.startswith(">>> ") for line in seen))

    def test_html_panel_keeps_channels_separate(self):
        view = {"cycle_count": 100000, "embers_taken": 40, "memory_rows": 10,
                "entropy": 0.4, "noise": 0.2}
        rows = [row for row in trends.evaluate_all(self.spec, view)
                if row["trend"] == "TREND-003"]
        html = viz.narrative_panels_html(rows, trends.coverage(self.spec))
        self.assertIn("delay", html)
        self.assertIn("tendency", html)
        self.assertIn("未接线", html)


class ScenarioReuseTest(unittest.TestCase):
    def test_scenario_check_still_separates_unknown(self):
        cards = agents.load_cards()
        statuses = {}
        for entry in canon.CanonBundle.load().of_kind("scenario"):
            result = agents.scenario_check(cards[entry.get("character")], entry.data)
            statuses[result["status"]] = statuses.get(result["status"], 0) + 1
        self.assertEqual(statuses, {"pass": 75, "unknown": 6})


if __name__ == "__main__":
    unittest.main()
