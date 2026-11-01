"""本地 socket 桥（`apps/terminal_bridge.py`）：握手、消息、阻塞提问、超时/断连。

测试用注入的假子进程在本地线程里连入，不真的开控制台窗口。
"""
from __future__ import annotations

import json
import socket
import subprocess
import threading
import time
import unittest

from _support import ROOT      # noqa: F401  （挂 sys.path + 钉 BLAS 线程）

from apps.terminal_bridge import TerminalBridge


class _FakeProc:
    def __init__(self, thread):
        self._thread = thread

    def wait(self, timeout=None):
        self._thread.join(timeout)
        return 0

    def terminate(self):
        pass


def _child(port, token, seen, answers=None, respond=True, close_after_prompt=False):
    """假子窗口：连入 → ready → 收消息；prompt 按脚本回答或断连。"""
    def run():
        try:
            s = socket.create_connection(("127.0.0.1", port), timeout=5)
        except OSError:
            return
        rf = s.makefile("r", encoding="utf-8", newline="\n")
        wf = s.makefile("w", encoding="utf-8", newline="\n")
        try:
            wf.write(json.dumps({"t": "ready", "token": token},
                                ensure_ascii=False) + "\n")
            wf.flush()
            for line in rf:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                seen.append(rec)
                if rec.get("t") == "prompt":
                    if close_after_prompt:
                        break
                    if respond:
                        ans = (answers.pop(0) if answers
                               else rec.get("default"))
                        wf.write(json.dumps(
                            {"t": "answer", "id": rec.get("id"),
                             "answer": ans}, ensure_ascii=False) + "\n")
                        wf.flush()
                elif rec.get("t") == "end":
                    break
        except (OSError, ValueError):
            pass
        finally:
            try:
                wf.close()
                rf.close()
                s.close()
            except OSError:
                pass

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return _FakeProc(t)


class BridgeTest(unittest.TestCase):
    def _start(self, **kw):
        seen = []
        answers = kw.pop("answers", None)
        b = TerminalBridge(
            timeout=kw.pop("timeout", 2.0),
            ready_timeout=kw.pop("ready_timeout", 2.0),
            spawn=lambda port, token: _child(port, token, seen,
                                             answers=answers, **kw))
        self.assertTrue(b.start(ROOT))
        return b, seen

    def test_msg_and_end(self):
        b, seen = self._start()
        b.msg({"frame": 1, "kind": "boot", "text": "hello"})
        b.end(5, "overwritten")
        b.close()
        self.assertEqual(seen[0]["t"], "msg")
        self.assertEqual(seen[0]["text"], "hello")
        self.assertEqual(seen[-1]["t"], "end")
        self.assertEqual(seen[-1]["verdict"], "overwritten")

    def test_prompt_returns_answer(self):
        b, seen = self._start(answers=["n"])
        got = b.prompt({"frame": 7, "id": 0, "text": "write?",
                        "ask": "允许？", "options": ["Y", "n"], "default": "Y"})
        self.assertEqual(got, "n")
        b.close()
        self.assertEqual(seen[0]["t"], "prompt")
        self.assertEqual(seen[0]["id"], 0)

    def test_prompt_timeout_returns_none(self):
        b, _ = self._start(respond=False, timeout=0.15)
        got = b.prompt({"frame": 7, "id": 0, "text": "q",
                        "options": ["Y", "n"], "default": "Y"})
        self.assertIsNone(got)
        b.close()

    def test_prompt_eof_returns_none(self):
        b, _ = self._start(close_after_prompt=True, timeout=2.0)
        got = b.prompt({"frame": 7, "id": 0, "text": "q",
                        "options": ["Y", "n"], "default": "Y"})
        self.assertIsNone(got)
        b.close()

    def test_prompt_after_close_returns_none(self):
        b, _ = self._start()
        b.close()
        self.assertIsNone(b.prompt({"frame": 1, "id": 0, "text": "q"}))

    def test_start_fails_when_spawn_returns_none(self):
        b = TerminalBridge(ready_timeout=0.2, spawn=lambda port, token: None)
        self.assertFalse(b.start(ROOT))
        b.close()

    def test_start_fails_on_token_mismatch(self):
        def bad(port, token):
            def run():
                s = socket.create_connection(("127.0.0.1", port), timeout=2)
                f = s.makefile("w", encoding="utf-8", newline="\n")
                f.write(json.dumps({"t": "ready", "token": "wrong"}) + "\n")
                f.flush()
                s.close()
            t = threading.Thread(target=run, daemon=True)
            t.start()
            return _FakeProc(t)

        b = TerminalBridge(ready_timeout=1.0, spawn=bad)
        self.assertFalse(b.start(ROOT))
        b.close()


class ClosePolicyTest(unittest.TestCase):
    """收尾策略：已经通知过结束的窗口不杀 —— 它在等读者按回车，自己关。"""

    class _Stuck:
        """收到 end 仍不退出（真实窗口演算完就停在这儿）。"""

        def __init__(self):
            self.terminated = False

        def wait(self, timeout=None):
            raise subprocess.TimeoutExpired("child", timeout)

        def terminate(self):
            self.terminated = True

    def _bridge(self, ready=True):
        proc = self._Stuck()

        def spawn(port, token):
            def run():
                s = socket.create_connection(("127.0.0.1", port), timeout=5)
                f = s.makefile("w", encoding="utf-8", newline="\n")
                f.write(json.dumps({"t": "ready", "token": token}) + "\n")
                f.flush()
                time.sleep(0.3)
                try:
                    s.close()
                except OSError:
                    pass
            if ready:
                threading.Thread(target=run, daemon=True).start()
            return proc

        b = TerminalBridge(timeout=1.0, ready_timeout=2.0, spawn=spawn)
        self.assertTrue(b.start(ROOT))
        return b, proc

    def test_close_after_end_leaves_the_window_open(self):
        b, proc = self._bridge()
        b.end(10, "origin_closed")
        b.close()
        self.assertFalse(proc.terminated)

    def test_start_failure_still_kills_the_child(self):
        """没连上的子进程（握手失败）照旧清掉 —— 只有「已通知结束」的才留。"""
        proc = self._Stuck()
        b = TerminalBridge(ready_timeout=0.2,
                           spawn=lambda port, token: proc)
        self.assertFalse(b.start(ROOT))
        b.close()
        self.assertTrue(proc.terminated)


if __name__ == "__main__":
    unittest.main()
