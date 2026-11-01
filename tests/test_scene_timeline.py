"""Contract tests for the frame-aware scene timeline (Task 4).

``scenes.load_all`` merges the plot catalogue with the per-mission scenes and
filters by the first frame a preset beat attests. The plot-only ``load`` must
stay exactly as it was, because the fidelity gate and the panel tests read it.

    python -m unittest discover -s tests -p "test_scene_timeline.py" -q
"""
from __future__ import annotations

import unittest

from apps import canon, scenes

VIEW_FIELDS = {
    "id", "title", "version", "first_frame", "loop", "before", "during",
    "after", "gap", "beats", "dialogue_refs", "source", "confidence", "kind",
}


class TestSceneTimeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = canon.CanonBundle.load()
        cls.rows = scenes.load_all(cls.bundle)
        cls.upto = scenes.load_all(cls.bundle, upto_frame=17000)

    def test_view_has_unified_fields(self):
        self.assertTrue(self.rows)
        for item in self.rows:
            self.assertTrue(VIEW_FIELDS <= set(item),
                            "%s missing %s" % (item.get("id"), VIEW_FIELDS - set(item)))
            self.assertIsInstance(item["during"], list, item["id"])

    def test_filter_keeps_only_reached_frames(self):
        self.assertTrue(self.upto)
        for item in self.upto:
            self.assertIsNotNone(item["first_frame"], item["id"])
            self.assertLessEqual(item["first_frame"], 17000, item["id"])
        # 边界帧算「已抵达」，更晚的剧情不出现。
        ids = {item["id"] for item in self.upto}
        self.assertIn("PLOT-014", ids)
        self.assertNotIn("PLOT-006", ids)

    def test_unknown_frame_absent_when_filtered(self):
        missing = [item for item in self.rows if item["first_frame"] is None]
        self.assertTrue(missing, "至少应有一条无首帧的记录")
        ids = {item["id"] for item in self.upto}
        for item in missing:
            self.assertNotIn(item["id"], ids)
            self.assertTrue(str(item.get("gap") or "").strip(), item["id"])

    def test_wiki_scenes_are_all_covered(self):
        wiki = [item for item in self.rows if item["kind"] == "wiki_scene"]
        self.assertEqual(len(wiki), 66)
        self.assertEqual(len(wiki), len(self.bundle.ids_of_kind("wiki_scene")))

    def test_dialogue_refs_match_scene_and_ascend(self):
        lines = {entry.id: entry for entry in self.bundle.of_kind("wiki_dialogue")}
        wiki = [item for item in self.rows if item["kind"] == "wiki_scene"]
        self.assertTrue(wiki)
        for item in wiki:
            refs = item["dialogue_refs"]
            self.assertTrue(refs, item["id"])
            orders = []
            for ref in refs:
                line = lines[ref]
                self.assertEqual(line.get("scene_id"), item["id"])
                orders.append(line.get("order"))
            self.assertEqual(orders, sorted(orders), item["id"])

    def test_plot_frames_come_from_beats(self):
        for entry in self.bundle.of_kind("plot"):
            frames = [beat.get("frame") for beat in self.bundle.beats_for(entry.id)
                      if isinstance(beat.get("frame"), int)]
            expected = min(frames) if frames else None
            got = [item["first_frame"] for item in self.rows
                   if item["kind"] == "plot" and item["id"] == entry.id]
            self.assertEqual(got, [expected], entry.id)

    def test_load_is_unchanged(self):
        rows = scenes.load(self.bundle)
        self.assertEqual(len(rows), 26)
        expected = [entry.id for entry in sorted(
            self.bundle.of_kind("plot"),
            key=lambda entry: (scenes._version_key(entry.get("version", "")), entry.id))]
        self.assertEqual([row["id"] for row in rows], expected)
        for row in rows:
            self.assertIn("beats", row)
            self.assertNotIn("first_frame", row)

    def test_narrate_exposes_frame_and_loop(self):
        item = scenes.narrate(self.rows[0])
        for key in ("first_frame", "loop", "dialogue_refs"):
            self.assertIn(key, item)
        self.assertEqual(item["acts"][0]["phase"], "before")
        self.assertEqual(item["acts"][-1]["phase"], "after")


if __name__ == "__main__":
    unittest.main()
