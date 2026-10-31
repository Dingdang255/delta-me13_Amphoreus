"""Contract tests for the trend evaluator (P4).

    python -m unittest tests.test_trends
"""
from __future__ import annotations

import unittest

from apps import trends

SPEC = trends.load_spec()

FULL = {
    "cycle_count": 33550336,
    "embers_taken": 402604032,
    "memory_rows": 12,
    "entropy": 1.65,
    "noise": 0.71,
}


def rows_for(trend_id, view):
    trend = SPEC["trends"][trend_id]
    return trends.evaluate_trend(trend_id, trend["channels"], view, SPEC["epsilon"])


class TestTrendSpec(unittest.TestCase):
    def test_eight_trends(self):
        self.assertEqual(len(SPEC["trends"]), 8)
        self.assertEqual(len(SPEC["drivers"]), 5)
        self.assertGreaterEqual(len(SPEC["targets"]), 8)

    def test_unwired_declare_reason(self):
        for trend_id, trend in SPEC["trends"].items():
            if trend["status"] == "unwired":
                self.assertTrue(trend.get("reason"), f"{trend_id} has no reason")

    def test_every_wired_channel_is_sourced_and_inferred(self):
        for trend_id, trend in SPEC["trends"].items():
            if trend["status"] != "wired":
                continue
            for ch in trend["channels"]:
                self.assertTrue(ch["source"], f"{trend_id}/{ch['id']} has no source")
                self.assertIn(ch["confidence"], {"A", "B", "C", "D", "E"})
                self.assertTrue(ch.get("inferred"), f"{trend_id}/{ch['id']} not marked inferred")


class TestTrendEvaluation(unittest.TestCase):
    def test_dual_channels_do_not_cancel(self):
        delay_only = rows_for("TREND-003", {"cycle_count": 33550336})
        tendency_only = rows_for("TREND-003", {"embers_taken": 402604032})
        both = rows_for("TREND-003", FULL)

        by_id = {r["channel"]: r for r in both}
        delay = by_id["delay"]["value"]
        tendency = by_id["tendency"]["value"]

        self.assertGreater(delay, 0.9)
        # the two channels are independent: each stays positive when the other is absent
        self.assertGreater(delay, 0.0)
        self.assertGreater(tendency, 0.0)
        # delay channel does not read embers at all
        self.assertEqual([r for r in delay_only if r["channel"] == "delay"][0]["value"],
                         round(delay, 6))
        # tendency channel does not read cycles at all
        self.assertEqual([r for r in tendency_only if r["channel"] == "tendency"][0]["value"],
                         round(tendency, 6))

    def test_tendency_is_monotonic_and_bounded(self):
        values = []
        for embers in (0, 1000, 1000000, 402604032, 10 ** 12):
            rows = rows_for("TREND-003", {"embers_taken": embers})
            values.append([r for r in rows if r["channel"] == "tendency"][0]["value"])
        self.assertEqual(values, sorted(values))
        self.assertLessEqual(values[-1], SPEC["trends"]["TREND-003"]["channels"][1]["cap"])

    def test_threshold_channel_is_zero_below_threshold(self):
        low = rows_for("TREND-001", {"entropy": 0.2})
        high = rows_for("TREND-001", {"entropy": 1.65})
        self.assertEqual(low[0]["value"], 0.0)
        self.assertGreater(high[0]["value"], 0.0)

    def test_missing_driver_is_reported_not_guessed(self):
        rows = trends.evaluate_all(SPEC, {})
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(row["value"], 0.0)
            self.assertFalse(row["active"])
            self.assertEqual(row["note"], "driver_missing")

    def test_deterministic(self):
        a = trends.evaluate_all(SPEC, FULL)
        b = trends.evaluate_all(SPEC, FULL)
        self.assertEqual(a, b)

    def test_epsilon_controls_active_flag(self):
        weak = rows_for("TREND-006", {"memory_rows": 0.4})
        self.assertFalse(weak[0]["active"])
        strong = rows_for("TREND-006", {"memory_rows": 12})
        self.assertTrue(strong[0]["active"])

    def test_view_from_features_maps_snapshot_keys(self):
        features = {"iterations": 100, "embers_taken": 7, "memory_rows": 3,
                    "final_entropy": 1.2, "final_noise": 0.9}
        view = trends.view_from_features(features)
        self.assertEqual(view["cycle_count"], 100)
        self.assertEqual(view["embers_taken"], 7)
        self.assertEqual(view["memory_rows"], 3)
        self.assertEqual(view["entropy"], 1.2)
        self.assertEqual(view["noise"], 0.9)

    def test_coverage_reports_unwired(self):
        cov = trends.coverage(SPEC)
        self.assertEqual(cov["trends"], 8)
        self.assertEqual(len(cov["wired"]) + len(cov["unwired"]), 8)
        self.assertEqual(len(cov["unwired"]), 4)


if __name__ == "__main__":
    unittest.main()
