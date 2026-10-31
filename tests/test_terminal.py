"""只读终端层（`apps/terminal.py`）：校验、按帧顺序、事件过滤、非交互默认答案。

终端层是只读钩子：它不写 `st`、不改账本，`__call__` 恒返回 True（绝不触发剪枝）。
这里只验这些性质，不跑演算。
"""
from __future__ import annotations

import io
import json
import os
import tempfile
import types
import unittest
from unittest import mock

from _support import ROOT      # noqa: F401  （挂 sys.path + 钉 BLAS 线程）

from apps.terminal import KINDS, TerminalFeed, load_messages


def _write(dirpath, rows, name="messages.jsonl"):
    """把若干行（dict 或原始字符串）写成一份 jsonl，返回路径。"""
    path = os.path.join(dirpath, name)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            line = row if isinstance(row, str) else json.dumps(row, ensure_ascii=False)
            f.write(line + "\n")
    return path


def _state(score=None):
    return types.SimpleNamespace(score=dict(score or {}))


def _rich_state(score=None):
    """带 origin / memory_bank 的只读状态，用于模板变量测试。"""
    origin = types.SimpleNamespace(
        tomb_cycles=7, tomb_rows=3, tomb_volume=0.5,
        energy=2.5, selfhood=0.25, companion_stage=3)
    return types.SimpleNamespace(
        score=dict(score or {}), origin=origin,
        memory_bank=types.SimpleNamespace(shape=(12, 13)))


class LoadMessagesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_missing_file_is_empty(self):
        self.assertEqual(load_messages(os.path.join(self.tmp, "nope.jsonl")), [])
        self.assertEqual(load_messages(None), [])

    def test_default_kind_is_log(self):
        msgs = load_messages(_write(self.tmp, [{"frame": 3, "text": "x"}]))
        self.assertEqual(msgs[0]["kind"], "log")

    def test_rows_are_sorted_by_frame(self):
        msgs = load_messages(_write(self.tmp, [
            {"frame": 9, "text": "c"},
            {"frame": 2, "text": "a"},
            {"frame": 5, "text": "b"},
        ]))
        self.assertEqual([m["frame"] for m in msgs], [2, 5, 9])
        self.assertEqual([m["text"] for m in msgs], ["a", "b", "c"])

    def test_blank_lines_are_ignored(self):
        msgs = load_messages(_write(self.tmp, ["", '{"frame": 1, "text": "x"}', "  "]))
        self.assertEqual(len(msgs), 1)

    def test_invalid_rows_carry_line_number(self):
        good = {"frame": 0, "text": "ok"}
        cases = [
            ({"text": "x"}, "frame"),
            ({"frame": -1, "text": "x"}, "frame"),
            ({"frame": 1.5, "text": "x"}, "frame"),
            ({"frame": 0, "kind": "nope", "text": "x"}, "kind"),
            ({"frame": 0, "text": "   "}, "text"),
            ({"frame": 0, "text": "x", "options": []}, "options"),
            ({"frame": 0, "text": "x", "options": ["Y", 1]}, "options"),
            ({"frame": 0, "text": "x", "options": ["Y"], "default": "n"}, "default"),
            ({"frame": 0, "text": "x", "require_event": ""}, "require_event"),
            ({"frame": 0, "text": "x", "suppress_if_event": 3}, "suppress_if_event"),
        ]
        for row, needle in cases:
            path = _write(self.tmp, [good, row])
            with self.subTest(row=row):
                with self.assertRaises(ValueError) as ctx:
                    load_messages(path)
                self.assertIn("L2", str(ctx.exception))       # 行号
                self.assertIn(needle, str(ctx.exception))     # 原因

    def test_invalid_json_is_loud(self):
        path = _write(self.tmp, ["{not json}"])
        with self.assertRaises(ValueError) as ctx:
            load_messages(path)
        self.assertIn("L1", str(ctx.exception))

    def test_plot_sample_covers_every_kind(self):
        path = os.path.join(ROOT, "presets", "plot", "messages.jsonl")
        msgs = load_messages(path)
        self.assertGreaterEqual(len(msgs), 12)
        self.assertEqual({m["kind"] for m in msgs}, set(KINDS))

    def test_period_is_expanded(self):
        path = _write(self.tmp, [
            {"frame": 0, "text": "tick", "period": 10, "until": 25},
        ])
        msgs = load_messages(path)
        self.assertEqual([m["frame"] for m in msgs], [0, 10, 20])

    def test_period_requires_until(self):
        path = _write(self.tmp, [{"frame": 0, "text": "tick", "period": 10}])
        with self.assertRaises(ValueError) as ctx:
            load_messages(path)
        self.assertIn("until", str(ctx.exception))

    def test_unknown_template_variable_is_loud(self):
        path = _write(self.tmp, [
            {"frame": 0, "text": "{nope}", "vars": ["nope"]},
        ])
        with self.assertRaises(ValueError) as ctx:
            load_messages(path)
        self.assertIn("vars", str(ctx.exception))

    def test_template_requires_vars_whitelist(self):
        path = _write(self.tmp, [{"frame": 0, "text": "{cycle}"}])
        with self.assertRaises(ValueError) as ctx:
            load_messages(path)
        self.assertIn("vars", str(ctx.exception))

    def test_period_expansion_is_bounded(self):
        path = _write(self.tmp, [
            {"frame": 0, "text": "tick", "period": 1, "until": 10},
        ])
        with self.assertRaises(ValueError) as ctx:
            load_messages(path, max_messages=5)
        self.assertIn("上限", str(ctx.exception))


class TerminalFeedTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.out = []

    def tearDown(self):
        self._tmp.cleanup()

    def _feed(self, rows, ask=False):
        msgs = load_messages(_write(self.tmp, rows))
        return TerminalFeed(msgs, write=self.out.append, ask=ask)

    def test_consumes_in_frame_order_with_prefix(self):
        feed = self._feed([{"frame": 5, "text": "b"}, {"frame": 2, "text": "a"}])
        self.assertTrue(feed(4, _state()))
        self.assertEqual(self.out, [">>> a"])
        self.assertTrue(feed(5, _state()))
        self.assertEqual(self.out, [">>> a", ">>> b"])
        self.assertTrue(feed(9, _state()))          # 没有新消息也恒为 True
        self.assertEqual(self.out, [">>> a", ">>> b"])

    def test_returns_true_when_empty_and_after_close(self):
        feed = TerminalFeed([], write=self.out.append)
        self.assertIs(feed(0, _state()), True)
        feed.close()
        self.assertIs(feed(10, _state()), True)
        self.assertEqual(self.out, [])

    def test_future_messages_are_not_flushed_by_close(self):
        feed = self._feed([{"frame": 100, "text": "future"}])
        feed(10, _state())
        feed.close()
        self.assertEqual(self.out, [])

    def test_require_event_filters(self):
        rows = [{"frame": 5, "text": "gated", "require_event": "pilgrimage"}]
        self._feed(rows)(5, _state())
        self.assertEqual(self.out, [])
        self.out.clear()
        self._feed(rows)(5, _state({"emitted_pilgrimage": 3.0}))
        self.assertEqual(self.out, [">>> gated"])

    def test_suppress_if_event_filters(self):
        rows = [{"frame": 5, "text": "skipped", "suppress_if_event": "done"}]
        self._feed(rows)(5, _state({"emitted_done": 1.0}))
        self.assertEqual(self.out, [])
        self._feed(rows)(5, _state())
        self.assertEqual(self.out, [">>> skipped"])

    def test_prompt_non_tty_uses_default(self):
        rows = [{"frame": 0, "kind": "prompt", "text": "未知程序 Philia093.exe",
                 "ask": "是否允许写入？", "options": ["Y", "n"], "default": "Y"}]
        with mock.patch("sys.stdin", io.StringIO("")):
            self._feed(rows, ask=True)(0, _state())
        self.assertEqual(
            self.out,
            [">>> 未知程序 Philia093.exe 是否允许写入？ [Y/n] → Y（默认）"])

    def test_prompt_without_ask_flag_never_reads_stdin(self):
        rows = [{"frame": 0, "kind": "prompt", "text": "q", "ask": "继续？"}]
        fake_stdin = types.SimpleNamespace(isatty=lambda: True)

        def _boom(*_a, **_k):
            raise AssertionError("未加 --terminal-ask 时不应读取标准输入")

        with mock.patch("sys.stdin", fake_stdin), \
                mock.patch("builtins.input", side_effect=_boom):
            self._feed(rows, ask=False)(0, _state())
        self.assertEqual(self.out, [">>> q 继续？ [Y/n] → Y（默认）"])

    def test_prompt_interactive_takes_valid_answer(self):
        rows = [{"frame": 0, "kind": "prompt", "text": "q", "ask": "继续？"}]
        fake_stdin = types.SimpleNamespace(isatty=lambda: True)
        with mock.patch("sys.stdin", fake_stdin), \
                mock.patch("builtins.input", side_effect=["n"]):
            self._feed(rows, ask=True)(0, _state())
        self.assertEqual(self.out, [">>> q 继续？ [Y/n] → n"])

    def test_prompt_interactive_invalid_twice_falls_back(self):
        rows = [{"frame": 0, "kind": "prompt", "text": "q", "ask": "继续？"}]
        fake_stdin = types.SimpleNamespace(isatty=lambda: True)
        with mock.patch("sys.stdin", fake_stdin), \
                mock.patch("builtins.input", side_effect=["maybe", "maybe"]) as inp:
            self._feed(rows, ask=True)(0, _state())
        self.assertEqual(inp.call_count, 2)                     # 重问一次
        self.assertEqual(self.out, [">>> q 继续？ [Y/n] → Y（默认）"])

    def test_template_variables_are_rendered(self):
        rows = [{"frame": 12030, "text": "第 {cycle} 轮 · 大墓 {tomb_cycles} 世 · {memory_rows} 行",
                 "vars": ["cycle", "tomb_cycles", "memory_rows"],
                 "cycle_from": 12020}]
        self._feed(rows)(12030, _rich_state())
        self.assertEqual(self.out, [">>> 第 11 轮 · 大墓 7 世 · 12 行"])

    def test_does_not_write_state(self):
        score = {"entropy": 0.25, "emitted_x": 7.0}
        st = _state(score)
        before = dict(st.score)
        feed = self._feed([
            {"frame": 0, "text": "a", "require_event": "x"},
            {"frame": 0, "text": "b", "suppress_if_event": "y"},
            {"frame": 0, "kind": "prompt", "text": "q"},
        ])
        with mock.patch("sys.stdin", io.StringIO("")):
            feed(0, st)
        self.assertEqual(st.score, before)
        self.assertIsInstance(st.score, dict)


class NarrativeFlagTest(unittest.TestCase):
    """`run.py` 的三态开关：CLI 显式给了就压过预设，否则读 `narrative` 表。"""

    def test_cli_overrides_preset(self):
        from run import _narrative_flag

        self.assertTrue(_narrative_flag(True, {"terminal": False}, "terminal"))
        self.assertFalse(_narrative_flag(False, {"terminal": True}, "terminal"))

    def test_falls_back_to_preset(self):
        from run import _narrative_flag

        self.assertTrue(_narrative_flag(None, {"terminal": True}, "terminal"))
        self.assertFalse(_narrative_flag(None, {"terminal": False}, "terminal"))
        self.assertFalse(_narrative_flag(None, {}, "terminal"))
        self.assertFalse(_narrative_flag(None, None, "terminal"))


class _Sink:
    def __init__(self, answers=None, fail=False):
        self.msgs = []
        self.prompts = []
        self.answers = list(answers or [])
        self.fail = fail

    def msg(self, rec):
        if self.fail:
            raise OSError("closed")
        self.msgs.append(rec)

    def prompt(self, rec):
        if self.fail:
            raise OSError("closed")
        self.prompts.append(rec)
        return self.answers.pop(0) if self.answers else rec.get("default")


class SinkTest(unittest.TestCase):
    """独立 CLI 窗口的 sink：消息镜像、阻塞提问、失败不拖垮演算。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.out = []

    def tearDown(self):
        self._tmp.cleanup()

    def _feed(self, rows, sink, ask=False):
        msgs = load_messages(_write(self.tmp, rows))
        return TerminalFeed(msgs, write=self.out.append, ask=ask, sink=sink)

    def test_msg_is_mirrored_to_sink(self):
        sink = _Sink()
        self._feed([{"frame": 0, "text": "hello"}], sink)(0, _state())
        self.assertEqual(self.out, [">>> hello"])
        self.assertEqual([m["text"] for m in sink.msgs], ["hello"])

    def test_prompt_uses_sink_answer(self):
        sink = _Sink(answers=["n"])
        rows = [{"frame": 0, "kind": "prompt", "text": "写？",
                 "ask": "允许？", "options": ["Y", "n"], "default": "Y"}]
        with mock.patch("builtins.input", side_effect=AssertionError("不应读 stdin")):
            self._feed(rows, sink)(0, _state())
        self.assertEqual(sink.prompts[0]["id"], 0)
        self.assertEqual(self.out, [">>> 写？ 允许？ [Y/n] → n"])

    def test_prompt_invalid_sink_answer_falls_back(self):
        sink = _Sink(answers=["maybe"])
        rows = [{"frame": 0, "kind": "prompt", "text": "q",
                 "options": ["Y", "n"], "default": "Y"}]
        self._feed(rows, sink)(0, _state())
        self.assertEqual(self.out, [">>> q [Y/n] → Y（默认）"])

    def test_sink_failure_does_not_crash(self):
        sink = _Sink(fail=True)
        rows = [
            {"frame": 0, "text": "hello"},
            {"frame": 0, "kind": "prompt", "text": "q", "default": "Y"},
        ]
        self._feed(rows, sink)(0, _state())
        self.assertEqual(self.out, [">>> hello", ">>> q [Y/n] → Y（默认）"])


if __name__ == "__main__":
    unittest.main()
