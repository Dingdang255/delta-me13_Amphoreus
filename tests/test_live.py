"""Contract tests for the live board state (`apps/live.py`).

The live state is written by the simulation thread and read by the HTTP
thread; everything goes through one lock. These tests pin the snapshot shape
the page consumes, including the incremental narrative stream.

    python -m unittest discover -s tests -p "test_live.py" -q
"""
from __future__ import annotations

import unittest

from apps.live import LiveState


def _scene(scene_id, frame):
    return {"id": scene_id, "title": scene_id, "version": "3.0",
            "first_frame": frame, "loop": None, "before": "前",
            "during": ["中"], "after": "后", "gap": "", "beats": []}


class LiveStateTest(unittest.TestCase):
    def test_snapshot_shape_includes_narrative(self):
        state = LiveState()
        state.add_row(10, "一行", None, 1)
        state.add_scene(10, None, _scene("S-1", 10))
        snap = state.snapshot(0, 0, 0)
        for key in ("frame", "done", "rows", "samples", "seatnames", "machines",
                    "marks", "promos", "mythfrom", "stages", "stageshtml",
                    "narrative", "final"):
            self.assertIn(key, snap)
        self.assertEqual(snap["rows"], [[10, "一行", None, 1]])
        self.assertEqual(snap["frame"], 10)
        self.assertEqual(snap["narrative"]["count"], 1)
        self.assertIn("场景面板", snap["narrative"]["html"])

    def test_same_scene_is_only_pushed_once(self):
        state = LiveState()
        state.add_scene(10, None, _scene("S-1", 10))
        state.add_scene(20, None, _scene("S-1", 20))
        state.add_scene(30, None, _scene("S-2", 30))
        snap = state.snapshot(0, 0, 0)["narrative"]
        self.assertEqual(snap["count"], 2)
        self.assertEqual([item["id"] for item in snap["items"]], ["S-1", "S-2"])

    def test_narrative_items_keep_render_fields_only(self):
        state = LiveState()
        item = dict(_scene("S-1", 10), dialogue_refs=["DLG-1"], source=["x"])
        state.add_scene(10, None, item)
        kept = state.snapshot(0, 0, 0)["narrative"]["items"][0]
        self.assertEqual(set(kept),
                         {"id", "title", "version", "first_frame", "loop",
                          "before", "during", "after", "gap", "beats"})

    def test_finish_marks_done(self):
        state = LiveState()

        class _Traj:
            reached_frame = 42
            verdict = "ok"

        state.finish(_Traj(), cards=[("状态", "完", False)])
        snap = state.snapshot(0, 0, 0)
        self.assertTrue(snap["done"])
        self.assertEqual(snap["frame"], 42)
        self.assertEqual(snap["verdict"], "ok")


if __name__ == "__main__":
    unittest.main()
