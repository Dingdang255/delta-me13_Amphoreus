"""Contract tests for narrative panel ordering and collapsible scenes.

The panel must render in story-time order no matter how the items arrive (the
live stream pushes them as rounds land), with frame-less records last and each
scene folded into a `<details>`.

    python -m unittest discover -s tests -p "test_narrative_order.py" -q
"""
from __future__ import annotations

import unittest

from apps import scenes, viz


def _item(scene_id, frame, version="3.0", source="beat"):
    return {"id": scene_id, "title": scene_id, "version": version,
            "first_frame": frame, "first_frame_source": source,
            "during": ["一步"], "gap": ""}


class NarrativeOrderTest(unittest.TestCase):
    def _shake(self):
        return [
            _item("B1", 200),
            _item("A2", 100, "3.7"),
            _item("A1b", 100, "3.0"),
            _item("C1", None),
            _item("A1a", 100, "3.0"),
            _item("C0", None),
        ]

    def test_items_render_in_frame_version_id_order(self):
        html = viz.narrative_block_html(self._shake())
        expected = ["A1a", "A1b", "A2", "B1", "C0", "C1"]
        positions = [html.index(name) for name in expected]
        self.assertEqual(positions, sorted(positions))

    def test_frameless_items_go_last_and_say_unknown(self):
        html = viz.narrative_block_html(self._shake())
        self.assertEqual(html.count("时序未知"), 2)
        self.assertGreater(html.index("C0"), html.index("B1"))
        self.assertGreater(html.index("C1"), html.index("B1"))

    def test_every_scene_is_a_details_block(self):
        html = viz.narrative_block_html(self._shake())
        self.assertEqual(html.count('<details class="scene">'), 6)
        self.assertEqual(html.count("<summary>"), 6)
        self.assertEqual(html.count("</details>"), 6)

    def test_projected_frames_are_labelled(self):
        html = viz.narrative_block_html([_item("P", 10, source="projected")])
        self.assertIn("帧为投影", html)

    def test_empty_list_renders_nothing(self):
        self.assertEqual(viz.narrative_block_html([]), "")
        self.assertEqual(viz.narrative_block_html(None), "")

    def test_narrate_keeps_frame_source(self):
        row = scenes.narrate({"id": "X", "title": "X", "first_frame": 7,
                              "first_frame_source": "projected"})
        self.assertEqual(row["first_frame_source"], "projected")
        row = scenes.narrate({"id": "Y", "title": "Y", "first_frame": 8})
        self.assertEqual(row["first_frame_source"], "beat")


if __name__ == "__main__":
    unittest.main()
