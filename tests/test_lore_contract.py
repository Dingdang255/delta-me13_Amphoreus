"""Contract skeleton for the raw lore corpus (P0).

These checks are intentionally shallow: they only prove the corpus is present,
parseable and shaped as eight dimensions. Field-level rules live in
`tools/lore_lint.py`, and the compiled bundle is covered by
`tests/test_canon_contract.py`.

    python -m unittest tests.test_lore_contract
"""
from __future__ import annotations

import json
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LORE = os.path.join(ROOT, "lore")

DIMENSIONS = (
    "D1_seed", "D2_trends", "D3_plot", "D4_dialogue",
    "D5_loops", "D6_terminal", "D7_community", "D8_characters",
)

TOP_FILES = (
    "00_manifest.md",
    "01_sources.csv",
    "02_glossary.json",
    "03_entity_index.jsonl",
    "04_event_index.jsonl",
    "05_term_index.jsonl",
    "10_conflicts.jsonl",
    "11_unknowns.jsonl",
    "12_fidelity_checklist.md",
    "13_changelog.md",
)


def _jsonl(path):
    with open(path, "r", encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            line = line.strip()
            if line:
                yield ln, json.loads(line)


def _corpus_files():
    """JSONL owned by the corpus; raw client dumps are out of scope."""
    for base, dirs, names in os.walk(LORE):
        dirs[:] = [d for d in dirs if d not in ("canon", "_probe", "export", "story")]
        for name in names:
            if name.endswith(".jsonl"):
                yield os.path.join(base, name)


@unittest.skipUnless(os.path.isdir(LORE), "lore/ not present")
class TestLoreCorpus(unittest.TestCase):
    def test_top_level_files_exist(self):
        for name in TOP_FILES:
            self.assertTrue(os.path.exists(os.path.join(LORE, name)), f"missing {name}")

    def test_eight_dimensions_present(self):
        for dim in DIMENSIONS:
            folder = os.path.join(LORE, dim)
            self.assertTrue(os.path.isdir(folder), f"missing {dim}/")
            self.assertTrue(os.listdir(folder), f"{dim}/ is empty")

    def test_manifest_declares_all_dimensions(self):
        text = open(os.path.join(LORE, "00_manifest.md"), encoding="utf-8").read()
        for dim in DIMENSIONS:
            self.assertIn(dim, text, f"manifest does not mention {dim}")

    def test_every_jsonl_parses(self):
        for path in _corpus_files():
            rel = os.path.relpath(path, LORE)
            for ln, row in _jsonl(path):
                self.assertIsInstance(row, dict, f"{rel}:{ln} is not an object")

    def test_every_record_has_an_id(self):
        id_fields = ("id", "entity_id", "event_id", "term_id")
        for path in _corpus_files():
            rel = os.path.relpath(path, LORE)
            for ln, row in _jsonl(path):
                if any(field in row for field in id_fields):
                    continue
                # relations.jsonl is an edge list; lines still carry endpoints
                self.assertIn("from", row, f"{rel}:{ln} has neither id nor from")

    def test_conflicts_and_unknowns_are_tables(self):
        conflicts = list(_jsonl(os.path.join(LORE, "10_conflicts.jsonl")))
        unknowns = list(_jsonl(os.path.join(LORE, "11_unknowns.jsonl")))
        self.assertGreater(len(conflicts), 0)
        self.assertGreater(len(unknowns), 0)
        for _ln, row in conflicts:
            self.assertTrue(row.get("resolution"))
        for _ln, row in unknowns:
            self.assertTrue(row.get("question"))
            self.assertTrue(row.get("impact"))


if __name__ == "__main__":
    unittest.main()
