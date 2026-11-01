"""Mind layer (`apps/mind.py`): memory, values, rule-first decisions, shadow.

The mind layer is an application-side read-only model: it may read state, but it
must never write it.  These tests pin the parts that matter:

  · the same input under two personas decides differently,
  · the same input under one persona is deterministic,
  · attaching the shadow observer leaves the trajectory fingerprint unchanged,
  · a card survives the round trip through ``MindState`` without loss.
"""
from __future__ import annotations

import json
import os
import tempfile
import types
import unittest

from _support import load

from apps import agents, mind


def _sandbox(tmp, name="mind.json"):
    path = os.path.join(tmp, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def _write_json(path, payload):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False)
    return path


class DecisionTest(unittest.TestCase):
    def setUp(self):
        self.state = mind.MindState(
            character="CHR-1",
            values={"order": 0.9, "bond": 0.9},
            memories=(mind.Memory(id="M-0001-loss", event="loss", weight=0.5,
                                  residue={"order": 0.2}, frame=3),),
            emotion="fear",
            emotion_level=0.5,
        )
        self.options = (
            {"action": "hold", "rule": "R-H", "priority": 2,
             "values": {"order": 0.9, "bond": 0.1}, "emotions": {"fear": 0.0}},
            {"action": "yield", "rule": "R-Y", "priority": 2,
             "values": {"order": 0.1, "bond": 0.9}, "emotions": {"fear": 1.0}},
        )

    @staticmethod
    def _persona(**weights):
        persona = mind.default_persona()
        persona["value_weights"] = dict(weights)
        persona["memory_weight"] = 0.5
        persona["emotion_weight"] = 0.0
        persona["rules"] = (
            {"id": "R-H", "when": "hold", "then": "hold", "priority": 2, "source": "S"},
            {"id": "R-Y", "when": "yield", "then": "yield", "priority": 2, "source": "S"},
        )
        return persona

    def test_different_personas_decide_differently(self):
        order_first = mind.decide(self.state, self.options,
                                  persona=self._persona(order=1.0, bond=0.0))
        bond_first = mind.decide(self.state, self.options,
                                 persona=self._persona(order=0.0, bond=1.0))
        self.assertEqual(order_first["action"], "hold")
        self.assertEqual(bond_first["action"], "yield")
        self.assertNotEqual(order_first["action"], bond_first["action"])

    def test_same_persona_is_deterministic(self):
        persona = self._persona(order=0.3, bond=0.7)
        first = mind.decide(self.state, self.options, persona=persona)
        second = mind.decide(self.state, self.options, persona=persona)
        self.assertEqual(first, second)

    def test_result_is_auditable_through_rule_and_memory_ids(self):
        result = mind.decide(self.state, self.options,
                             persona=self._persona(order=1.0, bond=0.0))
        self.assertEqual(set(result), {"action", "reason", "evidence", "scores"})
        ids = {item["id"] for item in result["evidence"]}
        self.assertIn("R-H", ids)
        self.assertIn("M-0001-loss", ids)
        self.assertEqual({row["option"] for row in result["scores"]},
                         {"hold", "yield"})
        self.assertTrue(all("score" in row for row in result["scores"]))

    def test_rules_win_before_scores(self):
        options = (
            {"action": "obey", "rule": "R-OBEY", "priority": 5},
            {"action": "rebel", "priority": 1},
        )
        persona = mind.default_persona()
        persona["rules"] = ({"id": "R-OBEY", "when": "obey",
                             "then": "obey", "priority": 9, "source": "S"},)
        result = mind.decide(self.state, options, persona=persona)
        self.assertEqual(result["action"], "obey")
        self.assertEqual(result["reason"], "rule R-OBEY")

    def test_rule_conflict_ties_break_on_priority(self):
        options = (
            {"action": "a", "rule": "R-A", "priority": 2},
            {"action": "b", "rule": "R-B", "priority": 1},
        )
        persona = mind.default_persona()
        persona["rules"] = (
            {"id": "R-A", "when": "a", "then": "a", "priority": 2},
            {"id": "R-B", "when": "b", "then": "b", "priority": 1},
        )
        self.assertEqual(mind.decide(self.state, options, persona=persona)["action"],
                         "b")

    def test_empty_options_return_none(self):
        self.assertIsNone(mind.decide(self.state, ()))


class PersonaFileTest(unittest.TestCase):
    def test_values_are_clamped_and_bad_entries_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_json(_sandbox(tmp), {
                "value_weights": {"order": 1.8, "bond": -2, "bad": "x"},
                "memory_weight": 3,
                "emotion_weight": -1,
                "event_values": {"loss": {"order": 2.0}},
                "event_emotions": {"loss": {"emotion": "fear", "level": 1.5}},
            })
            persona = mind.load_persona(path)
        self.assertEqual(persona["value_weights"]["order"], 1.0)
        self.assertEqual(persona["value_weights"]["bond"], 0.0)
        self.assertEqual(persona["value_weights"]["bad"], 0.0)
        self.assertEqual(persona["memory_weight"], 1.0)
        self.assertEqual(persona["emotion_weight"], 0.0)
        self.assertEqual(persona["event_values"]["loss"]["order"], 1.0)
        self.assertEqual(persona["event_emotions"]["loss"]["level"], 1.0)

    def test_preset_path_and_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _sandbox(tmp, os.path.join("presets", "sample", "mind.json"))
            _write_json(path, {"value_weights": {"order": 0.25}})
            found = mind.load_persona(preset="sample", root=tmp)
            missing = mind.load_persona(preset="absent", root=tmp)
        self.assertEqual(found["value_weights"]["order"], 0.25)
        self.assertEqual(missing, mind.default_persona())

    def test_broken_file_falls_back_without_raising(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _sandbox(tmp)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("{not json}")
            persona = mind.load_persona(path)
        self.assertEqual(persona, mind.default_persona())


class CardBridgeTest(unittest.TestCase):
    def test_real_card_round_trips_without_loss(self):
        cards = agents.load_cards()
        card = cards[sorted(cards)[0]]
        state = mind.from_card(card)
        self.assertEqual(state.character, card.id)
        self.assertEqual(state.goals, card.goals)
        self.assertEqual(state.to_card(), card)
        self.assertEqual(mind.to_card(state), card)
        self.assertEqual(mind.from_card(card).to_card(), card)

    def test_agents_decide_keeps_the_old_contract(self):
        card = agents.from_dict({
            "id": "CHR-900",
            "decision_rules": [
                {"id": "R-1", "when": "same", "then": "a", "priority": 2, "source": "S-1"},
                {"id": "R-2", "when": "same", "then": "b", "priority": 1, "source": "S-2"},
            ],
        })
        result = agents.decide(card, "same")
        self.assertEqual(result["rule"], "R-2")
        self.assertTrue(result["ambiguous"])
        self.assertEqual(result["candidates"], ["R-1", "R-2"])
        self.assertEqual(result["matched_by"], "exact")
        self.assertIsNone(agents.decide(card, "nothing"))


class ShadowTest(unittest.TestCase):
    def test_shadow_reads_but_never_writes_state(self):
        state = types.SimpleNamespace(score={"emitted_loss": 0.75, "entropy": 0.2})
        before = dict(state.score)
        shadow = mind.MindShadow(trace=True, options=("hold", "yield"))
        self.assertIs(shadow(0, state), True)
        self.assertEqual(state.score, before)
        self.assertEqual(len(shadow.state.memories), 1)
        self.assertEqual(shadow.state.memories[0].event, "loss")
        self.assertEqual(len(shadow.trace), 1)
        shadow.record_trace(False)
        shadow(1, state)
        self.assertEqual(len(shadow.trace), 1)
        self.assertTrue(shadow.describe())
        self.assertEqual(shadow.summary()["memories"], 1)

    def test_shadow_does_not_change_the_fingerprint(self):
        _ctx, _data, base = load("plot", frames=300)
        shadow = mind.MindShadow(
            persona={"value_weights": {"order": 1.0}},
            options=("hold", "yield"),
            trace=True,
        )
        _ctx2, _data2, watched = load("plot", frames=300, watch=shadow)
        self.assertEqual(base.reached_frame, watched.reached_frame)
        self.assertEqual(base.verdict, watched.verdict)
        self.assertEqual(base.final.digest(), watched.final.digest())
        self.assertGreater(shadow.frames, 0)
        self.assertTrue(shadow.trace)


if __name__ == "__main__":
    unittest.main()
