"""Contract tests for the compiled lore bundle (P2).

These tests do not need the raw client dumps: they only read ``lore/canon``.
The whole module is skipped when the bundle has not been compiled yet, so a
fresh clone without ``lore/canon`` still passes the rest of the suite.

    python -m unittest tests.test_canon_contract
"""
from __future__ import annotations

import json
import os
import unittest

from apps import canon

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANON_DIR = os.path.join(ROOT, "lore", "canon")
SCHEMA_DIR = os.path.join(ROOT, "lore", "schema")

EXPECTED_SCHEMAS = {
    "fact.schema.json",
    "scene.schema.json",
    "dialogue.schema.json",
    "loop.schema.json",
    "terminal.schema.json",
    "character.schema.json",
    "worldgen.schema.json",
    "trend.schema.json",
    "micro_event.schema.json",
}


def _read_jsonl(path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


@unittest.skipUnless(os.path.exists(os.path.join(CANON_DIR, "manifest.json")),
                     "lore/canon not compiled")
class TestCanonBundle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = canon.CanonBundle.load()

    def test_manifest_matches_payload(self):
        # load(verify=True) already hashed every declared file
        self.assertEqual(self.bundle.manifest["schema_version"], "1")
        self.assertGreater(self.bundle.manifest["entry_count"], 0)

    def test_ids_are_unique_per_kind(self):
        for kind in canon.JSONL_KINDS:
            path = os.path.join(CANON_DIR, f"{kind}.jsonl")
            if not os.path.exists(path):
                continue
            seen = set()
            for row in _read_jsonl(path):
                self.assertNotIn(row["id"], seen, f"duplicate {row['id']} in {kind}")
                seen.add(row["id"])

    def test_index_covers_every_record(self):
        missing = [entry.id for entry in self.bundle.entries()
                   if entry.id not in self.bundle._index]
        self.assertEqual(missing, [])

    def test_traceability_covers_every_record(self):
        missing = [entry.id for entry in self.bundle.entries()
                   if (entry.kind, entry.id) not in self.bundle._trace]
        self.assertEqual(missing, [])

    def test_dialogue_references_resolve(self):
        self.assertEqual(self.bundle.unresolved_refs(), [])

    def test_every_character_has_three_rules(self):
        cards = list(self.bundle.of_kind("character"))
        self.assertGreater(len(cards), 0)
        for card in cards:
            rules = card.get("decision_rules") or []
            self.assertGreaterEqual(
                len(rules), 3, f"{card.id} has only {len(rules)} decision_rules"
            )
            for rule in rules:
                self.assertTrue(rule.get("source"), f"{card.id}/{rule.get('id')} no source")

    def test_source_is_recorded_for_facts(self):
        for kind in ("dialogue", "terminal", "loop", "anchor"):
            for entry in self.bundle.of_kind(kind):
                self.assertTrue(
                    entry.get("source"), f"{entry.id} in {kind} has no source"
                )

    def test_schemas_exist(self):
        for name in EXPECTED_SCHEMAS:
            self.assertTrue(
                os.path.exists(os.path.join(SCHEMA_DIR, name)), f"missing schema {name}"
            )


if __name__ == "__main__":
    unittest.main()
