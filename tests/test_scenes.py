"""Contract tests for the scene catalogue (P6b).

    python -m unittest tests.test_scenes
"""
from __future__ import annotations

import unittest

from apps import canon, scenes

CHAPTERS = ("3.0", "3.1", "3.2", "3.3", "3.4", "3.5", "3.6", "3.7")


class TestSceneCatalogue(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = canon.CanonBundle.load()
        cls.rows = scenes.load(cls.bundle)

    def test_all_chapters_covered(self):
        cov = scenes.coverage(self.rows)
        for version in CHAPTERS:
            self.assertGreaterEqual(cov.get(version, 0), 1, version)

    def test_every_scene_has_provenance(self):
        for scene in self.rows:
            self.assertTrue(scene.get("sources"), scene.get("id"))
            self.assertTrue(scene.get("chapter"), scene.get("id"))
            self.assertTrue(scene.get("scene"), scene.get("id"))

    def test_beats_are_attached_in_order(self):
        """每个场景都带 `beats`（可为空），id 不重复、frame 升序；且至少一条真被演到。"""
        for scene in self.rows:
            self.assertIsInstance(scene.get("beats"), list, scene.get("id"))
            ids = [b["id"] for b in scene["beats"]]
            self.assertEqual(len(ids), len(set(ids)), scene.get("id"))
            frames = [b.get("frame") or 0 for b in scene["beats"]]
            self.assertEqual(frames, sorted(frames), scene.get("id"))
        played = [s for s in self.rows if s["beats"]]
        self.assertTrue(played, "至少应有一条剧情被预设演到")
        self.assertTrue(scenes.narrate(played[0])["beats"])

    def test_order_is_monotonic(self):
        keys = [scenes._version_key(s["version"]) for s in self.rows]
        self.assertEqual(keys, sorted(keys))

    def test_dag_is_a_linear_chain(self):
        graph = scenes.dag(self.rows)
        self.assertEqual(len(graph["nodes"]), len(self.rows))
        self.assertEqual(len(graph["edges"]), max(0, len(self.rows) - 1))

    def test_references_resolve(self):
        known = {
            "dialogue": self.bundle.ids_of_kind("dialogue"),
            "scene": self.bundle.ids_of_kind("scene"),
            "micro_event": self.bundle.ids_of_kind("micro_event"),
            "trend": self.bundle.ids_of_kind("trend"),
            "worldgen": self.bundle.ids_of_kind("worldgen"),
        }
        problems = []
        for scene in self.rows:
            problems.extend(scenes.unresolved(scene, known))
        self.assertEqual(problems, [])

    def test_narrate_flattens_acts(self):
        item = scenes.narrate(self.rows[0])
        self.assertTrue(item["acts"])
        self.assertEqual(item["acts"][0]["phase"], "before")
        self.assertEqual(item["acts"][-1]["phase"], "after")
        for act in item["acts"]:
            self.assertTrue(act["text"])

    def test_narrate_keeps_gaps_visible(self):
        item = scenes.narrate(self.rows[0])
        self.assertIn("gap", item)
        self.assertIn("verbatim_available", item)


if __name__ == "__main__":
    unittest.main()
