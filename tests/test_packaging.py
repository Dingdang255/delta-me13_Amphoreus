"""依赖声明的一致性（D3）：`requirements.txt` 与 `pyproject.toml` 不许漂移。

`pyproject.toml` 的注释声称「两者的版本约束由单测守着」—— 本文件把这句话兑现：
过去没有任何测试读过这两个文件，声明的约束可以悄悄分叉。

numpy 的【上界】也是刻意的：轨迹指纹依赖 float32 + BLAS 的逐位行为，它随 numpy
版本变 —— 所以这里连「有没有上界」也一并守住。
"""
from __future__ import annotations

import io
import os
import re
import unittest

from _support import ROOT

_NAME = re.compile(r"([A-Za-z0-9_.\-]+)\s*(.*)")


def _split(spec: str):
    """`numpy>=1.24, <3` → ("numpy", ">=1.24,<3")（约束里的空格一律去掉）。"""
    m = _NAME.match(spec.strip())
    return m.group(1).lower(), m.group(2).replace(" ", "")


def _requirements() -> dict:
    """requirements.txt → {包名: 版本约束}（忽略注释与空行）。"""
    out = {}
    with io.open(os.path.join(ROOT, "requirements.txt"), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                name, spec = _split(line)
                out[name] = spec
    return out


def _pyproject_dependencies():
    with io.open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8") as f:
        text = f.read()
    block = re.search(r"^dependencies\s*=\s*\[(.*?)\]", text, re.S | re.M)
    if block is None:
        return None
    return dict(_split(d) for d in re.findall(r'"([^"]+)"', block.group(1)))


class PackagingConsistency(unittest.TestCase):
    def test_both_files_declare_the_same_packages(self):
        deps = _pyproject_dependencies()
        self.assertIsNotNone(deps, "pyproject.toml 里没有 dependencies")
        self.assertEqual(set(_requirements()), set(deps))

    def test_numpy_constraint_matches(self):
        deps = _pyproject_dependencies()
        req = _requirements()
        self.assertIn("numpy", req)
        self.assertIn("numpy", deps)
        self.assertEqual(req["numpy"], deps["numpy"])

    def test_numpy_has_an_upper_bound(self):
        """上界不是洁癖：换 numpy 大版本可能改变 float32/BLAS 的逐位结果 ⇒ 指纹失配。"""
        self.assertIn("<", _requirements()["numpy"])


class ReleaseDiscipline(unittest.TestCase):
    """发版纪律：版本号不许只改一处（ADR-0001 §3.4）。

    过去 `pyproject.toml` 的 `version`、`CHANGELOG.md` 的小节、内核的 `API_VERSION`
    三处各写各的，靠人记 —— 改漏一处不会有任何报错。这里把两条最便宜的等式钉住：
    ① 包版本必须在 CHANGELOG 里有对应的 `## vX.Y.Z` 小节；
    ② 内核接口版本必须由 `capabilities()` 一并报出（应用据此判断兼容）。
    """

    def test_pyproject_version_has_a_changelog_section(self):
        from _support import ROOT as root

        with io.open(os.path.join(root, "pyproject.toml"), encoding="utf-8") as f:
            m = re.search(r'^version\s*=\s*"([^"]+)"', f.read(), re.M)
        self.assertIsNotNone(m, "pyproject.toml 里没有 version")
        version = m.group(1)

        with io.open(os.path.join(root, "CHANGELOG.md"), encoding="utf-8") as f:
            headings = re.findall(r"^## v(\d+\.\d+\.\d+)", f.read(), re.M)
        self.assertIn(version, headings,
                      f"pyproject 的 version = {version} 在 CHANGELOG 里没有对应小节"
                      f"（已有：{headings}）")

    def test_api_version_is_reported_by_capabilities(self):
        from kernel.api import API_VERSION, load

        self.assertRegex(API_VERSION, r"^\d+$")
        # 只建会话、不 step：装载是纯读，不跑演算。
        self.assertEqual(load().capabilities()["api_version"], API_VERSION)


if __name__ == "__main__":
    unittest.main()
