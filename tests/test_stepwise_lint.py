"""红线 2 / 判据 4（静态部分）：逐步推进 lint。

把 `tools/stepwise_lint.py` 的扫描口径搬进单测 —— 于是「引擎混进了非逐步的写法」
（解析求解 / 读终局捷径）不再只在手动跑工具时才发现。含反向自检：扫描器不是永远返回空。
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest

from _support import ROOT

sys.path.insert(0, os.path.join(ROOT, "tools"))
import stepwise_lint  # noqa: E402


def _write(tmpdir, name, text):
    path = os.path.join(tmpdir, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


class StepwiseLint(unittest.TestCase):
    def test_engine_is_clean(self):
        engine = os.path.join(ROOT, "engine")
        offenders = {}
        for name in sorted(os.listdir(engine)):
            if name.endswith(".py"):
                hits = stepwise_lint.scan_file(os.path.join(engine, name))
                if hits:
                    offenders[name] = hits
        self.assertEqual(offenders, {}, f"引擎出现了非逐步写法：{offenders}")

    def test_catches_direct_final_read(self):
        """反向自检：非 POST_HOC 文件里读 `traj.final` 必须命中。"""
        d = tempfile.mkdtemp()
        try:
            hits = stepwise_lint.scan_file(_write(d, "core.py", "x = traj.final\n"))
            self.assertTrue(hits)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_post_hoc_exempt(self):
        """`POST_HOC`（只读 / 事后核对层）读 `traj.final` 属合法 —— 不该命中。"""
        d = tempfile.mkdtemp()
        try:
            p = _write(d, "render.py", "x = traj.final\n")
            self.assertEqual(stepwise_lint.scan_file(p), [])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_assignment_is_not_a_read(self):
        """`traj.final = st` 是赋值，不是「读终局捷径」。"""
        d = tempfile.mkdtemp()
        try:
            p = _write(d, "core.py", "traj.final = st\n")
            self.assertEqual(stepwise_lint.scan_file(p), [])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_comment_ignored(self):
        """整行注释里的禁用写法不该命中。"""
        d = tempfile.mkdtemp()
        try:
            p = _write(d, "core.py", "# matrix_power(a, 2) 只是注释\nx = 1\n")
            self.assertEqual(stepwise_lint.scan_file(p), [])
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
