"""Branch behaviour of the terminal feed (ADR-0004).

    python -m unittest tests.test_terminal_branch
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from apps import terminal

STATE = SimpleNamespace(score={})


def messages():
    return [
        {
            "id": "T1", "frame": 0, "kind": "prompt", "text": ">>>未知来源的程序 ",
            "ask": "是否允许写入？",
            "options": ["deny", "allow"],
            "option_labels": {"deny": "保持沉默", "allow": "（成像）"},
            "default": "deny",
            "on_choice": {
                "deny": {"jump": "T3", "rejoin": "T4"},
                "allow": {"jump": "T2", "rejoin": "T4"},
            },
        },
        {"id": "T2", "frame": 0, "kind": "log", "text": "写入已获准", "branch": "allow"},
        {"id": "T3", "frame": 0, "kind": "log", "text": "写入被拒绝", "branch": "deny"},
        {"id": "T4", "frame": 0, "kind": "log", "text": "主线继续"},
    ]


class TestTerminalBranch(unittest.TestCase):
    def run_feed(self, ask=False, answer=None):
        out = []
        answers = iter(answer if isinstance(answer, list) else [answer])
        feed = terminal.TerminalFeed(
            messages(), write=out.append, ask=ask,
            ask_fn=(lambda _prompt: next(answers)) if answer is not None else None,
        )
        feed(0, STATE)
        feed.close()
        return out, feed

    def test_default_path_takes_default_branch(self):
        out, feed = self.run_feed()
        joined = "\n".join(out)
        self.assertIn("写入被拒绝", joined)
        self.assertNotIn("写入已获准", joined)
        self.assertIn("主线继续", joined)
        self.assertEqual(feed.ledger(), [
            {"frame": 0, "message": "T1", "option": "deny", "source": "default"}
        ])

    def test_interactive_answer_takes_other_branch(self):
        out, feed = self.run_feed(ask=True, answer=["allow"])
        joined = "\n".join(out)
        self.assertIn("写入已获准", joined)
        self.assertNotIn("写入被拒绝", joined)
        self.assertEqual(feed.ledger()[0]["source"], "user")

    def test_answer_by_label(self):
        out, feed = self.run_feed(ask=True, answer=["（成像）"])
        self.assertIn("写入已获准", "\n".join(out))
        self.assertEqual(feed.ledger()[0]["option"], "allow")

    def test_invalid_answer_falls_back_to_default(self):
        out, feed = self.run_feed(ask=True, answer=["bogus", "bogus"])
        self.assertIn("写入被拒绝", "\n".join(out))
        self.assertEqual(feed.ledger()[0]["source"], "default")

    def test_legacy_string_options_still_work(self):
        out = []
        feed = terminal.TerminalFeed(
            [{"id": "P1", "frame": 0, "kind": "prompt", "text": "继续？",
              "options": ["Y", "n"], "default": "Y"}],
            write=out.append,
        )
        feed(0, STATE)
        feed.close()
        self.assertIn("[Y/n]", "\n".join(out))
        self.assertEqual(feed.ledger()[0]["option"], "Y")

    def test_max_jumps_stops_a_loop(self):
        looped = [
            {"id": "A", "frame": 0, "kind": "prompt", "text": "?",
             "options": ["go"], "default": "go",
             "on_choice": {"go": {"jump": "B"}}},
            {"id": "B", "frame": 0, "kind": "prompt", "text": "?",
             "options": ["go"], "default": "go",
             "on_choice": {"go": {"jump": "A"}}},
        ]
        out = []
        feed = terminal.TerminalFeed(looped, write=out.append, max_jumps=3)
        feed(0, STATE)
        feed.close()
        self.assertLessEqual(len(feed.ledger()), 4)


class TestValidate(unittest.TestCase):
    def test_structured_options_are_normalised(self):
        import json
        import os
        import tempfile
        payload = {
            "frame": 1, "kind": "prompt", "text": "t", "default": "a",
            "options": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False,
                                         encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
            path = f.name
        try:
            msgs = terminal.load_messages(path)
        finally:
            os.unlink(path)
        self.assertEqual(msgs[0]["options"], ["a", "b"])
        self.assertEqual(msgs[0]["option_labels"], {"a": "A", "b": "B"})

    def test_branch_without_default_is_rejected(self):
        import json
        import os
        import tempfile
        payload = {
            "frame": 1, "kind": "prompt", "text": "t",
            "options": ["a"], "on_choice": {"a": {"jump": "X"}},
        }
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False,
                                         encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
            path = f.name
        try:
            with self.assertRaises(ValueError):
                terminal.load_messages(path)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
