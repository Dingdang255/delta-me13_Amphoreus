"""Wiring contract for the four trends that used to be unwired (002/005/007/008).

    python -m unittest tests.test_trends_wiring

Readings come from the real feature snapshot; a missing reading must surface as
``driver_missing`` with ``driver_value is None`` -- never as a fabricated 0.
"""
from __future__ import annotations

import unittest

import _support  # noqa: F401  # 挂 sys.path / 把 stdio 钉成 UTF-8

from apps import trends, viz

SPEC = trends.load_spec()
WIRED_IDS = ("TREND-002", "TREND-005", "TREND-007", "TREND-008")


def row_for(trend_id, features):
    view = trends.view_from_features(features)
    trend = SPEC["trends"][trend_id]
    row = trends.evaluate_trend(trend_id, trend["channels"], view, SPEC["epsilon"])[0]
    return view, row


class CoverageTest(unittest.TestCase):
    def test_all_eight_trends_are_wired(self):
        cov = trends.coverage(SPEC)
        self.assertEqual(cov["trends"], 8)
        self.assertEqual(cov["unwired"], {})
        self.assertEqual(len(cov["wired"]), 8)
        self.assertEqual(cov["channels"], 9)

    def test_wired_detail_covers_every_trend(self):
        cov = trends.coverage(SPEC)
        self.assertEqual({item["trend"] for item in cov["wired_detail"]},
                         set(SPEC["trends"]))
        for item in cov["wired_detail"]:
            self.assertTrue(item["channels"])
            self.assertEqual(len(item["channels"]), len(item["drivers"]))

    def test_new_channels_declare_source_and_confidence(self):
        for trend_id in WIRED_IDS:
            for ch in SPEC["trends"][trend_id]["channels"]:
                self.assertTrue(ch["source"], trend_id)
                self.assertIn(ch["confidence"], {"B", "C"}, trend_id)
                self.assertTrue(ch["inferred"], trend_id)


class RealReadingTest(unittest.TestCase):
    def test_stage_index_reaches_the_fourth_stage(self):
        view, row = row_for("TREND-002", {"domain_index": 2, "domains_exhausted": False})
        self.assertEqual(view["stage_index"], 3.0)
        self.assertAlmostEqual(row["value"], 2.0 / 3.0, places=6)
        self.assertTrue(row["active"])

        view, row = row_for("TREND-002", {"domain_index": 2, "domains_exhausted": True})
        self.assertEqual(view["stage_index"], 4.0)
        self.assertEqual(row["value"], 1.0)

    def test_promotion_gap_reads_interval_shortening(self):
        # gaps 100 / 100 / 100 / 40 -> later half averages 70 -> pressure 0.30
        view, row = row_for("TREND-005", {"promotion_frames": [0, 100, 200, 300, 340]})
        self.assertAlmostEqual(view["promotion_gap"], 0.30, places=6)
        self.assertGreater(row["value"], 0.0)
        self.assertTrue(row["active"])

    def test_promotion_gap_needs_three_shifts(self):
        view, row = row_for("TREND-005", {"promotion_frames": [0, 100]})
        self.assertIsNone(view["promotion_gap"])
        self.assertIsNone(row["driver_value"])
        self.assertEqual(row["note"], "driver_missing")

    def test_origin_closure_is_repaid_over_borrowed(self):
        view, row = row_for("TREND-007", {"origin_ever": True,
                                          "origin_borrowed": 4, "origin_repaid": 2})
        self.assertEqual(view["origin_closure"], 0.5)
        self.assertAlmostEqual(row["value"], 0.5, places=6)

    def test_disturb_share_normalizes_by_capability_count(self):
        view, row = row_for("TREND-008", {"disturb_capabilities": "a,b",
                                          "disturb_total": 6})
        self.assertEqual(view["disturb_share"], 3.0)
        self.assertAlmostEqual(row["value"], 2.0 / 3.0, places=6)
        self.assertTrue(row["active"])

    def test_absent_readings_stay_missing(self):
        for trend_id in WIRED_IDS:
            with self.subTest(trend=trend_id):
                view, row = row_for(trend_id, {})
                self.assertIsNone(row["driver_value"])
                self.assertEqual(row["note"], "driver_missing")


class OriginOffTest(unittest.TestCase):
    def test_origin_off_is_missing_not_zero(self):
        features = {"origin_ever": False, "origin_awake": False,
                    "origin_borrowed": 0, "origin_repaid": 0}
        view, row = row_for("TREND-007", features)
        self.assertIsNone(view["origin_closure"])
        self.assertIsNone(row["driver_value"])
        self.assertEqual(row["note"], "driver_missing")

        html = viz.narrative_panels_html([row], {})
        self.assertIn("driver_missing", html)
        self.assertIn("—", html)
        self.assertNotIn("0.00", html)


if __name__ == "__main__":
    unittest.main()
