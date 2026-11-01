"""权杖档案（`lore/D6_terminal/scepter_dossier.jsonl`）：解析完整度与报告接入。

只读：不跑演算，只读档案与源页、调 `apps/scepter.py` 的只读统计。
"""
from __future__ import annotations

import json
import os
import types
import unittest

from _support import ROOT

from apps import scepter

DOSSIER = os.path.join(ROOT, "lore", "D6_terminal", "scepter_dossier.jsonl")
SOURCE = os.path.join(ROOT, "lore", "story", "wiki_structured", "terminals_wiki.jsonl")
PAGE = "Δ-me13.exe"


def _jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _page_rows():
    return [row for row in _jsonl(SOURCE) if row.get("page") == PAGE]


class ScepterDossierTest(unittest.TestCase):
    """467 行原文 -> section 路径 + 正文条目。"""

    @classmethod
    def setUpClass(cls):
        cls.rows = _jsonl(DOSSIER)
        cls.page = _page_rows()

    def test_one_entry_per_body_row(self):
        """标题行不进正文，转为 section 路径：正文条目 = 源页行数 − 标题行数。"""
        headings = sum(1 for row in self.page
                       if str(row.get("text") or "").strip().startswith("=="))
        self.assertEqual(len(self.page), 467)
        self.assertEqual(len(self.rows) + headings, len(self.page))
        self.assertGreaterEqual(len(self.rows), 350)

    def test_sections_are_paths(self):
        top = {row["section"].split(" / ")[0] for row in self.rows if row["section"]}
        self.assertGreaterEqual(len(top), 6)
        self.assertIn("实验基础", top)
        self.assertIn("实验进程：结论", top)
        for row in self.rows:
            self.assertLessEqual(len(row["section"].split(" / ")), 3)
            self.assertFalse(row["section"].endswith("="))

    def test_progress_rows_are_flagged(self):
        progress = [row for row in self.rows if row["kind"] == "progress"]
        self.assertEqual(len(progress), 8)
        for row in progress:
            self.assertTrue(row["text"].startswith("进度："))
        self.assertEqual(progress[0]["text"], "进度：0%")
        self.assertEqual(progress[-1]["text"], "进度：100%")

    def test_dialog_log_is_captured(self):
        dialog = [row for row in self.rows if "对话日志" in row["section"]]
        self.assertEqual(len(dialog), 19)
        self.assertTrue(all(row["text"] for row in dialog))

    def test_entries_are_well_formed(self):
        ids = [row["id"] for row in self.rows]
        self.assertEqual(ids, ["DOS-%03d" % (i + 1) for i in range(len(self.rows))])
        self.assertEqual(len(set(ids)), len(ids))
        for row in self.rows:
            self.assertTrue(str(row["text"]).strip())
            self.assertEqual(row["grade"], "B")
            self.assertTrue(str(row["source_url"]).startswith("https://"))
            self.assertTrue(row["text_kind"])
            self.assertTrue(row["loop"] is None or isinstance(row["loop"], int))

    def test_summary_exposes_dossier_stats(self):
        stats = scepter.dossier_stats()
        self.assertEqual(stats["rows"], len(self.rows))
        self.assertIsNone(stats["unavailable_reason"])
        traj = types.SimpleNamespace(reached_frame=0, records=[], final=None)
        data = scepter.summary(traj, spec={})
        self.assertEqual(data["dossier_entries"], len(self.rows))
        self.assertGreaterEqual(data["dossier_sections"], 6)
        self.assertEqual(data["dialog_log_count"], 19)
        self.assertIn(0, data["progress_milestones"])
        self.assertIn(100, data["progress_milestones"])
        lines = scepter.render(data)
        self.assertTrue(any("档案" in line for line in lines), lines)

    def test_missing_dossier_is_null_not_fabricated(self):
        stats = scepter.dossier_stats(path=os.path.join(ROOT, "no-such-dossier.jsonl"))
        self.assertIsNone(stats["entries"])
        self.assertTrue(stats["unavailable_reason"])


if __name__ == "__main__":
    unittest.main()
