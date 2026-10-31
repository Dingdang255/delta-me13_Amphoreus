"""Replay every corpus scenario through the decision step (P5).

The corpus stores each scenario as ``given.percept`` plus an expected rule id.
This test asserts the engine reaches the same rule for every executable case,
and reports the ones the corpus itself marks unknown.

    python -m unittest tests.test_character_consistency
"""
from __future__ import annotations

import json
import os
import unittest

from apps import agents

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCENARIOS = os.path.join(ROOT, "lore", "D8_characters", "scenarios.jsonl")


def load_scenarios():
    rows = []
    with open(SCENARIOS, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


class TestScenarioConsistency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cards = agents.load_cards()
        cls.scenarios = load_scenarios()
        cls.results = []
        for scenario in cls.scenarios:
            card = cls.cards.get(scenario.get("character"))
            if card is None:
                continue
            cls.results.append((scenario, agents.scenario_check(card, scenario)))

    def test_all_scenarios_belong_to_known_characters(self):
        missing = [s["id"] for s in self.scenarios if s.get("character") not in self.cards]
        self.assertEqual(missing, [])

    def test_no_mismatch(self):
        bad = [(s["id"], r) for s, r in self.results if r["status"] == "mismatch"]
        self.assertEqual(bad, [])

    def test_executable_pass_rate(self):
        passed = sum(1 for _s, r in self.results if r["status"] == "pass")
        executable = sum(1 for _s, r in self.results if r["status"] in ("pass", "mismatch"))
        self.assertGreater(executable, 0)
        self.assertGreaterEqual(passed / executable, 0.99)

    def test_unknown_cases_are_reported(self):
        unknown = [(s, r) for s, r in self.results if r["status"] == "unknown"]
        # a rule whose trigger is UNKNOWN must surface here, never silently pass
        self.assertGreater(len(unknown), 0)
        self.assertLessEqual(len(unknown), 6)
        for scenario, _result in unknown:
            self.assertEqual(scenario["given"]["percept"], "UNKNOWN")

    def test_official_scenes_are_all_executable(self):
        official = [(s, r) for s, r in self.results if s.get("official_scene")]
        unexecuted = [s["id"] for s, r in official if r["status"] not in ("pass", "mismatch")]
        self.assertEqual(unexecuted, [])


if __name__ == "__main__":
    unittest.main()
