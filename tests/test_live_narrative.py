"""Contract tests for the live narrative stream (Task 5).

Scenes must surface while the simulation runs, in step with the rounds that
have arrived -- not in one dump at the end. The live set and the final set must
be the same `scenes.load_all(upto_frame=...)` view, so the panel is identical
before and after the收官 reload.

    python -m unittest discover -s tests -p "test_live_narrative.py" -q
"""
from __future__ import annotations

import unittest

from apps import canon, scenes, viz
from apps.live import LiveState


def _fake(scene_id, frame):
    return {"id": scene_id, "title": scene_id, "version": "3.0",
            "first_frame": frame, "loop": None, "before": None,
            "during": ["一步"], "after": None, "gap": "", "beats": []}


class LiveNarrativeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = canon.CanonBundle.load()
        cls.rows = scenes.load_all(cls.bundle)
        cls.final_frame = max(row["first_frame"] for row in cls.rows
                              if row.get("first_frame") is not None)
        cls.intervals = scenes._version_frames(cls.bundle)

    def _push(self, state, frame):
        for item in scenes.load_all(self.bundle, upto_frame=frame):
            state.add_scene(item["first_frame"], item.get("loop"), item)

    def test_three_frames_and_two_promotions_append_without_duplicates(self):
        state = LiveState()
        for i, frame in enumerate((100, 200, 300)):
            state.add_scene(frame, None, _fake("FAKE-%d" % i, frame))
        self.assertEqual(state.snapshot(0, 0, 0)["narrative"]["count"], 3)

        before = state.snapshot(0, 0, 0)["narrative"]["count"]
        for frame in (12000, 23000):        # 两次换代推送
            self._push(state, frame)
        snap = state.snapshot(0, 0, 0)["narrative"]
        self.assertGreater(snap["count"], before)
        ids = [item["id"] for item in snap["items"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(snap["count"], len(snap["items"]))

    def test_live_set_equals_final_set(self):
        state = LiveState()
        # 换代 / 换档帧 + 终局补推 —— 与 run.py 的推送点同一口径。
        triggers = [12000, 16000, 17000, 18400, 21000, 23000, 30000, 36000,
                    40000, 42000, 33594260, 33594320, 33594377, 33594393,
                    33594407, 33594430, 33594447, 33594470, 33594497,
                    33594545, self.final_frame]
        for frame in sorted(set(triggers)):
            self._push(state, min(frame, self.final_frame))
        live = {item["id"] for item in state.snapshot(0, 0, 0)["narrative"]["items"]}
        final = {row["id"] for row in
                 scenes.load_all(self.bundle, upto_frame=self.final_frame)}
        self.assertEqual(live, final)

    def test_block_html_tolerates_empty_list(self):
        self.assertEqual(viz.narrative_block_html([]), "")
        html = viz.narrative_block_html([_fake("X", 1)])
        self.assertIn("场景面板", html)
        self.assertIn("X", html)

    def test_projection_sources_and_per_version_coverage(self):
        wiki = [row for row in self.rows if row["kind"] == "wiki_scene"]
        self.assertTrue(wiki)
        for version, (lo, hi) in self.intervals.items():
            group = [row for row in wiki if row["version"] == version]
            self.assertGreaterEqual(len(group), 3, version)
            for row in group:
                self.assertEqual(row["first_frame_source"], "projected", row["id"])
                self.assertEqual(row["confidence"], "C", row["id"])
                self.assertTrue(lo <= row["first_frame"] <= hi, row["id"])
                self.assertIn("投影", row["gap"], row["id"])
            reached = [row for row in
                       scenes.load_all(self.bundle, upto_frame=hi)
                       if row["version"] == version]
            self.assertGreaterEqual(len(reached), 3, version)

    def test_beat_frames_keep_their_source(self):
        for row in self.rows:
            if row["kind"] == "plot" and row["first_frame"] is not None:
                self.assertEqual(row["first_frame_source"], "beat", row["id"])


if __name__ == "__main__":
    unittest.main()
