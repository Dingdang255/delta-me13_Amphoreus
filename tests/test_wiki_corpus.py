"""Contract tests for the S-024 wiki narrative corpus.

Covers the artefacts produced by ``tools/lore_build/build_wiki_scenes.py``:

    lore/D4_dialogue/scenes_wiki.jsonl
    lore/D4_dialogue/dialogues_wiki.jsonl
    lore/D3_plot/options_wiki.jsonl
    lore/D6_terminal/terminals_from_wiki.jsonl

The raw wiki markdown and ``lore/story/wiki_structured/`` are .gitignore'd, so the
baseline cross-check is skipped when they are absent; the corpus itself is always tested.

    python -m unittest discover -s tests -p "test_wiki_corpus.py" -q
"""
from __future__ import annotations

import json
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LORE = os.path.join(ROOT, "lore")
SCENES = os.path.join(LORE, "D4_dialogue", "scenes_wiki.jsonl")
DIALOGUES = os.path.join(LORE, "D4_dialogue", "dialogues_wiki.jsonl")
OPTIONS = os.path.join(LORE, "D3_plot", "options_wiki.jsonl")
TERMINALS = os.path.join(LORE, "D6_terminal", "terminals_from_wiki.jsonl")
BATTLE = os.path.join(LORE, "D3_plot", "battle_lines.jsonl")
STRUCTURED = os.path.join(LORE, "story", "wiki_structured")

VERSIONS = ("3.0", "3.1", "3.2", "3.3", "3.4", "3.5", "3.6", "3.7")
CONFIDENCE = {"A", "B", "C", "D", "E", "UNKNOWN"}

MIN_SCENES = 66
MIN_DIALOGUES = 12000
MIN_OPTIONS = 2167
MIN_TERMINALS = 280

SCENE_ID = re.compile(r"^SCN-W3\.\d-\d{2}$")
DIALOGUE_ID = re.compile(r"^DLG-W3\.\d-\d{4}$")
TERMINAL_ID = re.compile(r"^TRM-W-\d{4}$")
OPTION_ID = re.compile(r"^OPT-3\.\d-\d{2}-\d{3}$")


def read_jsonl(path):
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class TestWikiCorpus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for path in (SCENES, DIALOGUES, OPTIONS, TERMINALS):
            if not os.path.exists(path):
                raise unittest.SkipTest("wiki corpus not built: %s" % path)
        cls.scenes = read_jsonl(SCENES)
        cls.dialogues = read_jsonl(DIALOGUES)
        cls.options = read_jsonl(OPTIONS)
        cls.terminals = read_jsonl(TERMINALS)

    # -- volume thresholds -------------------------------------------------
    def test_scene_count(self):
        self.assertGreaterEqual(len(self.scenes), MIN_SCENES)

    def test_dialogue_count(self):
        self.assertGreaterEqual(len(self.dialogues), MIN_DIALOGUES)

    def test_option_count(self):
        self.assertGreaterEqual(len(self.options), MIN_OPTIONS)

    def test_terminal_count(self):
        self.assertGreaterEqual(len(self.terminals), MIN_TERMINALS)

    # -- coverage ----------------------------------------------------------
    def test_mission_coverage(self):
        pairs = {(s["version"], s["mission"]) for s in self.scenes}
        self.assertEqual(len(pairs), 66, "every one of the 66 missions needs a scene")
        self.assertEqual(len(self.scenes), 66, "one scene per mission")

        baseline = os.path.join(STRUCTURED, "missions.jsonl")
        if os.path.exists(baseline):
            expected = {(m["version"], m["name"]) for m in read_jsonl(baseline)}
            self.assertEqual(pairs, expected)

    def test_each_volume_has_readable_scenes(self):
        for version in VERSIONS:
            count = sum(1 for s in self.scenes if s["version"] == version)
            self.assertGreaterEqual(count, 3, "volume %s has only %d scenes" % (version, count))

    def test_scene_summary_is_readable(self):
        for scene in self.scenes:
            for field in ("before", "during", "after"):
                self.assertTrue(str(scene.get(field, "")).strip(),
                                "%s has empty %s" % (scene["id"], field))
            self.assertTrue(scene.get("gap"), "%s records no gap" % scene["id"])

    # -- identity ----------------------------------------------------------
    def test_ids_are_unique(self):
        for rows, pattern, label in (
            (self.scenes, SCENE_ID, "scene"),
            (self.dialogues, DIALOGUE_ID, "dialogue"),
            (self.options, OPTION_ID, "option"),
            (self.terminals, TERMINAL_ID, "terminal"),
        ):
            ids = [r["id"] for r in rows]
            self.assertEqual(len(ids), len(set(ids)), "duplicate id in %s" % label)
            bad = [i for i in ids if not pattern.match(i)]
            self.assertEqual(bad[:5], [], "%s ids do not match %s" % (label, pattern.pattern))

    # -- provenance --------------------------------------------------------
    def test_every_record_has_provenance(self):
        groups = (
            ("scene", self.scenes),
            ("dialogue", self.dialogues),
            ("option", self.options),
            ("terminal", self.terminals),
        )
        for label, rows in groups:
            for row in rows:
                self.assertTrue(str(row.get("source", "")).strip(),
                                "%s/%s has no source" % (label, row["id"]))
                self.assertTrue(str(row.get("locator", "")).strip(),
                                "%s/%s has no locator" % (label, row["id"]))
                self.assertIn(row.get("confidence"), CONFIDENCE,
                              "%s/%s has bad confidence" % (label, row["id"]))
                self.assertEqual(row.get("confidence"), "B",
                                 "%s/%s should stay at wiki grade B" % (label, row["id"]))

    def test_verbatim_claim_is_false(self):
        for label, rows in (("scene", self.scenes), ("dialogue", self.dialogues),
                            ("option", self.options), ("terminal", self.terminals)):
            for row in rows:
                self.assertIs(row.get("verbatim_claim"), False,
                              "%s/%s claims verbatim" % (label, row["id"]))

    def test_wiki_markup_is_stripped(self):
        for row in self.dialogues:
            text = row["verbatim"]
            for marker in ("**", "{{", "}}", "<color", "'''"):
                self.assertNotIn(marker, text, "%s kept wiki markup" % row["id"])

    def test_line_kinds(self):
        allowed = {"dialogue", "narration", "option"}
        for row in self.dialogues:
            self.assertIn(row["kind"], allowed, "%s has kind %r" % (row["id"], row["kind"]))
            if row["kind"] == "narration":
                self.assertIsNone(row["speaker"], "%s nudges a speaker onto narration" % row["id"])
            if row["kind"] == "dialogue":
                self.assertTrue(row["speaker"], "%s has no speaker" % row["id"])

    # -- references --------------------------------------------------------
    def test_dialogue_scene_refs_resolve(self):
        scene_ids = {s["id"] for s in self.scenes}
        for row in self.dialogues:
            self.assertIn(row["scene_id"], scene_ids,
                          "%s points at unknown scene %s" % (row["id"], row["scene_id"]))

    def test_dialogue_next_refs_resolve(self):
        ids = {row["id"] for row in self.dialogues}
        for row in self.dialogues:
            for nxt in row.get("next") or []:
                self.assertIn(nxt, ids, "%s next -> unknown %s" % (row["id"], nxt))

    def test_option_refs_resolve(self):
        dialogue_ids = {row["id"] for row in self.dialogues}
        for row in self.options:
            self.assertIn(row["dlg_id"], dialogue_ids,
                          "%s has no wiki line" % row["id"])
            for nxt in row.get("next") or []:
                self.assertIn(nxt, dialogue_ids, "%s next -> unknown %s" % (row["id"], nxt))

    def test_option_dlg_is_the_option_line(self):
        by_id = {row["id"]: row for row in self.dialogues}
        for row in self.options:
            self.assertEqual(by_id[row["dlg_id"]]["kind"], "option",
                             "%s points at a non-option line" % row["id"])

    # -- baseline fidelity -------------------------------------------------
    def test_option_baseline_preserved(self):
        baseline_path = os.path.join(STRUCTURED, "options.jsonl")
        if not os.path.exists(baseline_path):
            self.skipTest("wiki_structured baseline not present")
        baseline = read_jsonl(baseline_path)
        got = {row["id"]: row for row in self.options}
        self.assertEqual(set(got), {row["id"] for row in baseline})
        for old in baseline:
            new = got[old["id"]]
            self.assertEqual(new["option"], old["option"])
            self.assertEqual(new["branch_lines"], old.get("branch_lines") or [])
            self.assertEqual(new["merge_at"], old.get("merge_at") or "")
            self.assertEqual(new["parent"], old.get("parent"))


class TestBattleLinesRegistered(unittest.TestCase):
    def test_battle_line_kind_is_registered(self):
        import sys
        if ROOT not in sys.path:
            sys.path.insert(0, ROOT)
        import tools.lore_lint as lore_lint

        self.assertIn("battle_line", lore_lint.KINDS)
        rel, id_field, _required, _source, _extra = lore_lint.KINDS["battle_line"]
        self.assertEqual(id_field, "id")
        path = os.path.join(LORE, rel.replace("/", os.sep))
        self.assertTrue(os.path.exists(path), "missing %s" % rel)
        self.assertGreaterEqual(len(read_jsonl(path)), 500)


if __name__ == "__main__":
    unittest.main()
