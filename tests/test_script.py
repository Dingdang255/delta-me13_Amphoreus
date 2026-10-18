"""§D2 事件驱动应用模型（`apps/script.py`）：订阅 + 响应。

三条要证的事：

  1. **退化等价可证**（不是"跑一遍碰运气"）：`compile_rules(from_events(旧行))` 的定时
     投递与旧行**逐字相同**；用编译结果跑出来的世界，事件逐条与用旧行跑出来的相同、
     终局 digest 相同。这就是"脚本的退化形式 ≡ 旧日程表"的等式版。
  2. **反应真的在响应**：`on: <事件类别>` 的规则在事件发生后**下一帧**投递、只触发一次；
     `if` 不成立就继续等下一次同类事件；条件读到的世界是**事件那一帧**的活状态。
  3. **写错当场报错**：未知订阅名 / 反应式带 `at` / `FRAME` 缺 `at` / `do` 为空 /
     条件用了未知量 / 非 emit 动作没申报 permit / permit 没登记 / 未知 capability /
     未知选择器；以及 `events.jsonl` 与 `script.jsonl` 同存。
"""
import json
import os
import tempfile
import unittest

from _support import ROOT, temp_root_with_copy      # noqa: F401


# ---- 公共装配 -----------------------------------------------------------------
def _rows(preset, fn):
    """读一个预设的某个 jsonl —— 文件不在就是空表。"""
    path = os.path.join(ROOT, "presets", preset, fn)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def _run(preset, seed=0, frames=200, install=None):
    """跑一个小世界。`install(script, data)` 用来在跑之前挂脚本（不给就不挂）。"""
    from apps.conditions import evaluate
    from apps.namer import Namer
    from apps.services import default as default_services
    from kernel.core import run
    from kernel.loader import Config, DataSet

    data = DataSet(ROOT, preset=preset)
    ctx = Config(ROOT, lex_overlay=data.preset.get("lexicon"))
    if install is not None:
        install(data)
    return run(ctx, data, seed=seed, max_frames=frames,
               namer=Namer(ctx, data.anchors), rules=evaluate,
               runtime=default_services())


def _session(rows=(), events=(), preset="_default", seed=0, watch=None, peek=None):
    """一个挂了脚本反应的会话 —— 反应测试的公共台子。

    返回 `(sess, script)`；调用方自己 `sess.inject(...)` 造事件、`sess.step(n)` 推进。
    """
    from apps.conditions import evaluate
    from apps.namer import Namer
    from apps.script import Script, compile_rules
    from apps.services import default as default_services
    from kernel.api import load
    from kernel.loader import Config, DataSet

    data = DataSet(ROOT, preset=preset)
    ctx = Config(ROOT, lex_overlay=data.preset.get("lexicon"))
    script = Script(compile_rules(list(rows), cfg=ctx, actors=data.actors,
                                  events=events))
    namer = Namer(ctx, data.anchors)

    def on_event(frame, kind, payload=None, clock=None, namer=None):
        if peek is not None:
            peek(frame, kind, payload)
        script.on_event(frame, kind, payload, clock, namer)

    sess = load({"config": ctx, "data": data, "seed": seed, "namer": namer,
                 "rules": evaluate, "runtime": default_services(),
                 "on_event": on_event, "watch": watch})
    script.bind(sess)
    return sess, script


class DegenerateEquivalence(unittest.TestCase):
    """`from_events` → `compile_rules` 无损；编译结果跑出来的世界与旧行逐位一致。"""

    def test_round_trip_is_lossless_for_every_preset(self):
        from apps.script import compile_rules, from_events

        checked = 0
        root = os.path.join(ROOT, "presets")
        for preset in sorted(os.listdir(root)):
            if not os.path.isdir(os.path.join(root, preset)):
                continue
            for fn in ("events.jsonl", "disturbances.jsonl"):
                rows = _rows(preset, fn)
                if not rows:
                    continue
                compiled = compile_rules(from_events(rows))
                self.assertEqual(compiled.scheduled, rows,
                                 f"{preset}/{fn} 从旧行翻过来之后不再逐字相同")
                checked += len(rows)
        self.assertGreater(checked, 0)          # 前提：仓库里确实有旧行可翻

    def test_compiled_schedule_runs_the_same_world(self):
        """同一批投递，两种安放处：写进 `data.add()` vs 写成脚本的 FRAME 订阅。"""
        from apps.script import Script, compile_rules, from_events

        rows = [{"frame": 5, "channel": "world", "capability": "emit",
                 "selector": None, "label": "甲", "payload": {"event": "e1"}},
                {"frame": 20, "channel": "world", "capability": "suppress_slot",
                 "selector": {"expr": "order:1"}, "payload": {}},
                {"frame": 60, "when": "deaths >= 0", "channel": "observer",
                 "capability": "emit", "selector": None, "label": "丙",
                 "payload": {"event": "e3"}}]

        a = _run("_default", frames=200, install=lambda d: d.add(list(rows)))

        def plant(data):
            Script(compile_rules(from_events(rows))).install(data)

        b = _run("_default", frames=200, install=plant)
        self.assertEqual(a.records, b.records)
        self.assertEqual(a.final.digest(), b.final.digest())
        self.assertGreater(len(a.records), 0)   # 前提：这几条真的投出去过


class ReactiveSubscriptions(unittest.TestCase):
    """反应式订阅：事件 ↦ 下一帧的写回，只触发一次，`if` 说了算。"""

    ROWS = [{"on": "DISTURBANCE", "if": 'event("ping")',
             "do": [{"emit": "pong"}]}]

    def test_fires_next_frame_and_only_once(self):
        sess, script = _session(self.ROWS, events=["ping"])
        # 两枚同名的外生事件：第二枚落在 20 帧 —— 若反应会被重新武装，它就会再响一次
        sess.inject({"frame": 5, "capability": "emit",
                     "payload": {"event": "ping"}})
        sess.inject({"frame": 20, "capability": "emit",
                     "payload": {"event": "ping"}})
        sess.step(40)

        self.assertIn("pong", sess.observe()["events"])
        # 事件在第 5 帧 ⇒ 写回落在第 6 帧（下一帧生效），而不是第 5 帧、也不是第 21 帧
        self.assertEqual(sess.report.final.score["emitted_pong"], 6.0)
        self.assertEqual(script.fired, [0])

    def test_if_gates_the_reaction(self):
        rows = [{"on": "DISTURBANCE", "if": "frame >= 9999",
                 "do": [{"emit": "late"}]}]
        sess, script = _session(rows, events=["ping"])
        sess.inject({"frame": 5, "capability": "emit",
                     "payload": {"event": "ping"}})
        sess.step(40)
        self.assertNotIn("late", sess.observe()["events"])
        self.assertEqual(script.fired, [])

    def test_unknown_event_carries_no_reaction(self):
        """订阅类别对、但 `event("…")` 读的是另一件没发生的事 ⇒ 不响（且不报错）。"""
        sess, script = _session(self.ROWS, events=["ping"])
        sess.inject({"frame": 5, "capability": "emit",
                     "payload": {"event": "other"}})
        sess.step(40)
        self.assertNotIn("pong", sess.observe()["events"])
        self.assertEqual(script.fired, [])


class LiveObservationInsideCallbacks(unittest.TestCase):
    """条件读到的世界 = **事件那一帧**的世界（与预设的 `when` 同一口径）。"""

    def test_observe_mirrors_the_event_frame(self):
        watched, marks, sess = {}, {}, None

        def my_watch(frame, st, traj):
            watched[int(frame)] = st.digest()
            return True

        def peek(frame, kind, payload):
            if kind == "DISTURBANCE":
                marks[int(frame)] = sess.observe()["digest"]

        sess, _script = _session([{"on": "DISTURBANCE", "do": [{"emit": "seen"}]}],
                                 watch=my_watch, peek=peek)
        sess.inject({"frame": 5, "capability": "emit",
                     "payload": {"event": "ping"}})
        sess.step(30)

        # 第 5 帧的外生事件，和第 6 帧那次响应写回（`emit: seen`）各触发一回
        self.assertEqual(sorted(marks), [5, 6])
        for f in (5, 6):
            # 回调里读到的世界就是【这一帧】的世界 —— 而不是本次 step 起点（第 0 帧）
            self.assertEqual(marks[f], watched[f],
                             f"第 {f} 帧回调里读到的世界不是这一帧的世界")
            self.assertNotEqual(marks[f], watched[0])


class StaticGates(unittest.TestCase):
    """写错一律当场报错 —— 静默会把「写错了」变成「这条永远不触发」。"""

    def _err(self, rows, **kw):
        from apps.script import ScriptError, compile_rules
        with self.assertRaises(ScriptError) as cm:
            compile_rules(rows, **kw)
        return str(cm.exception)

    def test_unknown_subscription(self):
        self.assertIn("NOPE", self._err([{"on": "NOPE", "do": [{"emit": "x"}]}]))

    def test_reactive_must_not_carry_at(self):
        msg = self._err([{"on": "PROMOTION", "at": 10, "do": [{"emit": "x"}]}])
        self.assertIn("不该写 at", msg)

    def test_frame_subscription_needs_at(self):
        self.assertIn("须给 at", self._err([{"on": "FRAME", "do": [{"emit": "x"}]}]))

    def test_empty_do(self):
        self.assertIn("非空", self._err([{"on": "FRAME", "at": 1, "do": []}]))

    def test_unknown_condition_term(self):
        msg = self._err([{"on": "FRAME", "at": 1, "if": "nonesuch >= 1",
                          "do": [{"emit": "x"}]}])
        self.assertIn("nonesuch", msg)

    def test_writeback_needs_permit(self):
        msg = self._err([{"on": "FRAME", "at": 1,
                          "do": [{"inject": "suppress_slot:order:1"}]}])
        self.assertIn("permit", msg)

    def test_permit_must_be_registered(self):
        msg = self._err([{"on": "FRAME", "at": 1, "permit": "nobody",
                          "do": [{"inject": "suppress_slot:order:1"}]}])
        self.assertIn("nobody", msg)

    def test_emit_needs_no_permit(self):
        from apps.script import compile_rules
        compiled = compile_rules([{"on": "FRAME", "at": 1, "do": [{"emit": "x"}]}])
        self.assertEqual(len(compiled.scheduled), 1)

    def test_unknown_capability(self):
        msg = self._err([{"on": "FRAME", "at": 1, "permit": "preset",
                          "do": [{"inject": "nonesuch"}]}])
        self.assertIn("nonesuch", msg)

    def test_unknown_selector(self):
        msg = self._err([{"on": "FRAME", "at": 1, "permit": "preset",
                          "do": [{"inject": "suppress_slot:nonesuch"}]}])
        self.assertIn("nonesuch", msg)

    def test_presets_compile_clean(self):
        """闸门：仓库里每个预设的 `script.jsonl`（一旦有人开始写）都必须编译得过。"""
        from apps.script import Script
        from kernel.loader import Config, DataSet

        seen = 0
        root = os.path.join(ROOT, "presets")
        for preset in sorted(os.listdir(root)):
            if not os.path.isdir(os.path.join(root, preset)):
                continue
            data = DataSet(ROOT, preset=preset)
            ctx = Config(ROOT, lex_overlay=data.preset.get("lexicon"))
            Script.from_preset(data, cfg=ctx)          # 编译不过就抛 ScriptError
            seen += len(data.script)
        self.assertGreaterEqual(seen, 0)


class EventsAndScriptAreExclusive(unittest.TestCase):
    """同一批投递只许有一个安放处：`events.jsonl` 与 `script.jsonl` 同存即报错。"""

    def test_conflict_is_loud(self):
        from kernel.loader import ConfigError, DataSet

        with tempfile.TemporaryDirectory() as tmp:
            root = temp_root_with_copy(tmp)
            d = os.path.join(root, "presets", "_default")
            with open(os.path.join(d, "events.jsonl"), "w", encoding="utf-8") as f:
                f.write('{"frame": 3, "capability": "emit",'
                        ' "payload": {"event": "x"}}\n')
            with open(os.path.join(d, "script.jsonl"), "w", encoding="utf-8") as f:
                f.write('{"on": "FRAME", "at": 3, "do": [{"emit": "x"}]}\n')
            with self.assertRaises(ConfigError):
                DataSet(root, preset="_default")


if __name__ == "__main__":
    unittest.main()