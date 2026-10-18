"""红线 1：程序里不许出现专有名词。

把 tools/grep_forbidden.py 的扫描口径搬进单测 —— 于是「代码混进了剧情名词」
不再只在手动跑工具时才发现。扫的是 grep_forbidden.SCAN_DIRS（kernel/ 与 apps/）：
加了新的模块也会被自动纳入。
"""
from __future__ import annotations

import os
import sys
import unittest

from _support import ROOT

sys.path.insert(0, os.path.join(ROOT, "tools"))
import grep_forbidden  # noqa: E402


class ForbiddenWords(unittest.TestCase):
    def test_code_has_no_proper_nouns(self):
        offenders = {}
        for pkg in grep_forbidden.SCAN_DIRS:
            d = os.path.join(ROOT, pkg)
            for name in sorted(os.listdir(d)):
                if not name.endswith(".py"):
                    continue
                hits = grep_forbidden.scan_file(os.path.join(d, name))
                if hits:
                    offenders[f"{pkg}/{name}"] = hits
        detail = "\n".join(
            f"{n} L{ln} [{cat}] 「{w}」 → {line[:60]}"
            for n, hits in offenders.items() for ln, cat, w, line in hits
        )
        self.assertEqual(offenders, {}, f"程序里混入了剧情名词：\n{detail}")

    def test_scan_actually_catches_something(self):
        """反向自检：扫描器不是永远返回空 —— 否则上面那条测试形同虚设。"""
        import tempfile

        # 取一个词表里确实在册的词（tests/ 不在扫描集合里，写它不违红线）。
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
