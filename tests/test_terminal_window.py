"""独立 CLI 窗口（`apps/terminal_window.py`）：渲染、答案解析、完整消息循环。"""
from __future__ import annotations

import io
import json
import socket
import threading
import unittest
from unittest import mock

from _support import ROOT      # noqa: F401

from apps.terminal_window import parse_answer, render_msg, run


class PureTest(unittest.TestCase):
    def test_render_msg(self):
        self.assertEqual(render_msg({"text": "hello"}), ">>> hello")
        self.assertEqual(render_msg({}), ">>> ")

    def test_parse_answer(self):
        opts = ["Y", "n"]
        self.assertEqual(parse_answer("", opts, "Y"), "Y")
        self.assertEqual(parse_answer("y", opts, "Y"), "Y")
        self.assertEqual(parse_answer("N", opts, "Y"), "n")
        self.assertIsNone(parse_answer("maybe", opts, "Y"))

    def test_parse_answer_custom_options(self):
        opts = ["allow", "deny"]
        self.assertEqual(parse_answer("DENY", opts, "allow"), "deny")
        self.assertIsNone(parse_answer("Y", opts, "allow"))


class LoopTest(unittest.TestCase):
    def _server(self, seen):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]

        def serve():
            try:
                conn, _ = srv.accept()
                rf = conn.makefile("r", encoding="utf-8", newline="\n")
                wf = conn.makefile("w", encoding="utf-8", newline="\n")
                seen.append(json.loads(rf.readline()))
                for rec in (
                    {"t": "msg", "frame": 1, "kind": "boot", "text": "hello"},
                    {"t": "prompt", "id": 0, "frame": 2, "text": "写？",
                     "ask": "允许？", "options": ["Y", "n"], "default": "Y"},
                ):
                    wf.write(json.dumps(rec, ensure_ascii=False) + "\n")
                wf.flush()
                seen.append(json.loads(rf.readline()))
                wf.write(json.dumps({"t": "end", "frame": 3,
                                     "verdict": "overwritten"},
                                    ensure_ascii=False) + "\n")
                wf.flush()
                wf.close()
                rf.close()
                conn.close()
            finally:
                srv.close()

        t = threading.Thread(target=serve, daemon=True)
        t.start()
        return port, t

    @mock.patch("builtins.input", return_value="n")
    def test_run_loop(self, _inp):
        seen = []
        port, t = self._server(seen)
        out = io.StringIO()
        run(port, "tok", stream=out, writer=out)
        t.join(2)
        text = out.getvalue()
        self.assertIn("δ-me13 终端", text)
        self.assertIn(">>> hello", text)
        self.assertIn(">>> n", text)
        self.assertIn("演算结束", text)
        self.assertEqual(seen[0]["t"], "ready")
        self.assertEqual(seen[0]["token"], "tok")
        self.assertEqual(seen[1], {"t": "answer", "id": 0, "answer": "n"})

    @mock.patch("builtins.input", side_effect=["maybe", "maybe"])
    def test_invalid_answer_twice_falls_back_to_default(self, inp):
        seen = []
        port, t = self._server(seen)
        out = io.StringIO()
        run(port, "tok", stream=out, writer=out)
        t.join(2)
        self.assertEqual(inp.call_count, 2)
        self.assertEqual(seen[1], {"t": "answer", "id": 0, "answer": "Y"})


if __name__ == "__main__":
    unittest.main()
