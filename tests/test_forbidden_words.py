"""红线 1：引擎里不许出现专有名词。

把 tools/grep_forbidden.py 的扫描口径搬进单测 —— 于是「引擎混进了剧情名词」
不再只在手动跑工具时才发现。加了新的 engine/*.py 也会被自动纳入。
"""
from __future__ import annotations

import os
import sys
import unittest

from _support import ROOT

sys.path.insert(0, os.path.join(ROOT, "tools"))
import grep_forbidden  # noqa: E402


class ForbiddenWords(unittest.TestCase):
    def test_engine_has_no_proper_nouns(self):
        engine_dir = os.path.join(ROOT, "engine")
        offenders = {}
        for name in sorted(os.listdir(engine_dir)):
            if not name.endswith(".py"):
                continue
            hits = grep_forbidden.scan_file(os.path.join(engine_dir, name))
            if hits:
                offenders[name] = hits
        detail = "\n".join(
            f"engine/{n} L{ln} [{cat}] 「{w}」 → {line[:60]}"
            for n, hits in offenders.items() for ln, cat, w, line in hits
        )
        self.assertEqual(offenders, {}, f"引擎混入了剧情名词：\n{detail}")

    def test_scan_actually_catches_something(self):
        """反向自检：扫描器不是永远返回空 —— 否则上面那条测试形同虚设。"""
        import tempfile

        # 取一个词表里确实在册的词（tests/ 不在 engine/ 下，写它不违红线）。
        sample = sorted(grep_forbidden.FORBIDDEN["世界观词汇"])[0]
        with tempfile.NamedTemporaryFile("w", suffix=".py", encoding="utf-8",
                                         delete=False) as f:
            f.write(f"x = '{sample}'\n")
            path = f.name
        try:
            hits = grep_forbidden.scan_file(path)
            self.assertTrue(hits)
            self.assertEqual(hits[0][2], sample)
        finally:
            os.remove(path)


if __name__ == "__main__":
    unittest.main()
