"""术语对照表（F1）：`docs/术语对照表.md` 必须是配置的镜像。

手写的对照表迟早与配置漂移。这里直接拿生成器的输出与文档比对 ——
改了 lexicon / phonology / loci / conclusions / params 而忘了刷新文档，单测就会红。
"""
from __future__ import annotations

import io
import json
import os
import sys
import unittest

from _support import ROOT

sys.path.insert(0, os.path.join(ROOT, "tools"))
import lexicon_table  # noqa: E402


def _json(*parts):
    with io.open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return json.load(f)


class LexiconTable(unittest.TestCase):
    def test_doc_matches_config(self):
        self.assertTrue(os.path.exists(lexicon_table.DOC),
                        "还没有 docs/术语对照表.md；先跑 tools/lexicon_table.py --write")
        with io.open(lexicon_table.DOC, encoding="utf-8") as f:
            cur = f.read().strip()
        self.assertEqual(cur, lexicon_table.build().strip(),
                         "术语对照表与配置不一致：跑 "
                         "python tools/lexicon_table.py --write 刷新")

    def test_covers_every_locus_and_month(self):
        text = lexicon_table.build()
        for key in ("L00", "L11", "MONTH_GATE", "MONTH_CHANCE"):
            self.assertIn(key, text)


class CapabilityLabels(unittest.TestCase):
    """扰动能力与渲染词表不许漂移。

    两个方向要分开看（见 engine/loader.py `_check_capability_names` 的说明）：
      · 注册表里【有的】能力，词表里必须【也有】——否则经编年史 / 看板渲染时
        会漏出裸的英文名（`viz.py` 的回退就是 `cap or "介入"`）；
      · 词表里【多出】的名字（如只有词条、没有投递实现的 `bind_locus`）是允许的，
        因为 `params.capability_names` 把能力当【个体标签】用，不要求有实现。
    """

    def test_every_registered_capability_has_a_label(self):
        from engine.disturbance import CAPABILITIES
        labels = _json("config", "lexicon.json")["capabilities"]
        missing = sorted(set(CAPABILITIES) - set(labels))
        self.assertEqual(missing, [], f"这些已注册能力缺渲染词：{missing}")

    def test_capability_names_resolve_to_registered_or_declared(self):
        from engine.disturbance import CAPABILITIES
        labels = set(_json("config", "lexicon.json")["capabilities"])
        known = set(CAPABILITIES) | labels
        for i, nm in enumerate(_json("config", "params.json")["capability_names"]):
            if nm is not None:
                self.assertIn(nm, known, f"params.capability_names[{i}] = {nm!r}")


if __name__ == "__main__":
    unittest.main()
