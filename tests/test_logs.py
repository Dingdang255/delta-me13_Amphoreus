"""Contract tests for the loop ledger (P6a).

    python -m unittest tests.test_logs
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from apps import canon, logs


class FakeBundle:
    def __init__(self, rows):
        self.rows = rows

    def of_kind(self, kind):
        if kind != "loop":
            return []
        return [SimpleNamespace(data=row) for row in self.rows]


class TestLoopLedger(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = canon.CanonBundle.load()
        cls.rows = logs.load(cls.bundle)

    def test_rows_loaded_and_sorted(self):
        self.assertEqual(len(self.rows), 35)
        loops = [int(r["loop"]) for r in self.rows]
        self.assertEqual(loops, sorted(loops))

    def test_every_row_is_labelled_and_sourced(self):
        for row in self.rows:
            self.assertIn(row["evidence"], logs.LABELS)
            self.assertTrue(row["source"])
            self.assertTrue(row["locator"])

    def test_current_corpus_is_all_official(self):
        counts = logs.labels(self.rows)
        self.assertEqual(counts["official"], 35)
        self.assertEqual(counts["reconstructed"], 0)
        self.assertEqual(counts["inferred"], 0)

    def test_coverage_shape(self):
        cov = logs.coverage(self.rows)
        self.assertEqual(cov["total"], 35)
        self.assertEqual(cov["official_ratio"], 1.0)
        self.assertEqual(cov["first"], 1)

    def test_lookup_by_loop(self):
        self.assertIsNotNone(logs.by_loop(self.rows, 1))
        self.assertIsNone(logs.by_loop(self.rows, 10 ** 12))

    def test_phases_sum_to_total(self):
        self.assertEqual(sum(logs.phases(self.rows).values()), len(self.rows))

    def test_explain_keeps_label(self):
        row = logs.explain(self.rows[0])
        self.assertEqual(row["evidence"], "official")
        self.assertTrue(row["verbatim"])

    def test_unknown_label_is_rejected(self):
        broken = FakeBundle([{"id": "LOOP-1", "loop": 1, "phase": "p",
                              "evidence": "guess", "source": "S-1"}])
        with self.assertRaises(logs.LogError):
            logs.load(broken)

    def test_missing_source_is_rejected(self):
        broken = FakeBundle([{"id": "LOOP-1", "loop": 1, "phase": "p",
                              "evidence": "official"}])
        with self.assertRaises(logs.LogError):
            logs.load(broken)


if __name__ == "__main__":
    unittest.main()
