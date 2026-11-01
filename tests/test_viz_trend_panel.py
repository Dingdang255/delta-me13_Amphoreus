"""趋势压力面板：布局（复用 `.bar`）与 13 字段接线。

两条要求：
  ① 面板不再借用 `.seats` 网格、不再硬编码 120px 槽，每行用 flex 占满宽度，
     进度条只复用既有的 `.bar` / `.bar i`；
  ② 13 个字段全部展示，缺值统一 `—` 并写明原因，绝不把缺失补成 0.00，
     也绝不编造「已接线」。
"""
from __future__ import annotations

import unittest

import _support  # noqa: F401  # 挂 sys.path / 把 stdio 钉成 UTF-8

from apps import trends, viz

META_LABELS = ("类型", "目标", "可观测量", "来源", "置信",
               "推断", "驱动", "驱动值", "备注")


def _row(**kw):
    row = {
        "trend": "TREND-003",
        "channel": "delay",
        "type": "delays",
        "target": "WG-020",
        "observable": "hatch_progress",
        "source": "S-001:424954",
        "confidence": "A",
        "inferred": True,
        "driver": "cycle_count",
        "driver_value": 12.5,
        "value": 0.42,
        "active": True,
        "note": "",
    }
    row.update(kw)
    return row


class TrendPanelLayoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = trends.load_spec()
        cls.view = {"cycle_count": 2500, "embers_taken": 3,
                    "memory_rows": 4, "entropy": 2.0, "noise": 2.0}
        cls.rows = trends.evaluate_all(cls.spec, cls.view)
        cls.cov = trends.coverage(cls.spec)
        cls.html = viz.narrative_panels_html(cls.rows, cls.cov)

    def test_no_table_or_seats_grid_leak(self):
        self.assertNotIn('table class="seats"', self.html)
        self.assertNotIn("width:120px", self.html)
        self.assertNotIn("<table", self.html)
        self.assertIn('class="trow"', self.html)

    def test_every_channel_gets_one_shared_bar(self):
        self.assertEqual(self.html.count('<div class="bar'), len(self.rows))
        self.assertIn('<div class="bar"><i style="width:', self.html)
        # 行布局是 flex：标签列 + 条列 + 数值列
        self.assertIn('class="tbar"', self.html)
        self.assertIn('class="tval"', self.html)

    def test_all_thirteen_fields_are_rendered(self):
        for label in META_LABELS:
            self.assertIn(f"<b>{label}</b>", self.html)
        for row in self.rows:
            self.assertIn(row["trend"], self.html)
            self.assertIn(row["channel"], self.html)

    def test_unwired_trends_keep_their_reason(self):
        cov = {"unwired": {"TREND-099": "样本不足"}}
        html = viz.narrative_panels_html([], cov)
        self.assertIn("未接线", html)
        self.assertIn("样本不足", html)

    def test_coverage_adds_detail_lists_without_breaking_old_keys(self):
        self.assertEqual(set(self.cov), {"trends", "wired", "unwired",
                                         "channels", "wired_detail",
                                         "unwired_detail"})
        self.assertEqual(len(self.cov["wired_detail"]), len(self.cov["wired"]))
        self.assertEqual(len(self.cov["unwired_detail"]), len(self.cov["unwired"]))
        for item in self.cov["wired_detail"]:
            self.assertEqual(len(item["channels"]), len(item["drivers"]))


class TrendPanelMissingTest(unittest.TestCase):
    def test_missing_value_and_driver_are_reported_not_zeroed(self):
        rows = [
            _row(channel="no_value", value=None, note=""),
            _row(channel="no_driver", driver="", driver_value=None,
                 value=0.0, note="driver_missing"),
        ]
        html = viz.narrative_panels_html(rows, {})
        self.assertNotIn("0.00", html)
        self.assertNotIn("已接线", html)
        self.assertIn("—", html)
        self.assertIn("value_missing", html)
        self.assertIn("driver_missing", html)
        self.assertEqual(html.count('<div class="bar'), 2)


if __name__ == "__main__":
    unittest.main()
