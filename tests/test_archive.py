"""只读档案层（`apps/archive.py`）：校验、排序、抵达判定、事件缺失、进度。

档案层是只读渲染：它不写 `st`、不改 `traj`，判定只用 `reached_frame` /
`deadlock` / `final.score` 三处读数。这里只验这些性质，不跑长演算。
"""
from __future__ import annotations

import json
import os
import tempfile
import types
import unittest

from _support import ROOT      # noqa: F401  （挂 sys.path + 钉 BLAS 线程）

from apps.archive import DEFAULT_TITLES, load_archive, render


def _write(dirpath, payload, name="archive.json"):
    """把一份 JSON 写进临时目录，返回路径。"""
    path = os.path.join(dirpath, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    return path


def _traj(reached=0, deadlock=False, score=None):
    return types.SimpleNamespace(reached_frame=reached, deadlock=deadlock,
                                 final=types.SimpleNamespace(score=dict(score or {})))


def _arc(**kw):
    base = {"titles": dict(DEFAULT_TITLES), "progress": [], "archive": [],
            "anomalies": []}
    base.update(kw)
    return base


class LoadArchiveTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_missing_file_is_empty(self):
        self.assertEqual(load_archive(os.path.join(self.tmp, "nope.json")), {})
        self.assertEqual(load_archive(None), {})

    def test_defaults_are_filled(self):
        arc = load_archive(_write(self.tmp, {}))
        self.assertEqual(arc["titles"], DEFAULT_TITLES)
        self.assertEqual(arc["progress"], [])
        self.assertEqual(arc["archive"], [])
        self.assertEqual(arc["anomalies"], [])

    def test_titles_merge_over_defaults(self):
        arc = load_archive(_write(self.tmp, {"titles": {"archive": "归档"}}))
        self.assertEqual(arc["titles"]["archive"], "归档")
        self.assertEqual(arc["titles"]["anomalies"], DEFAULT_TITLES["anomalies"])
        self.assertEqual(arc["titles"]["progress"], DEFAULT_TITLES["progress"])

    def test_progress_is_sorted_by_frame(self):
        arc = load_archive(_write(self.tmp, {"progress": [
            {"percent": 55, "frame": 11000, "label": "c"},
            {"percent": 3, "frame": 2000, "label": "a"},
            {"percent": 19, "frame": 6000, "label": "b"},
        ]}))
        self.assertEqual([p["frame"] for p in arc["progress"]], [2000, 6000, 11000])
        self.assertEqual([p["percent"] for p in arc["progress"]], [3, 19, 55])

    def test_archive_is_sorted_by_frame_then_id(self):
        arc = load_archive(_write(self.tmp, {"archive": [
            {"id": "C", "title": "t", "body": "b"},
            {"id": "B", "title": "t", "body": "b", "frame": 20},
            {"id": "A", "title": "t", "body": "b", "frame": 20},
            {"id": "D", "title": "t", "body": "b", "frame": 0},
        ]}))
        self.assertEqual([r["id"] for r in arc["archive"]], ["D", "A", "B", "C"])

    def test_progress_invalid_fields(self):
        good = {"percent": 3, "frame": 2000, "label": "ok"}
        cases = [
            ({"frame": 1, "label": "x"}, "percent"),
            ({"percent": -1, "frame": 1, "label": "x"}, "percent"),
            ({"percent": 101, "frame": 1, "label": "x"}, "percent"),
            ({"percent": "3", "frame": 1, "label": "x"}, "percent"),
            ({"percent": True, "frame": 1, "label": "x"}, "percent"),
            ({"percent": 3, "label": "x"}, "frame"),
            ({"percent": 3, "frame": -1, "label": "x"}, "frame"),
            ({"percent": 3, "frame": 1.5, "label": "x"}, "frame"),
            ({"percent": 3, "frame": 1, "label": "  "}, "label"),
        ]
        for row, needle in cases:
            with self.subTest(row=row):
                with self.assertRaises(ValueError) as ctx:
                    load_archive(_write(self.tmp, {"progress": [good, row]}))
                self.assertIn("progress[1]", str(ctx.exception))
                self.assertIn(needle, str(ctx.exception))

    def test_archive_invalid_fields(self):
        good = {"id": "A", "title": "t", "body": "b"}
        cases = [
            ({"title": "t", "body": "b"}, "id"),
            ({"id": "A", "body": "b"}, "title"),
            ({"id": "A", "title": "t"}, "body"),
            ({"id": "A", "title": "t", "body": "b", "frame": -1}, "frame"),
            ({"id": "A", "title": "t", "body": "b", "frame": 1.2}, "frame"),
            ({"id": "A", "title": "t", "body": "b", "stage": 3}, "stage"),
            ({"id": "A", "title": "t", "body": "b", "loop": ""}, "loop"),
        ]
        for row, needle in cases:
            with self.subTest(row=row):
                with self.assertRaises(ValueError) as ctx:
                    load_archive(_write(self.tmp, {"archive": [good, row]}))
                self.assertIn("archive[1]", str(ctx.exception))
                self.assertIn(needle, str(ctx.exception))

    def test_anomalies_invalid_fields(self):
        good = {"id": "X", "title": "t", "body": "b"}
        cases = [
            ({"title": "t", "body": "b"}, "id"),
            ({"id": "X", "body": "b"}, "title"),
            ({"id": "X", "title": "t"}, "body"),
            ({"id": "X", "title": "t", "body": "b", "event": ""}, "event"),
            ({"id": "X", "title": "t", "body": "b", "event": 7}, "event"),
        ]
        for row, needle in cases:
            with self.subTest(row=row):
                with self.assertRaises(ValueError) as ctx:
                    load_archive(_write(self.tmp, {"anomalies": [good, row]}))
                self.assertIn("anomalies[1]", str(ctx.exception))
                self.assertIn(needle, str(ctx.exception))

    def test_bad_shapes_are_loud(self):
        with self.assertRaises(ValueError) as ctx:
            load_archive(_write(self.tmp, []))
        self.assertIn("<root>", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            load_archive(_write(self.tmp, {"progress": {}}))
        self.assertIn("progress", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            load_archive(_write(self.tmp, {"titles": []}))
        self.assertIn("titles", str(ctx.exception))
        path = os.path.join(self.tmp, "broken.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write("{not json}")
        with self.assertRaises(ValueError) as ctx:
            load_archive(path)
        self.assertIn("不是合法 JSON", str(ctx.exception))

    def test_plot_sample_is_valid(self):
        arc = load_archive(os.path.join(ROOT, "presets", "plot", "archive.json"))
        self.assertEqual([p["percent"] for p in arc["progress"]],
                         [3, 19, 55, 70, 100])
        self.assertEqual([p["frame"] for p in arc["progress"]],
                         [2000, 6000, 11000, 33594527, 33594547])
        self.assertEqual([r["id"] for r in arc["archive"]],
                         ["归档01", "归档02", "归档03"])
        self.assertEqual([a["title"] for a in arc["anomalies"]],
                         ["永劫回归", "心中的英雄", "被遗忘的岁月"])
        self.assertEqual(arc["anomalies"][0]["event"], "deadlock")
        self.assertEqual({r["stage"] for r in arc["archive"]}, {"无机"})
        self.assertEqual({r["loop"] for r in arc["archive"]}, {"1–50121"})


class RenderTest(unittest.TestCase):
    PROGRESS = [
        {"percent": 3, "frame": 2000, "label": "a"},
        {"percent": 19, "frame": 6000, "label": "b"},
        {"percent": 100, "frame": 9000, "label": "c"},
    ]

    def test_empty_archive_renders_nothing(self):
        self.assertEqual(render(None, None, _traj(), {}), [])
        self.assertEqual(render(None, None, _traj(), None), [])

    def test_two_sections_with_titles(self):
        out = render(None, None, _traj(), _arc())
        self.assertEqual([t for t, _ in out], ["【六】实验档案", "【七】异常记录"])

    def test_titles_are_overridable(self):
        arc = _arc(titles={"archive": "甲", "anomalies": "乙", "progress": "丙"})
        out = render(None, None, _traj(), arc)
        self.assertEqual([t for t, _ in out], ["【六】甲", "【七】乙"])

    def test_progress_zero_percent(self):
        out = render(None, None, _traj(reached=0), _arc(progress=self.PROGRESS))
        self.assertEqual(out[0][1][0], "实验进度    已抵达 0%（下一档 3% @ 2000）")

    def test_progress_middle(self):
        out = render(None, None, _traj(reached=6000), _arc(progress=self.PROGRESS))
        self.assertEqual(out[0][1][0], "实验进度    已抵达 19%（下一档 100% @ 9000）")

    def test_progress_complete(self):
        out = render(None, None, _traj(reached=9000), _arc(progress=self.PROGRESS))
        self.assertEqual(out[0][1][0], "实验进度    已抵达 100%")

    def test_archive_reached_and_not_reached(self):
        arc = _arc(archive=[
            {"id": "A", "title": "甲", "body": "正文甲", "stage": "无机"},
            {"id": "B", "title": "乙", "body": "正文乙", "stage": "有机", "frame": 5000},
            {"id": "C", "title": "丙", "body": "正文丙", "loop": "1–9", "frame": 9999},
        ])
        lines = render(None, None, _traj(reached=5000), arc)[0][1]
        self.assertEqual(lines[0], "[—] A · 无机 · 甲")
        self.assertEqual(lines[1], "      正文甲")
        self.assertEqual(lines[2], "[已抵达] B · 有机 · 乙")
        self.assertEqual(lines[3], "      正文乙")
        self.assertEqual(lines[4], "[未抵达] C · 1–9 · 丙")
        self.assertEqual(lines[5], "      正文丙")

    def test_loop_wins_over_stage_and_placeholder_when_both_missing(self):
        arc = _arc(archive=[
            {"id": "A", "title": "甲", "body": "b"},
            {"id": "B", "title": "乙", "body": "b", "stage": "无机", "loop": "1–2"},
        ])
        lines = render(None, None, _traj(), arc)[0][1]
        self.assertEqual(lines[0], "[—] A · — · 甲")
        self.assertEqual(lines[2], "[—] B · 1–2 · 乙")

    def test_anomaly_deadlock_happened_and_not(self):
        arc = _arc(anomalies=[{"id": "X", "title": "回归", "body": "b", "event": "deadlock"}])
        hit = render(None, None, _traj(deadlock=True), arc)[1][1]
        miss = render(None, None, _traj(deadlock=False), arc)[1][1]
        self.assertEqual(hit, ["[本轨道发生] X · 回归", "      b"])
        self.assertEqual(miss, ["[本轨道未发生] X · 回归", "      b"])

    def test_anomaly_event_happened_and_not(self):
        arc = _arc(anomalies=[{"id": "X", "title": "镜", "body": "b", "event": "mirror"}])
        hit = render(None, None, _traj(score={"emitted_mirror": 1.0}), arc)[1][1]
        miss = render(None, None, _traj(score={"emitted_other": 1.0}), arc)[1][1]
        self.assertEqual(hit[0], "[本轨道发生] X · 镜")
        self.assertEqual(miss[0], "[本轨道未发生] X · 镜")

    def test_anomaly_without_event_is_dash(self):
        arc = _arc(anomalies=[{"id": "X", "title": "岁月", "body": "b"}])
        lines = render(None, None, _traj(score={"emitted_mirror": 1.0}), arc)[1][1]
        self.assertEqual(lines, ["[—] X · 岁月", "      b"])

    def test_render_does_not_write_traj(self):
        score = {"emitted_mirror": 1.0, "memory_repaired": 0.0}
        traj = _traj(reached=6000, deadlock=True, score=score)
        before = json.dumps(score, sort_keys=True)
        arc = _arc(progress=self.PROGRESS, anomalies=[
            {"id": "X", "title": "镜", "body": "b", "event": "mirror"},
            {"id": "Y", "title": "回归", "body": "b", "event": "deadlock"},
        ])
        render(None, None, traj, arc)
        self.assertEqual(json.dumps(score, sort_keys=True), before)
        self.assertIsInstance(traj.final.score, dict)
        self.assertEqual(traj.reached_frame, 6000)
        self.assertIs(traj.deadlock, True)


class ReportIntegrationTest(unittest.TestCase):
    """`run.report(..., narrative=…)`：未启用时逐字不变，启用时只多出两节。"""

    @classmethod
    def setUpClass(cls):
        from _support import load
        cls.ctx, cls.data, cls.traj = load("plot", frames=3)

    def test_narrative_none_keeps_report_unchanged(self):
        import run

        plain = run.report(self.ctx, self.data, self.traj, [])
        again = run.report(self.ctx, self.data, self.traj, [], narrative=None)
        self.assertEqual(plain, again)
        self.assertNotIn("【六】", plain)

    def test_narrative_appends_sections_before_the_last_rule(self):
        import run

        plain = run.report(self.ctx, self.data, self.traj, [])
        narrative = [("【六】实验档案", ["进度行", "条目"]),
                     ("【七】异常记录", ["[—] X · 回归"])]
        text = run.report(self.ctx, self.data, self.traj, [], narrative=narrative)
        self.assertNotIn("【六】", plain)
        self.assertIn("【六】实验档案\n进度行\n条目\n\n【七】异常记录\n[—] X · 回归\n\n"
                      + run.BAR, text)
        self.assertTrue(text.endswith(run.BAR))
        self.assertTrue(plain.endswith(run.BAR))


if __name__ == "__main__":
    unittest.main()
