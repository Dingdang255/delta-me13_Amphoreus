"""Contract tests for the world generator (P3).

    python -m unittest tests.test_worldgen
"""
from __future__ import annotations

import hashlib
import os
import unittest

from apps import worldgen

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "config")


def _tree_digest(folder):
    h = hashlib.sha256()
    for base, dirs, names in os.walk(folder):
        dirs.sort()
        for name in sorted(names):
            path = os.path.join(base, name)
            h.update(os.path.relpath(path, folder).replace(os.sep, "/").encode("utf-8"))
            with open(path, "rb") as f:
                h.update(f.read())
    return h.hexdigest()


class TestWorldGen(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = worldgen.load_spec()
        cls.w0 = worldgen.bootstrap_world(0, cls.spec, ROOT)
        cls.w7 = worldgen.bootstrap_world(7, cls.spec, ROOT)

    def test_twenty_dimensions(self):
        dims = self.spec["dimensions"]
        self.assertEqual(len(dims), 20)
        keys = [d["key"] for d in dims]
        self.assertEqual(len(set(keys)), 20)
        sampled = [d for d in dims if d["status"] == "sampled"]
        self.assertGreaterEqual(len(sampled), 8)
        for dim in sampled:
            for knob in dim["knobs"]:
                self.assertIn(knob, self.spec["knobs"], f"{dim['key']} -> {knob}")

    def test_same_seed_is_deterministic(self):
        again = worldgen.bootstrap_world(0, self.spec, ROOT)
        self.assertEqual(again["manifest"]["world_digest"],
                         self.w0["manifest"]["world_digest"])
        a = worldgen.build_files(self.w0, self.spec, ROOT)
        b = worldgen.build_files(again, self.spec, ROOT)
        self.assertEqual(a.keys(), b.keys())
        for rel in a:
            self.assertEqual(a[rel], b[rel], f"{rel} differs between runs")

    def test_different_seeds_diverge(self):
        changed = worldgen.diff_dimensions(self.w0, self.w7)
        self.assertGreaterEqual(len(changed), 6,
                                f"only {len(changed)} dimensions changed: {changed}")
        self.assertNotEqual(self.w0["manifest"]["world_digest"],
                            self.w7["manifest"]["world_digest"])

    def test_template_digest_is_independent_of_seed(self):
        self.assertEqual(self.w0["manifest"]["template_digest"],
                         self.w7["manifest"]["template_digest"])

    def test_canonical_config_is_not_touched(self):
        before = _tree_digest(CONFIG)
        world = worldgen.bootstrap_world(12345, self.spec, ROOT)
        worldgen.build_files(world, self.spec, ROOT)
        after = _tree_digest(CONFIG)
        self.assertEqual(before, after, "generation wrote into the tracked config/")

    def test_constraints_hold(self):
        seeding = self.w7["config"]["config/seeding.json"]
        self.assertGreaterEqual(seeding["per_locus"]["max"], seeding["per_locus"]["min"])
        self.assertGreaterEqual(seeding["per_locus"]["min"], 3)
        self.assertLessEqual(seeding["per_locus"]["max"], 9)
        self.assertTrue(0.15 <= seeding["alpha"] <= 0.6)

        loci = self.w7["config"]["config/loci.json"]["loci"]
        n = len(loci)
        for i in range(n):
            self.assertEqual(loci[i]["couplings"][i], 0.0, "diagonal must stay 0")
            self.assertTrue(0.12 <= loci[i]["capacity"] <= 0.32)
            for j in range(i + 1, n):
                self.assertAlmostEqual(loci[i]["couplings"][j],
                                       loci[j]["couplings"][i], places=6,
                                       msg="couplings must stay symmetric")

        matrix = self.w7["config"]["config/mapping.json"]["matrix"]
        for row in matrix:
            for value in row:
                self.assertTrue(-1.0 <= value <= 1.0)

    def test_sampled_dimensions_are_marked_inferred(self):
        for key, dim in self.w0["dimensions"].items():
            self.assertTrue(dim["inferred"], f"{key} should be marked inferred")
            if dim["status"] == "sampled":
                self.assertTrue(dim["signatures"])


if __name__ == "__main__":
    unittest.main()
