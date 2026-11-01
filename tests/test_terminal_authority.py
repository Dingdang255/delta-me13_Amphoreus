"""终端语料的来源、逐卷覆盖率与帧位。

只读：这些断言不跑演算，只读预设文件、跑构建器（写临时目录）并回放少量消息。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import types
import unittest

from _support import ROOT      # noqa: F401  （挂 sys.path + 钉 BLAS 线程）

from apps.terminal import AUTHORITIES, TerminalFeed, load_messages

MESSAGES = os.path.join(ROOT, "presets", "plot-full", "messages.jsonl")
EVENTS = os.path.join(ROOT, "presets", "plot-full", "events.jsonl")
#: 入库的派生抽取（原始卷不入库）：每卷的 `>>>` 行，见构建器的 `--export-sources`。
LINES = os.path.join(ROOT, "lore", "D6_terminal", "terminal_lines.jsonl")
BUILDER = os.path.join(ROOT, "tools", "lore_build", "build_terminal_messages.py")
VERSIONS = ("3.0", "3.1", "3.2", "3.3", "3.4", "3.5", "3.6", "3.7")


def _jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows

#: 原卷里没有 `>>>` 的卷：该段终端只能是手写条目，不得「借位」凑数。
NO_TERMINAL_VERSIONS = ("3.0", "3.1", "3.2", "3.3")

#: 必须逐字覆盖全卷 `>>>` 的三卷。
COVERED_VERSIONS = ("3.4", "3.6", "3.7")

_TEMPLATE = re.compile(r"\{\{([^{}]*)\}\}")


def _norm(text):
    """归一化：去 `{{颜色|…}}` 模板、折叠空白（与构建器同口径）。"""
    text = _TEMPLATE.sub(lambda m: m.group(1).split("|")[-1], str(text or ""))
    return " ".join(text.split())


def _gt_lines(version):
    """某卷里所有 `>>>` 行（保留前缀与 █，去掉排版标记）。

    读的是入库的派生抽取 `lore/D6_terminal/terminal_lines.jsonl` —— 原始卷不入库，
    CI 上没有；`build_terminal_messages.py --export-sources` 负责重建这份抽取。
    """
    out = []
    for row in _jsonl(LINES):
        if str(row.get("chapter")) != version:
            continue
        body = _norm(row.get("text"))       # 派生抽取里已带 `>>>` 前缀
        if body:
            out.append(body)
    return out


def _events():
    """events.jsonl 里所有 payload.event。"""
    names = set()
    with open(EVENTS, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            name = (json.loads(line).get("payload") or {}).get("event")
            if name:
                names.add(name)
    return names


def _builder():
    sys.path.insert(0, os.path.dirname(BUILDER))
    try:
        import build_terminal_messages as builder
    finally:
        sys.path.pop(0)
    return builder


def _state(score=None):
    return types.SimpleNamespace(score=dict(score or {}))


def _write(dirpath, rows, name="messages.jsonl"):
    path = os.path.join(dirpath, name)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def _md5(path):
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def _chapter_of_frame(frame):
    return _builder()._chapter_of_frame(frame)


class PlotFullMessagesTest(unittest.TestCase):
    """plot-full 的终端消息：规模、触发条件、权限层级、来源。"""

    def test_at_least_150_messages(self):
        msgs = load_messages(MESSAGES)
        self.assertGreaterEqual(len(msgs), 150)

    def test_every_message_has_a_valid_trigger(self):
        events = _events()
        msgs = load_messages(MESSAGES)
        for i, msg in enumerate(msgs, 1):
            frame, need = msg.get("frame"), msg.get("require_event")
            with self.subTest(line=i, text=msg["text"][:20]):
                self.assertTrue(
                    (isinstance(frame, int) and not isinstance(frame, bool) and frame > 0)
                    or (isinstance(need, str) and need in events),
                    "每条消息都要有正整数 frame，或一个 events.jsonl 里真有的 require_event")
                if need:
                    self.assertIn(need, events)

    def test_authority_is_legal(self):
        for msg in load_messages(MESSAGES):
            self.assertIn(msg["authority"], AUTHORITIES)

    def test_every_message_carries_a_source(self):
        """每条消息都能说清出处（原文行号或预设手写）。"""
        for i, msg in enumerate(load_messages(MESSAGES), 1):
            with self.subTest(line=i, text=msg["text"][:20]):
                self.assertTrue(str(msg.get("source") or "").strip())

    def test_no_fabricated_terminal_in_early_volumes(self):
        """3.0–3.3 原卷没有 `>>>`：该段只能是手写条目，且必须带 source。"""
        for ver in NO_TERMINAL_VERSIONS:
            self.assertEqual(_gt_lines(ver), [],
                             "%s 里出现了 `>>>`，本断言的前提已变" % ver)
        for i, msg in enumerate(load_messages(MESSAGES), 1):
            if _chapter_of_frame(msg.get("frame")) not in NO_TERMINAL_VERSIONS:
                continue
            source = str(msg.get("source") or "")
            with self.subTest(line=i, text=msg["text"][:20]):
                self.assertTrue(source.strip(), "3.0–3.3 的每条都要有 source")
                self.assertFalse(
                    source.startswith("S-024:amphoreus_"),
                    "3.0–3.3 原卷没有 `>>>`，不该有逐字溯源条目：%s" % source)

    def test_builder_has_no_per_chapter_quota(self):
        """「每章 ≥12」是编造出来的门槛，构建器里不该再有它。"""
        self.assertFalse(hasattr(_builder(), "MIN_PER_CHAPTER"))

    def test_late_volumes_cover_every_unique_terminal_line(self):
        """3.4 / 3.6 / 3.7 的 `>>>` 唯一文本必须全部进消息文件。"""
        texts = {_norm(msg["text"]) for msg in load_messages(MESSAGES)}
        for ver in COVERED_VERSIONS:
            lines = _gt_lines(ver)
            self.assertTrue(lines, "%s 应该有 `>>>` 行" % ver)
            missing = sorted({_norm(t) for t in lines} - texts)
            with self.subTest(version=ver):
                self.assertEqual(missing, [], "缺 %d 条：%s" % (len(missing), missing[:5]))

    def test_frames_are_monotonic(self):
        """帧升序；构建器产出的条目（带原文行号）帧严格递增。"""
        msgs = load_messages(MESSAGES)
        frames = [m["frame"] for m in msgs if m.get("frame") is not None]
        self.assertEqual(frames, sorted(frames))
        generated = [m["frame"] for m in msgs
                     if str(m.get("source") or "").startswith("S-024:")
                     and m.get("frame") is not None]
        for prev, cur in zip(generated, generated[1:]):
            self.assertLess(prev, cur, "构建器产出的帧必须严格递增")


class AuthorityFilterTest(unittest.TestCase):
    """`TerminalFeed(authorities=...)`：只播放指定层级。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.out = []

    def tearDown(self):
        self._tmp.cleanup()

    def _feed(self, rows, authorities=None):
        msgs = load_messages(_write(self.tmp, rows))
        return TerminalFeed(msgs, write=self.out.append, authorities=authorities)

    def test_filter_keeps_only_selected_level(self):
        rows = [
            {"frame": 1, "text": "g", "authority": "guest"},
            {"frame": 1, "text": "u", "authority": "user"},
            {"frame": 1, "text": "a", "authority": "admin"},
            {"frame": 1, "kind": "status", "text": "k", "authority": "kernel"},
        ]
        self._feed(rows, ["admin", "kernel"])(1, _state())
        self.assertEqual(self.out, [">>> a", ">>> k"])

    def test_no_filter_plays_every_level(self):
        rows = [
            {"frame": 1, "text": "g", "authority": "guest"},
            {"frame": 1, "text": "u"},
            {"frame": 1, "text": "a", "authority": "admin"},
            {"frame": 1, "text": "k", "authority": "kernel"},
        ]
        self._feed(rows)(1, _state())
        self.assertEqual(self.out, [">>> g", ">>> u", ">>> a", ">>> k"])

    def test_unknown_level_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            TerminalFeed([], write=self.out.append, authorities=["root"])
        self.assertIn("root", str(ctx.exception))


class InvalidMessageTest(unittest.TestCase):
    """启动即报错：非法 authority、缺触发条件；事件触发的消息照常播放。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.out = []

    def tearDown(self):
        self._tmp.cleanup()

    def test_invalid_authority_is_loud_and_carries_line(self):
        path = _write(self.tmp, [
            {"frame": 1, "text": "ok"},
            {"frame": 2, "text": "x", "authority": "root"},
        ])
        with self.assertRaises(ValueError) as ctx:
            load_messages(path)
        self.assertIn("L2", str(ctx.exception))
        self.assertIn("authority", str(ctx.exception))

    def test_missing_trigger_is_loud_and_carries_line(self):
        path = _write(self.tmp, [
            {"frame": 1, "text": "ok"},
            {"text": "no frame, no event"},
        ])
        with self.assertRaises(ValueError) as ctx:
            load_messages(path)
        self.assertIn("L2", str(ctx.exception))
        self.assertIn("frame", str(ctx.exception))

    def test_event_only_message_waits_for_its_event(self):
        path = _write(self.tmp, [{"text": "late", "require_event": "x"}])
        msgs = load_messages(path)
        self.assertNotIn("frame", msgs[0])
        feed = TerminalFeed(msgs, write=self.out.append)
        feed(10, _state())
        self.assertEqual(self.out, [])
        feed(20, _state({"emitted_x": 1.0}))
        self.assertEqual(self.out, [">>> late"])
        feed(30, _state({"emitted_x": 1.0}))
        self.assertEqual(self.out, [">>> late"])      # 只播放一次


class BuilderIdempotenceTest(unittest.TestCase):
    """构建器连跑两次输出逐字节相同，且与仓库里的那份一致。"""

    def test_two_runs_are_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "messages.jsonl")
            dossier = os.path.join(tmp, "scepter_dossier.jsonl")
            cmd = [sys.executable, BUILDER, "--out", out, "--dossier-out", dossier]
            digests = []
            for _ in range(2):
                done = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
                self.assertEqual(done.returncode, 0, done.stderr)
                with open(out, encoding="utf-8") as f:
                    self.assertGreaterEqual(
                        sum(1 for line in f if line.strip()), 150)
                digests.append(_md5(out))
            self.assertEqual(digests[0], digests[1])
            self.assertEqual(digests[1], _md5(MESSAGES))


if __name__ == "__main__":
    unittest.main()
