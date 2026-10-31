"""Contract tests for agent cards and the decision step (P5).

    python -m unittest tests.test_agents_contract
"""
from __future__ import annotations

import unittest

from apps import agents

CARDS = agents.load_cards()


class TestCardShape(unittest.TestCase):
    def test_cards_loaded(self):
        self.assertGreaterEqual(len(CARDS), 27)

    def test_every_card_has_three_rules(self):
        for cid, card in CARDS.items():
            self.assertGreaterEqual(len(card.rules), 3, cid)
            for rule in card.rules:
                self.assertTrue(rule.id, cid)
                self.assertTrue(rule.source, f"{cid}/{rule.id}")
                self.assertTrue(rule.then, f"{cid}/{rule.id}")

    def test_every_card_has_speech_and_guards(self):
        for cid, card in CARDS.items():
            self.assertTrue(card.speech, cid)
            self.assertTrue(card.guards, cid)

    def test_unknown_trigger_is_not_executable(self):
        card = agents.from_dict({
            "id": "CHR-999",
            "decision_rules": [
                {"id": "R-1", "when": "UNKNOWN", "then": "x", "priority": 1, "source": "S"},
                {"id": "R-2", "when": "real", "then": "y", "priority": 2, "source": "S"},
            ],
        })
        self.assertEqual([r.id for r in card.executable_rules], ["R-2"])
        self.assertIsNone(agents.decide(card, "UNKNOWN"))


class TestDecision(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.card = agents.from_dict({
            "id": "CHR-900",
            "decision_rules": [
                {"id": "R-900-1", "when": "same", "then": "a", "priority": 2, "source": "S-1"},
                {"id": "R-900-2", "when": "same", "then": "b", "priority": 1, "source": "S-2"},
                {"id": "R-900-3", "when": "other", "then": "c", "priority": 3, "source": "S-3"},
            ],
        })

    def test_priority_wins_and_ambiguity_is_reported(self):
        result = agents.decide(self.card, "same")
        self.assertEqual(result["rule"], "R-900-2")
        self.assertTrue(result["ambiguous"])
        self.assertEqual(set(result["candidates"]), {"R-900-1", "R-900-2"})

    def test_no_match_returns_none(self):
        self.assertIsNone(agents.decide(self.card, "nothing"))

    def test_empty_percept_returns_none(self):
        self.assertIsNone(agents.decide(self.card, ""))

    def test_deterministic(self):
        self.assertEqual(agents.decide(self.card, "other"),
                         agents.decide(self.card, "other"))


class TestAuxiliary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.card = agents.from_dict({
            "id": "CHR-901",
            "decision_rules": [{"id": "R-901-1", "when": "w", "then": "t",
                                "priority": 1, "source": "S"}],
            "relations": [{"target": "CHR-902", "type": "trust", "intensity": 0.9}],
            "emotions": [{"trigger": "loss", "response": "withdraw"}],
            "speech": {"tone": "calm", "sentence_style": "short"},
            "ooc_guards": ["never cruel"],
        })

    def test_relation_update_is_pure_and_clamped(self):
        self.assertEqual(agents.relation_update(self.card, "CHR-902", -0.05), 0.85)
        self.assertEqual(agents.relation_update(self.card, "CHR-902", 1.0), 1.0)
        self.assertEqual(agents.relation_update(self.card, "CHR-902", -5.0), 0.0)
        self.assertIsNone(agents.relation_update(self.card, "CHR-000", 0.1))
        self.assertEqual(self.card.relations[0]["intensity"], 0.9)

    def test_emotion_lookup(self):
        self.assertEqual(agents.emotion_for(self.card, "loss")["response"], "withdraw")
        self.assertIsNone(agents.emotion_for(self.card, "joy"))

    def test_speech_profile_has_no_generated_text(self):
        profile = agents.speech_profile(self.card)
        self.assertEqual(profile["character"], "CHR-901")
        self.assertEqual(profile["tone"], "calm")

    def test_scenario_check_reports_unknown(self):
        scenario = {"id": "T-900", "given": {"percept": "UNKNOWN"},
                    "expect": {"reason": "R-901-1"}}
        self.assertEqual(agents.scenario_check(self.card, scenario)["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
