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

    @staticmethod
    def _known_names():
        """内核 `obs_now()` 会给出的全部名字 —— 与 core.py 的构造一一对应。"""
        from engine.disturbance import CAPABILITIES
        from engine.state import DEATH_CAUSES

        return ({"frame", "promotions", "round", "domain_index", "entropy",
                 "personas", "deadlocked", "seats_filled", "seats_vacant", "deaths"}
                | {f"seat_l{i:02d}" for i in range(32)}          # 席位（按 loci.id）
                | {f"cap_{c}" for c in CAPABILITIES}             # 能力（按配置的能力表）
                | {f"deaths_{c}" for c in DEATH_CAUSES})         # 账本（按死因分档）

    def test_all_presets(self):
        from engine.conditions import check

        root = os.path.join(ROOT, "presets")
        names = self._known_names()
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
                    check(expr, allowed_names=names, allowed_events=events)
                except Exception as exc:                       # noqa: BLE001
                    self.fail(f"{preset}/{fn}:L{ln} 的 when 不合法：{exc}")
                seen += 1
        self.assertGreaterEqual(seen, 0)


class ConditionReallyGatesDispatch(unittest.TestCase):
    """证明条件**真的**在管投递 —— 不是摆设。

    做法：拿 plot 的一份【内存副本】，把最早那条投递（1200 帧的纳努克目光）改成
    条件永远不成立 → 断言它整场都不触发；再改成恒真 → 断言照旧在 1200 帧触发。
    （后者就是 `tools/dual_track.py` 在整条时间线上验的那件事的单点版。）
    """

    def _gaze_frames(self, when, frames=1400):
        from engine.conditions import evaluate
        from engine.core import run
        from engine.loader import Config, DataSet
        from engine.namer import Namer

        data = DataSet(ROOT, preset="plot")
        ctx = Config(ROOT, lex_overlay=data.preset.get("lexicon"))
        rec = min(data.disturbances, key=lambda r: int(r["frame"]))
        self.assertEqual(int(rec["frame"]), 1200)          # 前提：最早那条就在 1200
        rec["when"] = when
        data.conditioned = [r for r in data.disturbances if r.get("when")]
        traj = run(ctx, data, seed=0, max_frames=frames,
                   namer=Namer(ctx, data.anchors), rules=evaluate)
        return [f for f, k, p in traj.records
                if k == "DISTURBANCE" and p.get("capability") == "gaze"]

    def test_condition_gates_the_dispatch(self):
        self.assertEqual(self._gaze_frames("entropy < 0"), [])         # 永假 ⇒ 永不触发
        self.assertEqual(self._gaze_frames("frame >= 1200"), [1200])   # 退化 ⇒ 照旧

    def test_missing_predicate_is_loud(self):
        """有 when 却不给谓词 —— 必须当场报错，绝不静默忽略。"""
        from engine.core import run
        from engine.loader import Config, DataSet

        data = DataSet(ROOT, preset="plot")
        ctx = Config(ROOT, lex_overlay=data.preset.get("lexicon"))
        first = min(data.disturbances, key=lambda r: int(r["frame"]))
        first["when"] = "frame >= 0"
        data.conditioned = [first]
        with self.assertRaises(ValueError):
            run(ctx, data, seed=0, max_frames=8)

    def test_obs_exposes_seats_caps_and_ledger(self):
        """扩出来的观测量**真的读得到** —— 任一名字缺失都会让求值抛错。"""
        from engine.conditions import evaluate
        from engine.core import run
        from engine.loader import Config, DataSet
        from engine.namer import Namer

        data = DataSet(ROOT, preset="plot")
        ctx = Config(ROOT, lex_overlay=data.preset.get("lexicon"))
        first = min(data.disturbances, key=lambda r: int(r["frame"]))
        first["when"] = ("seat_l00 >= 0 && seats_filled >= 0 && seats_vacant >= 0"
                         " && cap_emit >= 0 && deaths >= 0 && deaths_aged >= 0"
                         " && deadlocked >= 0")
        data.conditioned = [first]
        # 跑 60 帧即可：条件每帧都会被求值一次（条目到 1200 帧才到期，故不会真触发）
        run(ctx, data, seed=0, max_frames=60,
            namer=Namer(ctx, data.anchors), rules=evaluate)


if __name__ == "__main__":
    unittest.main()
