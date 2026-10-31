"""Contract tests for the read-only dialogue runner (P6a).

    python -m unittest tests.test_dialogue
"""
from __future__ import annotations

import unittest

from apps import canon, dialogue


class TestDialogueCorpus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = canon.CanonBundle.load()

    def test_scene_has_lines(self):
        runner = dialogue.DialogueRunner.from_bundle(self.bundle, "SCN-001")
        self.assertGreater(len(runner.lines()), 10)
        self.assertIsNotNone(runner.current())

    def test_walk_to_end_is_linear(self):
        runner = dialogue.DialogueRunner.from_bundle(self.bundle, "SCN-001")
        steps = 1
        while runner.advance() is not None:
            steps += 1
            if steps > 500:
                self.fail("scene does not terminate")
        self.assertEqual(steps, len(runner.lines()))
        self.assertEqual(len(runner.trace), steps)
        self.assertTrue(runner.finished())

    def test_text_and_provenance_are_preserved(self):
        runner = dialogue.DialogueRunner.from_bundle(self.bundle, "SCN-001")
        line = runner.current()
        self.assertTrue(line.text)
        self.assertTrue(line.source)
        self.assertTrue(line.locator)
        self.assertEqual(line.confidence, "A")

    def test_unknown_scene_raises(self):
        with self.assertRaises(dialogue.DialogueError):
            dialogue.DialogueRunner.from_bundle(self.bundle, "SCN-999")


class TestDialogueRunner(unittest.TestCase):
    LINES = [
        {"id": "D1", "scene_id": "S", "order": 1, "verbatim": "a", "next": ["D2"]},
        {"id": "D2", "scene_id": "S", "order": 2, "verbatim": "b", "next": ["D3", "D4"]},
        {"id": "D3", "scene_id": "S", "order": 3, "verbatim": "c", "next": ["D5"]},
        {"id": "D4", "scene_id": "S", "order": 4, "verbatim": "d", "next": ["D5"]},
        {"id": "D5", "scene_id": "S", "order": 5, "verbatim": "e", "next": []},
    ]

    def test_ambiguous_step_requires_choice(self):
        runner = dialogue.DialogueRunner("S", self.LINES, start="D2")
        with self.assertRaises(dialogue.DialogueError):
            runner.advance()

    def test_choice_selects_branch(self):
        runner = dialogue.DialogueRunner("S", self.LINES, start="D2")
        self.assertEqual(runner.advance("D4").id, "D4")
        self.assertEqual(runner.advance().id, "D5")
        self.assertIsNone(runner.advance())

    def test_dangling_link_raises(self):
        broken = [{"id": "D1", "scene_id": "S", "order": 1, "verbatim": "a",
                   "next": ["missing"]}]
        runner = dialogue.DialogueRunner("S", broken)
        with self.assertRaises(dialogue.DialogueError):
            runner.advance()

    def test_reset_returns_to_start(self):
        runner = dialogue.DialogueRunner("S", self.LINES)
        runner.advance()
        runner.reset()
        self.assertEqual(runner.current().id, "D1")
        self.assertEqual(runner.trace, ["D1"])


if __name__ == "__main__":
    unittest.main()
