"""投递条件求值器（`engine/conditions.py`）：三类词法 / 拒绝未知量 / 拒绝预读未来。"""
import json
import os
import unittest

from _support import ROOT      # noqa: F401  （挂 sys.path + 钉 BLAS 线程）


class ParsingAndEvaluating(unittest.TestCase):
    def test_three_kinds(self):
        from engine.conditions import evaluate

        obs = {"frame": 12000, "promotions": 9, "order": 0.5,
               "events": {"nikador_felled": True, "other": False}}
        self.assertTrue(evaluate("frame >= 12000", obs))            # ① 观测量
        self.assertTrue(evaluate("promotions >= 8", obs))           # ② 账本计数
        self.assertTrue(evaluate('event("nikador_felled")', obs))   # ③ 事件
        self.assertFalse(evaluate('event("other")', obs))
        self.assertFalse(evaluate("order > 0.9", obs))

    def test_boolean_algebra_and_parens(self):
        from engine.conditions import evaluate

        obs = {"a": 1, "b": 0, "events": {}}
        self.assertTrue(evaluate("a && !b", obs))
        self.assertTrue(evaluate("b || (a && !b)", obs))
        self.assertFalse(evaluate("!a || b", obs))
        self.assertTrue(evaluate("   a   ", obs))       # 前后空白不影响

    def test_repeated_evaluation_is_deterministic(self):
        from engine.conditions import evaluate

        obs = {"frame": 5, "events": {}}
        self.assertEqual({evaluate("frame >= 5", obs) for _ in range(50)}, {True})


class RejectsBadConditions(unittest.TestCase):
    def test_unknown_name(self):
        from engine.conditions import ConditionError, evaluate
        with self.assertRaises(ConditionError):
            evaluate("nonesuch >= 1", {"frame": 0, "events": {}})

    def test_unknown_event(self):
        from engine.conditions import ConditionError, evaluate
        with self.assertRaises(ConditionError):
            evaluate('event("nope")', {"frame": 0, "events": {}})

    def test_type_mismatch(self):
        from engine.conditions import ConditionError, evaluate
        with self.assertRaises(ConditionError):
            evaluate('frame >= "x"', {"frame": 1, "events": {}})

    def test_no_lookahead_shapes_parse_at_all(self):
        """预读未来的写法在【词法】这一层就不成立 —— 这正是我们要的性质。"""
        from engine.conditions import ConditionError, parse
        for bad in ("state[n+1]", "events.peek()", "traj.final",
                    "x; y", "__import__('os')", "frame >= 1 + 2"):
            with self.assertRaises(ConditionError):
                parse(bad)

    def test_terms(self):
        from engine.conditions import terms
        self.assertEqual(terms('promotions >= 8 && event("x")'),
                         {"promotions", "event:x"})

    def test_check_rejects_unknown(self):
        from engine.conditions import ConditionError, check
        self.assertEqual(check("frame >= 1", allowed_names={"frame"}), {"frame"})
        with self.assertRaises(ConditionError):
            check("frame >= 1", allowed_names={"promotions"})
        with self.assertRaises(ConditionError):
            check('event("x")', allowed_names=set(), allowed_events={"y"})


class PresetsOnlyUseKnownTerms(unittest.TestCase):
    """闸门：仓库里每个预设的 `when`（一旦有人开始写）都必须能解析、且只用已知量。

    目前还没有预设写 `when`，所以这条现在恒真；它是**为第一条 `when` 准备的关卡**。
    校验放在测试里而不是 `engine/loader.py` 里 —— 后者会让内核 import 服务层，
    立刻多一条分层越界（见 tools/layer_lint.py 的棘轮）。
    """

    #: 允许的观测 / 账本量。与内核 `observe()` 的口径一一对应。
    NAMES = {"frame", "order", "entropy", "noise", "promotions", "round",
             "attempts", "skipped_frames", "personas", "population",
             "domain_index", "destruction_events", "promotion_cooldown"}

    def _rows(self, preset_dir):
        for fn in ("events.jsonl", "disturbances.jsonl"):
            path = os.path.join(preset_dir, fn)
            if not os.path.exists(path):
                continue
            with open(path, encoding="utf-8") as f:
                for ln, line in enumerate(f, 1):
                    line = line.strip()
                    if line:
                        yield fn, ln, json.loads(line)

    def test_all_presets(self):
        from engine.conditions import check

        root = os.path.join(ROOT, "presets")
        seen = 0
        for preset in sorted(os.listdir(root)):
            d = os.path.join(root, preset)
            if not os.path.isdir(d):
                continue
            events = {str((r.get("payload") or {}).get("event"))
                      for _, _, r in self._rows(d)
                      if (r.get("payload") or {}).get("event")}
            for fn, ln, row in self._rows(d):
                expr = row.get("when")
                if not expr:
                    continue
                try:
                    check(expr, allowed_names=self.NAMES, allowed_events=events)
                except Exception as exc:                       # noqa: BLE001
                    self.fail(f"{preset}/{fn}:L{ln} 的 when 不合法：{exc}")
                seen += 1
        self.assertGreaterEqual(seen, 0)


if __name__ == "__main__":
    unittest.main()
